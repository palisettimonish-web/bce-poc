"""Attributable kill, curtailment and the per-(scenario, mutant) table (2.16). Pure functions of logged runs."""

from detect import rules

COMPLETE, CURTAILED, INCOMPLETE = "COMPLETE", "CURTAILED", "INCOMPLETE"


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
    """{scenario_ref: {"clean": [...by rep], "mutant": {mid: [...by rep]}}} from completed 3e run records."""
    out = {}
    for r in records:
        if r.get("transport_failure") or r["stage"] != rules.STAGE_DETECT:
            continue
        slot = out.setdefault(r["scenario_ref"], {"arm": r["arm"], "slot": r["slot"], "clean": {}, "mutant": {}})
        if r["variant"] == "clean":
            slot["clean"].setdefault(r["rep"], r)
        else:
            slot["mutant"].setdefault(r["subject"], {}).setdefault(r["rep"], r)
    for slot in out.values():
        slot["clean"] = [slot["clean"][k] for k in sorted(slot["clean"])]
        slot["mutant"] = {m: [reps[k] for k in sorted(reps)] for m, reps in slot["mutant"].items()}
    return out


def build_table(records, slots_by_arm, info):
    """One row per DSL-valid scenario of every arm. Raises ValueError if any pair is INCOMPLETE."""
    grouped = group_records(records)
    nominal = rules.CLEAN_REPS + rules.MUTANT_REPS * len(info)
    table, problems = {}, []
    for arm, slots in slots_by_arm.items():
        for s in slots:
            if s["status"] != "VALID":
                continue
            g = grouped.get(s["ref"], {"clean": [], "mutant": {}})
            row = {"arm": arm, "slot": s["slot"], "nominal_executions": nominal, "clean_codes_per_rep": [sorted(r["violations"]) for r in g["clean"]],
                   "pairs": {}, "attributable": {}, "any_code": {}, "actual_executions": len(g["clean"]) + sum(len(v) for v in g["mutant"].values())}
            used = g["clean"] + [r for runs in g["mutant"].values() for r in runs]
            row["agent_tokens"] = sum((r["tokens"] or {}).get("input", 0) + (r["tokens"] or {}).get("output", 0) for r in used)
            for mid, i in info.items():
                runs = g["mutant"].get(mid, [])
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
