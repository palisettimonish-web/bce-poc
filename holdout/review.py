"""S7: human construct review packet and answer handling (Amendment 2, 2.10).

The review is label-blinded only and is not independent. Packets use fresh review ids in a seeded
random order; the key from review id to candidate id is not opened until every answer is validated.
"""

import json
import random
import re
from pathlib import Path

from agent import SYSTEM
from holdout import rules, schema

REVIEW_DIR = rules.HOLDOUT_DIR / "construct_review"
CHECKLIST = {
    "1": "Does the mutant actually change behavior?",
    "2": "Does the trigger activate the intended change?",
    "3": "Does the neutral condition avoid activation?",
    "4": "Is the mutation specific to its trigger class?",
    "5": "Does the existing oracle detect the intended failure?",
    "6": "Is the mutation plausibly representative of a real failure?",
}


class ReviewError(RuntimeError):
    pass


def review_ids(n):
    return [f"R{i:02d}" for i in range(1, n + 1)]


def packet_leaks(packet_text):
    """Tokens that must not appear in a blinded packet: gold ids/names, candidate ids, BCE, the arms."""
    gold = schema._gold()
    banned = [d["name"] for d in gold.values()] + list(gold) + ["BCE", "gold", "hypothesis"]
    hits = [b for b in banned if re.search(r"(?<![A-Za-z0-9_])" + re.escape(b) + r"(?![A-Za-z0-9_])", packet_text)]
    hits += re.findall(r"\bM\d{2}\b", packet_text)
    return hits


def build_packet(run):
    """Return (packet, key) for the candidates that passed S6. Pure; nothing is written."""
    done = run.completed()
    if "S6" not in done:
        raise ReviewError("the review packet needs S6 to be complete")
    ids = sorted(run.active("S7"))
    order = sorted(ids)
    random.Random(rules.REVIEW_SEED).shuffle(order)
    key = dict(zip(review_ids(len(order)), order))
    cat = rules.catalogue()
    items = {}
    for rid, cid in key.items():
        c = run.by_id[cid]
        op = cat["operators"][c["operator"]]
        rates = {}
        for stage in ("S1", "S2", "S3", "S4", "S5", "S6"):
            res = done[stage]["outcomes"].get(cid)
            if res is not None:
                rates[stage] = res["rates"]
        items[rid] = {
            "clean_system": SYSTEM,
            "system_edit": [dict(step) for step in c["edit"]],
            "mutant_system": schema.build_mutant_system(c),
            "operator": {"name": op["name"], "definition": op["definition"], "real_world_analogue": op["analogue"]},
            "plausibility_note": c["plausibility_note"],
            "trigger_class_description": c["trigger_class"]["description"],
            "trigger_instances": [{"id": i["id"], "scenario": i["scenario"]} for i in c["trigger_instances"]],
            "neutral_instances": [{"id": i["id"], "scenario": i["scenario"]} for i in c["neutral_instances"]],
            "intended_codes": {code: cat["oracle_rule_text"][code] for code in c["intended_codes"]},
            "primary_code": c["primary_code"],
            "stage_rates": rates,
            "checklist": CHECKLIST,
        }
    packet = {"seed": rules.REVIEW_SEED, "items": items}
    leaks = packet_leaks(json.dumps(packet))
    if leaks:
        raise ReviewError(f"packet would reveal labels: {sorted(set(leaks))}")
    return packet, key


def write_packet(run, review_dir=REVIEW_DIR):
    packet_path, key_path = Path(review_dir) / "packet.json", Path(review_dir) / "key.json"
    if packet_path.exists() or key_path.exists():
        raise ReviewError("review files already exist; they are never overwritten")
    packet, key = build_packet(run)
    Path(review_dir).mkdir(parents=True, exist_ok=True)
    packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    key_path.write_text(json.dumps(key, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return packet_path, key_path


def validate_answers(answers, expected_ids):
    errors = []
    if set(answers) != set(expected_ids):
        errors.append(f"answers must cover exactly {sorted(expected_ids)}")
        return errors
    for rid, items in answers.items():
        if not (isinstance(items, dict) and set(items) == set(rules.REVIEW_ITEMS)):
            errors.append(f"{rid}: must answer items {list(rules.REVIEW_ITEMS)}")
            continue
        for n, a in items.items():
            if not (isinstance(a, dict) and set(a) == {"answer", "reason"} and a["answer"] in ("yes", "no")
                    and isinstance(a["reason"], str) and a["reason"].strip()):
                errors.append(f"{rid} item {n}: needs answer yes|no and a non-empty reason")
    return errors


def outcomes_from_answers(run, answers, key_path=REVIEW_DIR / "key.json", packet_path=REVIEW_DIR / "packet.json"):
    """S7 outcomes. The key is opened only after every answer has been validated."""
    expected = list(json.loads(Path(packet_path).read_text(encoding="utf-8"))["items"])
    errors = validate_answers(answers, expected)
    if errors:
        raise ReviewError("; ".join(errors))
    key = json.loads(Path(key_path).read_text(encoding="utf-8"))
    outcomes = {}
    for cid in run.active("S7"):
        outcomes[cid] = {"status": rules.PASS, "details": {}, "rates": {}}
    for rid, cid in key.items():
        failed = {n: a["reason"] for n, a in answers[rid].items() if a["answer"] == "no"}
        outcomes[cid] = {
            "status": "CONSTRUCT_REVIEW_FAILURE" if failed else rules.PASS,
            "details": {"review_id": rid, "no_answers": failed},
            "rates": {},
        }
    return outcomes
