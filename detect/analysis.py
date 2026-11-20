"""3e detection analysis (2.16, 2.17; Amendment 3 A3.4). Pure functions of the logged runs and the frozen holdout files.

    PYTHONPATH=. python -m detect.analysis [--discovery-scores PATH]

Nothing here changes a kill, a threshold or a gate. Recall, precision and stability come from the judge step, which is
not part of this module; without them the gates are reported as PENDING_DISCOVERY_SCORES.
"""

import argparse
import json
import math
import random
import sys

from detect import drift, holdout_info, kills, rules, runner
from detect.session import Session

EPS = 1e-9


def budgets_for(arm):
    return rules.ARM_A_BUDGETS if arm == "A" else rules.BUDGETS


# ---------------------------------------------------------------------------- kills within a budget

def rows_in(table, arm, budget):
    return [r for r in table.values() if r["arm"] == arm and r["slot"] < budget]


def killed_variants(table, arm, budget, info, key="attributable"):
    return {m for r in rows_in(table, arm, budget) for m, codes in r[key].items() if codes and m in info}


def killed_pairs(table, arm, budget, info, key="attributable"):
    return {(m, c) for r in rows_in(table, arm, budget) for m, codes in r[key].items() if m in info for c in codes}


def variants_by_dim(info):
    return holdout_info.variants_by_dimension(info)


def dims_detected(killed, info):
    return sorted({info[m]["dimension"] for m in killed})


# ---------------------------------------------------------------------------- bootstrap (2.16 l.380-385)

def percentile(values, q):
    """Linear interpolation between order statistics (the numpy default)."""
    v = sorted(values)
    pos = (len(v) - 1) * q / 100.0
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(v) - 1)
    return v[lo] * (1 - (pos - lo)) + v[hi] * (pos - lo)


def bootstrap(killed, vbd, resamples=rules.BOOTSTRAP_RESAMPLES, seed=rules.BOOTSTRAP_SEED, dims=rules.DIMENSIONS):
    """Paired cluster bootstrap. `killed` is {(arm, budget): set(variants)}; one resample is shared by every arm and budget.

    Each resample draws len(dims) dimensions with replacement; within each drawn dimension that has admitted variants it draws
    its variants with replacement. An arm detects a drawn dimension if any drawn variant is killed. Rates use the fixed
    denominator len(dims). Descriptive only.
    """
    rng = random.Random(seed)
    keys = sorted(killed)
    samples = {k: [] for k in keys}
    for _ in range(resamples):
        picks = []
        for d in (rng.choice(dims) for _ in dims):
            vs = vbd.get(d, [])
            picks.append([rng.choice(vs) for _ in vs] if vs else [])
        for k in keys:
            samples[k].append(sum(1 for p in picks if p and any(v in killed[k] for v in p)) / len(dims))
    out = {}
    for arm, b in keys:
        s = samples[(arm, b)]
        out[f"{arm}@{b}"] = {"mean": sum(s) / len(s), "low": percentile(s, rules.CI_LOW), "high": percentile(s, rules.CI_HIGH)}
    for b in rules.BUDGETS:
        if ("B", b) in samples and ("C", b) in samples:
            diff = [c - bb for c, bb in zip(samples[("C", b)], samples[("B", b)])]
            out[f"C-B@{b}"] = {"mean": sum(diff) / len(diff), "low": percentile(diff, rules.CI_LOW), "high": percentile(diff, rules.CI_HIGH)}
    return {"resamples": resamples, "seed": seed, "interval": "percentile 95%", "descriptive_only": True, "estimates": out}


# ---------------------------------------------------------------------------- detection block

def detection_block(table, info, with_bootstrap=True, resamples=rules.BOOTSTRAP_RESAMPLES):
    """Dimension-level detection (primary) and the variant-level secondary measures, for one set of admitted variants."""
    vbd = variants_by_dim(info)
    testable = sorted(vbd)
    arms, killed_sets = {}, {}
    for arm in rules.ARMS:
        arms[arm] = {}
        for b in budgets_for(arm):
            killed = killed_variants(table, arm, b, info)
            killed_sets[(arm, b)] = killed
            dims = dims_detected(killed, info)
            rows = rows_in(table, arm, b)
            pairs = killed_pairs(table, arm, b, info)
            arms[arm][b] = {
                "killed_variants": sorted(killed),
                "dimensions_detected": dims,
                "dimensions_detected_count": len(dims),
                "dimension_detection_rate": len(dims) / rules.DENOMINATOR,
                "rate_over_testable_dimensions": (len(dims) / len(testable)) if testable else None,
                "variant_kill_rate": (len(killed) / len(info)) if info else None,
                "distinct_mutant_code_pairs": sorted(f"{m}:{c}" for m, c in pairs),
                "any_code_killed_variants": sorted(killed_variants(table, arm, b, info, "any_code")),
                "any_code_pairs": len(killed_pairs(table, arm, b, info, "any_code")),
                "valid_scenarios": len(rows),
                "nominal_executions": sum(r["nominal_executions"] for r in rows),
                "actual_executions": sum(r["actual_executions"] for r in rows),
                "agent_tokens": sum(r["agent_tokens"] for r in rows),
                "curtailed_pairs": sum(1 for r in rows for st in r["pairs"].values() if st == kills.CURTAILED),
            }
    classes = {}
    for cls in sorted(set(rules.CLASS_OF.values())):
        members = [d for d in rules.DIMENSIONS if rules.CLASS_OF[d] == cls]
        classes[cls] = {"dimensions": members, "testable": [d for d in members if d in vbd], "denominator": len(members), "arms": {
            arm: {b: len([d for d in arms[arm][b]["dimensions_detected"] if d in members]) for b in budgets_for(arm)} for arm in rules.ARMS}}
    per_dim = {}
    for d in rules.DIMENSIONS:
        vs = vbd.get(d, [])
        per_dim[d] = {"class": rules.CLASS_OF[d], "variants": vs, "NOT_DETECTION_TESTABLE": not vs,
                      "detected": {arm: {b: d in arms[arm][b]["dimensions_detected"] for b in budgets_for(arm)} for arm in rules.ARMS}}
    out = {"T": len(testable), "testable_dimensions": testable,
           "not_detection_testable": [d for d in rules.DIMENSIONS if d not in vbd], "denominator": rules.DENOMINATOR,
           "arms": arms, "classes": classes, "per_dimension": per_dim}
    if with_bootstrap:
        out["bootstrap"] = bootstrap({k: v for k, v in killed_sets.items() if k[0] in rules.GENERATED_ARMS}, vbd, resamples)  # B, C, C-B only (2.16 l.380); A is descriptive
    return out


def tier(T):
    if T < rules.T_INVALID_BELOW:
        return "INVALID"
    return "EXPLORATORY" if T < rules.T_NORMAL_FROM else "NORMAL"


def sensitivity(table, info, drop, label, resamples=rules.BOOTSTRAP_RESAMPLES):
    """A3.4: the same metrics without the variants in `drop`; the denominator stays 8."""
    subset = {m: i for m, i in info.items() if m not in drop}
    block = detection_block(table, subset, resamples=resamples)
    block.update({"label": label, "excluded_variants": sorted(drop), "T_prime": block["T"], "status": "secondary and descriptive; enters no gate"})
    return block


# ---------------------------------------------------------------------------- gates (2.17)

def _adv_budgets(c, b, key):
    return sum(1 for x in rules.BUDGETS if c[x][key] > b[x][key])


def gates(det, discovery):
    """Success / inconclusive / against per 2.17, and the original gates (construction-biased) per l.404.

    Verdict precedence: success if every condition holds, else against if its condition holds, else inconclusive.
    """
    arms = det["arms"]
    dB, dC = ({b: arms[a][b]["dimensions_detected_count"] for b in rules.BUDGETS} for a in ("B", "C"))
    kB, kC = ({b: len(arms[a][b]["killed_variants"]) for b in rules.BUDGETS} for a in ("B", "C"))
    kA25 = len(arms["A"][25]["killed_variants"])
    out = {"detection": {"dimension_counts": {"B": dB, "C": dC}, "C_gt_B_at_100": dC[100] > dB[100], "C_ge_B_at_50": dC[50] >= dB[50],
                         "budgets_with_C_advantage": [b for b in rules.BUDGETS if dC[b] > dB[b]], "B_ge_C_at_100": dB[100] >= dC[100]},
           "tier": tier(det["T"])}
    if not discovery:
        out.update(verdict="PENDING_DISCOVERY_SCORES", original_verdict="PENDING_DISCOVERY_SCORES")
        return out
    r, p, j = discovery["recall"], discovery["precision"], discovery["stability_jaccard"]
    diff = r["C"] - r["B"]

    def verdict(det_gt100, det_ge50, adv_budgets, against_det, extra_success, extra_against):
        success = diff >= rules.RECALL_MARGIN - EPS and p["C"] >= p["B"] - EPS and det_gt100 and det_ge50 and j["C"] >= rules.JACCARD_MIN - EPS and extra_success
        against = (r["B"] >= r["C"] - EPS and against_det) or extra_against
        named = abs(diff) < rules.RECALL_MARGIN - EPS or len(adv_budgets) == 1
        if success:
            return "SUCCESS_FOR_BCE", named
        if against:
            return "EVIDENCE_AGAINST_THESIS", named
        return "INCONCLUSIVE", named

    v, named = verdict(dC[100] > dB[100], dC[50] >= dB[50], out["detection"]["budgets_with_C_advantage"], dB[100] >= dC[100], True, False)
    out.update(verdict=v, inconclusive_by_named_condition=named,
               discovery={"recall_difference_C_minus_B": diff, "precision_C_ge_B": p["C"] >= p["B"] - EPS, "stability_jaccard_C": j["C"],
                          "stability_jaccard_B": j["B"], "stability_jaccard_arm_read_as": "C"})
    adv_orig = [b for b in rules.BUDGETS if kC[b] > kB[b]]
    vo, named_o = verdict(kC[100] > kB[100], kC[50] >= kB[50], adv_orig, kB[100] >= kC[100], kC[25] > kA25, kC[25] <= kA25)
    out.update(original_verdict=vo, original_label="construction-biased; variant-level kills and the C > A at 25 clause",
               original_inconclusive_by_named_condition=named_o, original_counts={"killed_variants": {"B": kB, "C": kC}, "A_at_25": kA25})
    return out


# ---------------------------------------------------------------------------- discovery-side inputs and cost

def discovery_counts(slots_by_arm, stats):
    out = {}
    for arm in rules.GENERATED_ARMS:
        s = slots_by_arm[arm]
        valid = sum(1 for x in s if x["status"] == "VALID")
        invalid = [{"ref": x["ref"], "errors": x["errors"]} for x in s if x["status"] == "INVALID"]
        missing = [x["ref"] for x in s if x["status"] == "MISSING"]
        out[arm] = {"slots": len(s), "valid_slots": valid, "invalid_slots": len(invalid), "missing_slots": len(missing),
                    "invalid": invalid, "missing": missing, **stats[arm], "regenerated_or_repaired": 0,
                    "scenario_validity": (stats[arm]["returned_valid"] / stats[arm]["returned"]) if stats[arm]["returned"] else None}
    return out


def cost(det, slots_by_arm, gen_tokens):
    """Failures per execution and cost per true failure (metrics 10), per arm and budget."""
    out = {}
    for arm in rules.ARMS:
        out[arm] = {}
        for b in budgets_for(arm):
            blk = det["arms"][arm][b]
            n = len(blk["distinct_mutant_code_pairs"])
            used = {}
            for s in slots_by_arm[arm]:
                if s["slot"] < b and s["run"] is not None:
                    used[s["run"]] = used.get(s["run"], 0) + 1
            toks = gen_tokens.get(arm, {})
            pro_rata = sum((toks.get(run) or 0) * cnt / rules.SLOTS_PER_RUN for run, cnt in used.items())
            total = sum(v or 0 for v in toks.values())
            out[arm][b] = {
                "distinct_true_failures": n,
                "failures_per_execution_nominal": n / blk["nominal_executions"] if blk["nominal_executions"] else None,
                "failures_per_execution_actual": n / blk["actual_executions"] if blk["actual_executions"] else None,
                "generation_tokens_pro_rata_by_slots": pro_rata, "generation_tokens_all_runs": total,
                "cost_per_true_failure_pro_rata": ((pro_rata + blk["agent_tokens"]) / n) if n else None,
                "cost_per_true_failure_all_generation_runs": ((total + blk["agent_tokens"]) / n) if n else None,
            }
    return out


def generation_tokens(scenario_dir=None):
    """{arm: {run: input+output tokens of that discovery call}} from the sealed run metadata."""
    out = {}
    for arm in rules.GENERATED_ARMS:
        out[arm] = {}
        for run in range(1, rules.RUNS_PER_ARM + 1):
            meta = json.loads(runner.slots.scenario_path(arm, run, scenario_dir).read_text(encoding="utf-8"))["meta"]
            t = meta.get("tokens") or {}
            out[arm][run] = (t.get("input") or 0) + (t.get("output") or 0)
    return out


def natural_failures(table):
    out = {}
    for arm in rules.ARMS:
        codes = {}
        for r in table.values():
            if r["arm"] == arm:
                for c in r["natural_failures"]:
                    codes[c] = codes.get(c, 0) + 1
        out[arm] = {"scenarios_with_natural_failure": sum(1 for r in table.values() if r["arm"] == arm and r["natural_failures"]), "codes": codes}
    return out


# ---------------------------------------------------------------------------- whole analysis

def analyze(table, slots_by_arm, stats, info, drift_verdict, gen_tokens, discovery=None, resamples=rules.BOOTSTRAP_RESAMPLES, served_models=()):
    primary = detection_block(table, info, resamples=resamples)
    overlap = {m for m, i in info.items() if "OVERLAP" in i["flags"]}
    suspect = set(drift_verdict["drift_suspect"]) if drift_verdict else None
    counts = discovery_counts(slots_by_arm, stats)
    c_invalid = 1 - counts["C"]["scenario_validity"] if counts["C"]["scenario_validity"] is not None else None
    return {
        "analysis": "step3e detection (2.16, 2.17, A3.4)",
        "pilot_scope": "T-dimension pilot on one toy agent; POC gates, not significance claims (A3.1, P A8)",
        "tier": tier(primary["T"]),
        "flags": {"POTENTIALLY_INVALID": bool(drift_verdict and drift_verdict["potentially_invalid"]),
                  "served_model_identity": drift_verdict["served_model_identity"] if drift_verdict else None,
                  "OVERLAP": sorted(overlap), "DRIFT_SUSPECT": sorted(suspect) if suspect is not None else None},
        "invalid_experiment_checks": {"T_below_4": primary["T"] < rules.T_INVALID_BELOW,
                                      "arm_C_over_half_dsl_invalid": (c_invalid is not None and c_invalid > rules.INVALID_C_FRACTION)},
        "discovery_side_inputs": counts,
        "detection": primary,
        "gates": gates(primary, discovery),
        "cost": cost(primary, slots_by_arm, gen_tokens),
        "natural_failures": natural_failures(table),
        "sensitivity_without_OVERLAP": sensitivity(table, info, overlap, "without OVERLAP variants", resamples),
        "sensitivity_without_DRIFT_SUSPECT": (sensitivity(table, info, suspect, "without DRIFT_SUSPECT variants", resamples)
                                              if suspect is not None else None),
        "served_models_3e": list(served_models),
        "execution_note": "nominal executions follow P metric 10; actual executions are the logged runs after curtailment (2.16 l.375)",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="detect.analysis")
    parser.add_argument("--discovery-scores", default=None, help="JSON {recall, precision, stability_jaccard} each {B, C}")
    args = parser.parse_args(argv)
    from detect import preflight
    problems = preflight.verify()
    if problems:
        print("\n".join(problems))
        print("STOP: pre-3e freeze verification failed")
        return 1
    session = Session(rules.DETECTION_DIR, None)
    done = session.completed(runner.STATUS_DETECT_DONE)
    if not done:
        print("STOP: detection is not complete")
        return 1
    info = holdout_info.load_admitted()
    slots_by_arm, stats = runner.load_all_slots()
    table = kills.build_table(session.records(), slots_by_arm, info)
    drift_done = Session(rules.DRIFT_DIR, None).completed(drift.STATUS_DONE)
    discovery = json.loads(open(args.discovery_scores, encoding="utf-8").read()) if args.discovery_scores else None
    result = analyze(table, slots_by_arm, stats, info, drift_done[-1] if drift_done else None, generation_tokens(), discovery,
                     served_models=done[-1]["served_models"])
    rules.ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    path = rules.ANALYSIS_DIR / "detection_analysis.json"
    with path.open("x", encoding="utf-8") as handle:  # never overwritten
        json.dump(result, handle, indent=1, sort_keys=True)
        handle.write("\n")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
