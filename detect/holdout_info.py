"""Admitted mutants and their frozen attributes, read from the sealed holdout files (evaluator side only)."""

import json

from agent import SYSTEM
from holdout import rules as holdout_rules
from holdout import runtime, schema, seal

CANDIDATES = holdout_rules.HOLDOUT_DIR / "candidates.json"
STATUS = holdout_rules.VALIDATION_DIR / "status.jsonl"


def s5_flags(status_path=STATUS):
    flags = {}
    for rec in runtime.JsonlLog(status_path).read():
        if rec.get("type") == "stage_complete" and rec["stage"] == "S5":
            for cid, out in rec["outcomes"].items():
                flags[cid] = list(out.get("flags", []))
    return flags


def load_admitted(eligibility=None, candidates=CANDIDATES, status_path=STATUS):
    """{mutant_id: info} for every ADMITTED candidate, in id order. Never changes anything."""
    elig = json.loads((eligibility or seal.ELIGIBILITY).read_text(encoding="utf-8"))["mapping"]
    by_id = {c["id"]: c for c in schema.load_candidates(candidates)}
    flags = s5_flags(status_path)
    info = {}
    for cid in sorted(elig):
        if elig[cid]["status"] != holdout_rules.ADMITTED:
            continue
        c = by_id[cid]
        info[cid] = {
            "dimension": c["dimension"],
            "primary_code": c["primary_code"],
            "intended_codes": list(c["intended_codes"]),
            "flags": sorted(flags.get(cid, [])),
            "system": schema.build_mutant_system(c, SYSTEM),
            "trigger_instance_1": c["trigger_instances"][0],
        }
    return info


def variants_by_dimension(info):
    out = {}
    for mid, i in info.items():
        out.setdefault(i["dimension"], []).append(mid)
    return {d: sorted(v) for d, v in out.items()}
