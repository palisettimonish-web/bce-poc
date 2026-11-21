"""Attributable kill, curtailment and the per-(scenario, mutant) table (2.16). Pure functions of logged runs."""

from detect import rules
from detect.session import is_completed, is_rejected

COMPLETE, CURTAILED, INCOMPLETE = "COMPLETE", "CURTAILED", "INCOMPLETE"
REJECTED = "REJECTED"  # A5.1: a run of the pair ended PROVIDER_REJECTED; the pair cannot be a kill (execution-level, not DSL-invalid)


def count(runs, code):
    return sum(1 for r in runs if code in r["violations"])


def codes_in(runs):
    return {c for r in runs for c in r["violations"]}


def curtailable(first_two, clean_runs):
    """True when neither of the first two mutant runs contains a code absent from all clean runs (2.16 l.375)."""
    return codes_in(first_two) <= codes_in(clean_runs)


def attributable_codes(intended, mutant_runs, clean_runs):
    """Intended codes in >= 2 of 3 mutant runs and 0 of 3 clean runs (2.16 l.376)."""
    return [c for c in intended if count(mutant_runs, c) >= rules.KILL_MUTANT_MIN and count(clean_runs, c) == 0]


def any_code_kills(mutant_runs, clean_runs):
    """The original any-code kill (P l.64), reported alongside; never the primary metric."""
    return sorted(c for c in codes_in(mutant_runs) if count(mutant_runs, c) >= rules.KILL_MUTANT_MIN and count(clean_runs, c) == 0)


def pair_status(mutant_runs, clean_runs):
    """COMPLETE (3 runs), CURTAILED (2 runs and the outcome cannot change) or INCOMPLETE."""
    if len(clean_runs) < rules.CLEAN_REPS:
        return INCOMPLETE
    if len(mutant_runs) >= rules.MUTANT_REPS:
        return COMPLETE
    if len(mutant_runs) == rules.MUTANT_REPS - 1 and curtailable(mutant_runs, clean_runs):
        return CURTAILED
    return INCOMPLETE


def group_records(records):
    """{scenario_ref: {"clean": [...by rep], "mutant": {mid: [...by rep]}, "rejected_clean": [rep], "rejected_mutant": {mid: [rep]}}}.

    Completed 3e run records only fill "clean" and "mutant"; PROVIDER_REJECTED terminal records are listed apart (A5.1). The first
    final record per key wins. Retryable transport failures are ignored.
    """
    out = {}
    for r in records:
        if r["stage"] != rules.STAGE_DETECT or not (is_completed(r) or is_rejected(r)):
            continue
        slot = out.setdefault(r["scenario_ref"], {"arm": r["arm"], "slot": r["slot"], "clean": {}, "mutant": {},
                                                  "rejected_clean": {}, "rejected_mutant": {}})
        done = is_completed(r)
        if r["variant"] == "clean":
            (slot["clean"] if done else slot["rejected_clean"]).setdefault(r["rep"], r)
        else:
            (slot["mutant"] if done else slot["rejected_mutant"]).setdefault(r["subject"], {}).setdefault(r["rep"], r)
    for slot in out.values():
        slot["clean"] = [slot["clean"][k] for k in sorted(slot["clean"])]
        slot["mutant"] = {m: [reps[k] for k in sorted(reps)] for m, reps in slot["mutant"].items()}
        slot["rejected_clean"] = sorted(slot["rejected_clean"])
        slot["rejected_mutant"] = {m: sorted(reps) for m, reps in slot["rejected_mutant"].items()}
    return out


def build_table(records, slots_by_arm, info):
    """One row per DSL-valid scenario of every arm. Raises ValueError if any pair is INCOMPLETE.

    A pair is REJECTED (A5.1) when any of its runs ended PROVIDER_REJECTED: a rejected clean run rejects every pair of the scenario
    (the 0-of-3 clean condition cannot be established), a rejected mutant run rejects that pair. A REJECTED pair has no attributable
    and no any-code kill, whatever its other runs show; nothing is imputed for the missing outcome.
    """
    grouped = group_records(records)
    nominal = rules.CLEAN_REPS + rules.MUTANT_REPS * len(info)
    table, problems = {}, []
    for arm, slots in slots_by_arm.items():
        for s in slots:
            if s["status"] != "VALID":
                continue
            g = grouped.get(s["ref"], {"clean": [], "mutant": {}, "rejected_clean": [], "rejected_mutant": {}})
            rejected_runs = len(g["rejected_clean"]) + sum(len(v) for v in g["rejected_mutant"].values())
            row = {"arm": arm, "slot": s["slot"], "nominal_executions": nominal, "clean_codes_per_rep": [sorted(r["violations"]) for r in g["clean"]],
                   "pairs": {}, "attributable": {}, "any_code": {}, "actual_executions": len(g["clean"]) + sum(len(v) for v in g["mutant"].values()),
                   "rejected_executions": rejected_runs, "clean_rejected": bool(g["rejected_clean"])}
            used = g["clean"] + [r for runs in g["mutant"].values() for r in runs]
            row["agent_tokens"] = sum((r["tokens"] or {}).get("input", 0) + (r["tokens"] or {}).get("output", 0) for r in used)
            for mid, i in info.items():
                runs = g["mutant"].get(mid, [])
                if g["rejected_clean"] or g["rejected_mutant"].get(mid):
                    row["pairs"][mid] = REJECTED
                    row["attributable"][mid] = []
                    row["any_code"][mid] = []
                    continue
                st = pair_status(runs, g["clean"])
                row["pairs"][mid] = st
                if st == INCOMPLETE:
                    problems.append(f"{s['ref']}/{mid}")
                    continue
                row["attributable"][mid] = attributable_codes(i["intended_codes"], runs, g["clean"])
                row["any_code"][mid] = any_code_kills(runs, g["clean"])
            row["natural_failures"] = sorted(c for c in codes_in(g["clean"]) if count(g["clean"], c) >= rules.NATURAL_FAILURE_MIN)
            table[s["ref"]] = row
    if problems:
        raise ValueError(f"{len(problems)} (scenario, mutant) pairs are incomplete, e.g. {problems[:3]}")
    return table
