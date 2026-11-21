"""The discovery judge step (scoring protocol lines 5-15; preregistration metrics 1-6; Amendment 5, A5.6).

    PYTHONPATH=. python -m detect.judge prepare
    PYTHONPATH=. python -m detect.judge score --raw-dir DIR [--human PATH]

The judge itself is a fresh Claude subagent with no session context (SP l.8). This module makes no model call. `prepare` pools
and shuffles the items, assembles one frozen-template prompt per batch of at most 40, and fixes the 20% human sample before any
judge runs. The operator gives each prompt to the subagent once and stores its answer unedited as `batch_NNN.json` in the raw
directory. `score` parses those answers strictly (no repair, no re-run) and computes the discovery metrics of the preregistration.

It reads only the sealed scenario and candidate files, the gold list, the base coverage and the judge prompt. It never reads a
detection result, the holdout mapping, a mutant or an oracle code (2.19). Every function is deterministic and synthetic-testable.
"""

import argparse
import hashlib
import json
import math
import random
import sys

from bce import dsl
from detect import rules, slots

ROOT = rules.ROOT
GOLD_PATH = ROOT / "gold_hidden_dimensions.json"
COVERAGE_PATH = ROOT / "experiments" / "step3_base_coverage_v1.json"
PROMPT_PATH = ROOT / "evaluate" / "judge_prompt_v1.txt"
NORMALIZED_DIR = ROOT / "experiments" / "step3" / "normalized"
HIDDEN_FROM_JUDGE = ("candidate_id", "confidence", "run_id", "position")  # SP l.7: no arm, run id, confidence or targeted candidate id
CANDIDATE, SCENARIO = "candidate", "scenario"


class JudgeError(RuntimeError):
    """A sealed input or a judge answer is not as the protocol requires. Nothing is repaired or re-run."""


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------- inputs

def load_gold(path=GOLD_PATH):
    """[{id, name, values}] for the 17 gold dimensions: name and values only, no provenance or rationale (SP l.8)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [{"id": d["id"], "name": d["name"], "values": d["values"]} for d in doc["dimensions"]]


def load_covered(path=COVERAGE_PATH):
    """The already-covered list: the dimension names and observed values of the base coverage (SP l.8)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [{"name": d["name"], "observed_values": d["observed_values"]} for d in doc["dimensions"]]


def candidate_path(arm, run, normalized_dir=None):
    return (normalized_dir or NORMALIZED_DIR) / f"{arm}_run_{run:03d}_candidates.json"


def load_items(scenario_dir=None, normalized_dir=None):
    """Every judged item of arms B and C with its hidden metadata, in a deterministic (unshuffled) order.

    Arm C: every candidate (a candidate that is not an object is not valid and is not judged) and every DSL-valid scenario. Arm B:
    every DSL-valid scenario (SP l.6, A5.6). DSL-invalid scenarios are not judged: they are not valid items (metric 1), count only
    in the validity metric (metric 4) and earn no recall credit. Positions of 20 and above are judged and flagged `in_budget: False`.
    """
    items, stats = [], {}
    for arm in rules.GENERATED_ARMS:
        stats[arm] = {"candidates": 0, "candidates_not_objects": 0, "scenarios_returned": 0, "scenarios_valid": 0, "scenarios_invalid": 0}
        for run in range(1, rules.RUNS_PER_ARM + 1):
            spath = slots.scenario_path(arm, run, scenario_dir)
            if not spath.exists():
                raise JudgeError(f"missing sealed file: {spath}")
            if arm == "C":
                cpath = candidate_path(arm, run, normalized_dir)
                if not cpath.exists():
                    raise JudgeError(f"missing sealed file: {cpath}")
                for c in json.loads(cpath.read_text(encoding="utf-8"))["candidates"]:
                    if not isinstance(c, dict) or set(c) == {"raw", "run_id", "position"}:  # normalize() wraps a non-object candidate as {raw, run_id, position}
                        stats[arm]["candidates_not_objects"] += 1
                        continue
                    stats[arm]["candidates"] += 1
                    items.append({"arm": arm, "run": run, "kind": CANDIDATE, "position": c["position"], "in_budget": True,
                                  "text": {k: v for k, v in c.items() if k not in HIDDEN_FROM_JUDGE}})
            for e in json.loads(spath.read_text(encoding="utf-8"))["scenarios"]:
                stats[arm]["scenarios_returned"] += 1
                errors = dsl.validate(e["scenario"])
                if bool(e["valid"]) != (not errors):
                    raise JudgeError(f"{arm} run {run} position {e['position']}: stored validity disagrees with the frozen DSL validator")
                if errors:
                    stats[arm]["scenarios_invalid"] += 1
                    continue
                stats[arm]["scenarios_valid"] += 1
                items.append({"arm": arm, "run": run, "kind": SCENARIO, "position": e["position"],
                              "in_budget": e["position"] < rules.SLOTS_PER_RUN,
                              "text": {k: v for k, v in e["scenario"].items() if k not in HIDDEN_FROM_JUDGE}})
    items.sort(key=lambda i: (i["arm"], i["run"], i["kind"], i["position"]))
    return items, stats


def pool(items, seed=rules.JUDGE_SEED):
    """All items pooled and shuffled with the fixed seed; opaque ids i0001... (SP l.7). Returns {id: item} in judge order."""
    shuffled = list(items)
    random.Random(seed).shuffle(shuffled)
    return {f"i{n:04d}": item for n, item in enumerate(shuffled, 1)}


def batches(ids, size=rules.JUDGE_BATCH_MAX):
    """Consecutive batches of at most `size` items (SP l.8)."""
    return [ids[k:k + size] for k in range(0, len(ids), size)]


def human_sample(ids, seed=rules.JUDGE_SEED, fraction=rules.HUMAN_SAMPLE_FRACTION):
    """A seeded random 20% sample of the pooled items, fixed before the judge runs (SP l.14)."""
    ids = sorted(ids)
    return sorted(random.Random(seed).sample(ids, math.ceil(fraction * len(ids)))) if ids else []


def render_items(pooled, ids):
    """What the judge sees of each item: its opaque id and its text, nothing about arm, run, position or targeted candidate."""
    return [{"item_id": i, "text": pooled[i]["text"]} for i in ids]


def build_prompt(template, gold, covered, pooled, ids):
    return (template.replace("{{REFERENCE}}", json.dumps(gold, indent=1, sort_keys=True))
            .replace("{{COVERED}}", json.dumps(covered, indent=1, sort_keys=True))
            .replace("{{ITEMS}}", json.dumps(render_items(pooled, ids), indent=1, sort_keys=True)))


# ---------------------------------------------------------------------------- parsing (strict, no repair)

def parse_batch(raw_text, expected_ids, gold_ids):
    """{item_id: {matched, known, cluster, evidence}} from one raw judge answer. Raises JudgeError on any deviation."""
    try:
        obj = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise JudgeError(f"the judge answer is not one JSON object: {exc}")
    if not isinstance(obj, dict) or set(obj) != {"judgments"} or not isinstance(obj["judgments"], list):
        raise JudgeError('the judge answer must be {"judgments": [...]} and nothing else')
    rows = obj["judgments"]
    if [r.get("item_id") if isinstance(r, dict) else None for r in rows] != list(expected_ids):
        raise JudgeError("the judge answer must hold exactly one entry per item, in the given order")
    out, gold_ids = {}, set(gold_ids)
    for r in rows:
        matched = r.get("matched_ids")
        if not isinstance(matched, list) or any(not isinstance(m, str) for m in matched) or len(set(matched)) != len(matched):
            raise JudgeError(f"{r['item_id']}: matched_ids must be a list of distinct strings")
        if set(matched) - gold_ids:
            raise JudgeError(f"{r['item_id']}: unknown reference ids {sorted(set(matched) - gold_ids)}")
        if not isinstance(r.get("known"), bool) or not isinstance(r.get("cluster"), str) or not isinstance(r.get("evidence"), str):
            raise JudgeError(f"{r['item_id']}: known must be boolean, cluster and evidence strings")
        out[r["item_id"]] = {"matched": set(matched), "known": r["known"], "cluster": r["cluster"].strip().lower(), "evidence": r["evidence"]}
    return out


# ---------------------------------------------------------------------------- scoring (metrics 1, 2, 3, 6; class breakdown)

def _effective(label, eligible):
    """Matches that earn credit: `known` items earn none (SP l.12) and only members of E count (SP l.11)."""
    return set() if label["known"] else label["matched"] & set(eligible)


def _jaccard(a, b):
    return len(a & b) / len(a | b) if (a | b) else 0.0  # two empty sets show no agreement; reported, not rewarded (A5.6)


def arm_scores(pooled, labels, arm, eligible=rules.DIMENSIONS, include=lambda item: True):
    """Precision, recall (pooled and per-run mean), novel dimensions and stability for one arm over the included valid items."""
    ids = [i for i, it in pooled.items() if it["arm"] == arm and include(it)]
    eff = {i: _effective(labels[i], eligible) for i in ids}
    per_run = {r: set().union(*[eff[i] for i in ids if pooled[i]["run"] == r]) if any(pooled[i]["run"] == r for i in ids) else set()
               for r in range(1, rules.RUNS_PER_ARM + 1)}
    union = set().union(*per_run.values())
    pairs = [(a, b) for a in per_run for b in per_run if a < b]
    jaccards = [_jaccard(per_run[a], per_run[b]) for a, b in pairs]
    novel = {labels[i]["cluster"] for i in ids if not labels[i]["matched"] and not labels[i]["known"]}
    classes = {}
    for cls in sorted(set(rules.CLASS_OF.values())):
        members = {d for d in eligible if rules.CLASS_OF[d] == cls}
        classes[cls] = {"members": sorted(members), "recall": len(union & members) / len(members) if members else None,
                        "precision": sum(1 for i in ids if eff[i] & members) / len(ids) if ids else None, "matched": sorted(union & members)}
    return {
        "valid_items": len(ids), "items_matching_E": sum(1 for i in ids if eff[i]),
        "precision": sum(1 for i in ids if eff[i]) / len(ids) if ids else 0.0,  # no valid item: 0.0 (valid_items says so), so the gate can compare
        "recall_pooled": len(union) / len(eligible), "matched_gold_pooled": sorted(union),
        "recall_per_run": {str(r): len(s) / len(eligible) for r, s in per_run.items()},
        "recall_per_run_mean": sum(len(s) for s in per_run.values()) / (len(per_run) * len(eligible)),
        "novel_dimensions": len(novel), "novel_clusters": sorted(novel),
        "stability_jaccard": sum(jaccards) / len(jaccards) if jaccards else 0.0,
        "stability_pairs_with_empty_union": sum(1 for a, b in pairs if not (per_run[a] | per_run[b])),
        "stability_union_size": len(union),
        "unique_clusters_across_runs": len({labels[i]["cluster"] for i in ids}),
        "known_items": sum(1 for i in ids if labels[i]["known"]),
        "items_matching_dev_only": sum(1 for i in ids if not labels[i]["known"] and labels[i]["matched"] & set(rules.DEV_ONLY_GOLD)),
        "classes": classes,
    }


def discovery_scores(pooled, labels, eligible=rules.DIMENSIONS, include=lambda item: True):
    """The per-arm scores and the {recall, precision, stability_jaccard} input that `detect.analysis.gates` reads."""
    arms = {arm: arm_scores(pooled, labels, arm, eligible, include) for arm in rules.GENERATED_ARMS}
    gate = {"recall": {a: arms[a]["recall_pooled"] for a in arms}, "precision": {a: arms[a]["precision"] for a in arms},
            "stability_jaccard": {a: arms[a]["stability_jaccard"] for a in arms}}
    return {"arms": arms, "gate_input": gate}


# ---------------------------------------------------------------------------- human agreement (SP l.14-15)

def agreement(judge_labels, human_matches, sample_ids, gold_ids):
    """Raw agreement on matched_ids as a set, and Cohen's kappa over the per-(item, gold id) binary decisions."""
    if set(human_matches) != set(sample_ids):
        raise JudgeError("the human answers must cover exactly the fixed sample")
    same = sum(1 for i in sample_ids if set(human_matches[i]) == judge_labels[i]["matched"])
    a = b = c = d = 0
    for i in sample_ids:
        for g in gold_ids:
            j, h = g in judge_labels[i]["matched"], g in set(human_matches[i])
            a, b, c, d = a + (j and h), b + (j and not h), c + ((not j) and h), d + ((not j) and (not h))
    n = a + b + c + d
    po = (a + d) / n
    pe = ((a + b) * (a + c) + (c + d) * (b + d)) / (n * n)
    kappa = 1.0 if pe == 1 else (po - pe) / (1 - pe)
    return {"items": len(sample_ids), "raw_agreement": same / len(sample_ids), "kappa": kappa, "decisions": n,
            "counts": {"both_match": a, "judge_only": b, "human_only": c, "neither": d}, "unreliable": kappa < rules.KAPPA_MIN}


def human_corrected(labels, human_matches):
    """The judge's labels with the human's matched sets on the sampled items; `known` and `cluster` stay the judge's. Reported, never silent."""
    return {i: ({**lab, "matched": set(human_matches[i])} if i in human_matches else lab) for i, lab in labels.items()}


def full_report(pooled, labels, gold, sample_ids, human_matches=None, counts=None):
    """Headline judge-based scores, the position-<20 sensitivity, the evaluation budget and the human audit when answers exist."""
    gold_ids = [g["id"] for g in gold]
    out = {"judge_based": discovery_scores(pooled, labels), "sensitivity_positions_below_20": discovery_scores(pooled, labels, include=lambda it: it["in_budget"]),
           "evaluation_budget": {"judge_items": len(pooled), "judge_calls": len(batches(list(pooled))), "human_sample_items": len(sample_ids)},
           "counts": counts or {}, "dev_only_gold": list(rules.DEV_ONLY_GOLD), "gate_input": None}
    if human_matches is None:
        out.update(human_audit="PENDING_HUMAN_REVIEW", reliability="PENDING_HUMAN_REVIEW")
        return out
    agree = agreement(labels, human_matches, sample_ids, gold_ids)
    out.update(human_audit=agree, reliability="UNRELIABLE" if agree["unreliable"] else "ACCEPTABLE")
    if agree["unreliable"]:
        out["human_corrected_on_sample"] = discovery_scores(pooled, human_corrected(labels, human_matches))
    return out


# ---------------------------------------------------------------------------- command line

def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:  # never overwritten
        handle.write(text)


def _json(obj):
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def prepare(out_dir=None, scenario_dir=None, normalized_dir=None, gold_path=GOLD_PATH, coverage_path=COVERAGE_PATH, prompt_path=PROMPT_PATH):
    """Write the pooled items' key, one prompt per batch, the human sample and a manifest of hashes. Overwrites nothing."""
    out_dir = out_dir or rules.JUDGE_DIR
    items, stats = load_items(scenario_dir, normalized_dir)
    pooled = pool(items)
    ids = list(pooled)
    gold, covered, template = load_gold(gold_path), load_covered(coverage_path), prompt_path.read_text(encoding="utf-8")
    sample = human_sample(ids)
    files = {}
    key = {"seed": rules.JUDGE_SEED, "items": {i: {k: v for k, v in it.items() if k != "text"} for i, it in pooled.items()},
           "human_sample": sample, "stats": stats}
    for n, batch in enumerate(batches(ids), 1):
        name = f"batch_{n:03d}_prompt.txt"
        files[name] = build_prompt(template, gold, covered, pooled, batch)
        key.setdefault("batches", []).append({"batch": n, "item_ids": batch, "prompt": name})
    files["items_text.json"] = _json({i: it["text"] for i, it in pooled.items()})
    files["human_packet.json"] = _json({"instructions": "For each item list the reference dimension ids it concretely names or exercises (possibly none). "
                                        "You are not shown any judge label.", "reference_dimensions": gold, "items": render_items(pooled, sample)})
    files["human_answers_template.json"] = _json({i: {"matched_ids": []} for i in sample})
    files["items_key.json"] = _json(key)
    manifest = {"seed": rules.JUDGE_SEED, "items": len(ids), "batches": len(key.get("batches", [])), "human_sample_items": len(sample),
                "template_sha256": sha256_text(template), "gold_sha256": sha256_text(gold_path.read_text(encoding="utf-8")),
                "coverage_sha256": sha256_text(coverage_path.read_text(encoding="utf-8")),
                "file_sha256": {n: sha256_text(t) for n, t in sorted(files.items())},
                "note": "the judge runs once per batch, answers are stored raw and never edited (SP l.8)"}
    for name, text in files.items():
        _write(out_dir / name, text)
    _write(out_dir / "prepare_manifest.json", _json(manifest))
    return {"items": len(ids), "batches": manifest["batches"], "human_sample_items": len(sample)}


def score(raw_dir, human_path=None, out_dir=None):
    """Parse the raw answers of every batch and write the discovery scores. The raw files are hashed, never altered."""
    out_dir = out_dir or rules.JUDGE_DIR
    key = json.loads((out_dir / "items_key.json").read_text(encoding="utf-8"))
    gold = load_gold()
    gold_ids = [g["id"] for g in gold]
    pooled = {i: {**meta, "text": None} for i, meta in key["items"].items()}
    labels, raw_hashes = {}, {}
    for b in key["batches"]:
        path = raw_dir / f"batch_{b['batch']:03d}.json"
        if not path.exists():
            raise JudgeError(f"missing raw judge answer: {path}")
        text = path.read_text(encoding="utf-8")
        raw_hashes[path.name] = sha256_text(text)
        labels.update(parse_batch(text, b["item_ids"], gold_ids))
    human = None
    if human_path:
        human = {i: v["matched_ids"] for i, v in json.loads(human_path.read_text(encoding="utf-8")).items()}
    report = full_report(pooled, labels, gold, key["human_sample"], human, key["stats"])
    report["gate_input"] = report["judge_based"]["gate_input"]  # headline = judge-based scores; a human-corrected variant is reported beside them, never silently
    report["raw_answer_sha256"] = raw_hashes
    _write(out_dir / "discovery_report.json", _json(report))
    _write(out_dir / "discovery_scores.json", _json(report["gate_input"]))  # exactly what `detect.analysis --discovery-scores` reads
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(prog="detect.judge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    sc = sub.add_parser("score")
    sc.add_argument("--raw-dir", required=True)
    sc.add_argument("--human", default=None)
    args = parser.parse_args(argv)
    from detect import preflight
    problems = preflight.verify()
    if problems:
        print("\n".join(problems))
        print("STOP: pre-3e freeze verification failed")
        return 1
    try:
        if args.cmd == "prepare":
            print(json.dumps(prepare(), indent=1))
        else:
            from pathlib import Path
            report = score(Path(args.raw_dir), Path(args.human) if args.human else None)
            print(json.dumps({"reliability": report["reliability"], "gate_input": report["gate_input"]}, indent=1))
    except (JudgeError, FileExistsError) as exc:
        print(f"STOP: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
