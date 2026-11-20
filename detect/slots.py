"""Budget slots (2.18). Loads the sealed 3d scenario files and the Arm A baseline; repairs and replaces nothing."""

import json

from bce import dsl
from detect import rules

VALID, INVALID, MISSING = "VALID", "INVALID", "MISSING"


class SlotError(RuntimeError):
    """A sealed scenario file is absent or inconsistent. Nothing is repaired."""


def scenario_path(arm, run, scenario_dir=None):
    return (scenario_dir or rules.SCENARIO_DIR) / f"{arm}_run_{run:03d}_scenarios.json"


def slot_ref(arm, run, position):
    return f"{arm}-r{run}-p{position:02d}"


def load_arm_slots(arm, scenario_dir=None):
    """The 100 slots of a generated arm. Slot k = run (k mod 5)+1, position floor(k/5) (2.18 l.411).

    A missing position is an invalid slot; positions >= 20 are excluded from every budget. Returns
    (slots, stats): `stats` counts the recorded positions >= 20 and all returned / DSL-valid scenario outputs.
    """
    runs, excluded, returned, returned_valid = {}, 0, 0, 0
    for run in range(1, rules.RUNS_PER_ARM + 1):
        path = scenario_path(arm, run, scenario_dir)
        if not path.exists():
            raise SlotError(f"missing sealed file: {path}")
        entries = json.loads(path.read_text(encoding="utf-8"))["scenarios"]
        by_pos = {}
        for e in entries:
            if e["position"] in by_pos:
                raise SlotError(f"{path}: duplicate position {e['position']}")
            by_pos[e["position"]] = e
        excluded += sum(1 for p in by_pos if p >= rules.SLOTS_PER_RUN)
        returned += len(by_pos)
        returned_valid += sum(1 for e in by_pos.values() if e["valid"])
        runs[run] = by_pos
    slots = []
    for k in range(rules.RUNS_PER_ARM * rules.SLOTS_PER_RUN):
        run, position = (k % rules.RUNS_PER_ARM) + 1, k // rules.RUNS_PER_ARM
        entry = runs[run].get(position)
        slot = {"arm": arm, "slot": k, "run": run, "position": position, "ref": slot_ref(arm, run, position)}
        if entry is None:
            slot.update(status=MISSING, scenario=None, world=None, errors=["missing position"])
        else:
            errors = dsl.validate(entry["scenario"])
            if bool(entry["valid"]) != (not errors):
                raise SlotError(f"{slot['ref']}: stored validity disagrees with the frozen DSL validator")
            if errors:
                slot.update(status=INVALID, scenario=None, world=None, errors=list(entry["errors"]))
            else:
                slot.update(status=VALID, scenario=entry["scenario"], world=dsl.to_world_scenario(entry["scenario"], slot["ref"]), errors=[])
        slots.append(slot)
    return slots, {"positions_ge_20": excluded, "returned": returned, "returned_valid": returned_valid}


def arm_a_slots(baseline):
    """Arm A: the fixed 35 scenarios in file order (A3 l.117). `baseline` is the list of world scenarios."""
    return [{"arm": "A", "slot": k, "run": None, "position": k, "ref": sc["id"], "status": VALID, "scenario": None, "world": sc, "errors": []}
            for k, sc in enumerate(baseline)]


def budget_slots(slots, budget):
    return [s for s in slots if s["slot"] < budget]
