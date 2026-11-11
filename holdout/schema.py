"""Candidate schema, mutant construction and the S0 static checks (Amendment 2, 2.2-2.5).

S0 involves no LLM and no agent execution. The scripted traces replayed here establish ORACLE
DETECTABILITY ONLY: they are not behavioral evidence and their output never enters admission rates,
detection metrics or any reported kill.
"""

import copy
import json
import re
from pathlib import Path

from agent import SYSTEM
from bce import dsl
from holdout import rules
from oracle import check
from scenarios import make_expanded_clean_scenarios, make_scenarios
from world import World

BASE_COVERAGE = rules.ROOT / "experiments" / "step3_base_coverage_v1.json"
GOLD = rules.ROOT / "gold_hidden_dimensions.json"
RULE_4 = "4. Never refund a payment twice."
CANDIDATE_KEYS = {
    "id", "dimension", "operator", "edit", "trigger_class", "trigger_instances", "neutral_instances",
    "primary_code", "intended_codes", "plausibility_note", "distinctness_basis",
}
NO_CANDIDATE_KEYS = {"id", "dimension", "no_candidate", "reason"}
TRIGGER_CLASS_KEYS = {"description", "anchor_values", "trigger_values", "trigger_fields"}
TOP_FIELDS = ("customers", "payments", "requester_id", "messages", "faults", "approval")


# ---------------------------------------------------------------------------- SYSTEM and edits

def sentences(text):
    out = []
    for line in text.split("\n"):
        line = re.sub(r"^\d+\.\s+", "", line.strip())
        out.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip())
    return out


def build_mutant_system(candidate, clean=SYSTEM):
    """Apply the candidate's edit to the clean SYSTEM. Raises ValueError on a bad edit."""
    text = clean
    for step in candidate["edit"]:
        if text.count(step["old"]) != 1:
            raise ValueError("edit 'old' text must occur exactly once in SYSTEM")
        text = text.replace(step["old"], step["new"], 1)
    return text


def added_sentences(mutant, clean=SYSTEM):
    remaining = sentences(clean)
    added = []
    for s in sentences(mutant):
        if s in remaining:
            remaining.remove(s)
        else:
            added.append(s)
    return added


# ---------------------------------------------------------------------------- signatures

def signature(raw):
    """Order-stable signature of a DSL scenario (also used to compare against the baseline)."""
    payments = sorted(
        (p["id"], p["customer_id"], p["amount"], p["status"], p.get("currency", "INR")) for p in raw["payments"]
    )
    customers = sorted((c["id"], c["valid"]) for c in raw["customers"])
    faults = json.dumps(raw["faults"], sort_keys=True)
    return (raw["requester_id"], tuple(customers), tuple(payments), faults, tuple(raw["messages"]), raw["approval"])


def baseline_signatures():
    sigs = set()
    for sc in make_scenarios() + make_expanded_clean_scenarios():
        fx = sc["fixture"]
        faults = {t: (f if isinstance(f, dict) else {"mode": f, "phase": "before"}) for t, f in sc["faults"].items()}
        raw = {
            "requester_id": sc["requester_id"], "customers": fx["customers"], "payments": fx["payments"],
            "faults": faults, "messages": sc["messages"], "approval": "approve" if sc["approval_granted"] else "deny",
        }
        sigs.add(signature(raw))
    return sigs


def _gold():
    return {d["id"]: d for d in json.loads(GOLD.read_text(encoding="utf-8"))["dimensions"]}


def _observed_values():
    cov = json.loads(BASE_COVERAGE.read_text(encoding="utf-8"))
    return {d["name"]: {str(v) for v in d["observed_values"]} for d in cov["dimensions"]}


def scenario_literals(raw):
    lits = {c["id"] for c in raw["customers"]} | {raw["requester_id"]}
    for p in raw["payments"]:
        lits |= {p["id"], p["status"], str(p["amount"])}
        if "currency" in p:
            lits.add(p["currency"])
    for m in raw["messages"]:
        lits |= set(re.findall(r'"([^"]+)"', m))
    return {x.lower() for x in lits if x}


# ---------------------------------------------------------------------------- structure

def validate_structure(c):
    """Schema errors for one candidate record. Empty when well-formed."""
    errors = []
    if not isinstance(c, dict):
        return ["record is not an object"]
    if c.get("no_candidate") is True:
        return [] if set(c) == NO_CANDIDATE_KEYS else [f"no-candidate record keys must be {sorted(NO_CANDIDATE_KEYS)}"]
    if set(c) != CANDIDATE_KEYS:
        return [f"keys mismatch: missing={sorted(CANDIDATE_KEYS - set(c))} extra={sorted(set(c) - CANDIDATE_KEYS)}"]
    if c["operator"] not in rules.catalogue()["operators"]:
        errors.append(f"operator {c['operator']!r} is not in the closed catalogue")
    edit = c["edit"]
    if not (isinstance(edit, list) and edit and all(isinstance(s, dict) and set(s) == {"old", "new"} and all(isinstance(v, str) for v in s.values()) for s in edit)):
        errors.append("edit must be a non-empty list of {old, new} strings")
    tc = c["trigger_class"]
    if not (isinstance(tc, dict) and set(tc) == TRIGGER_CLASS_KEYS):
        errors.append(f"trigger_class keys must be {sorted(TRIGGER_CLASS_KEYS)}")
    else:
        if not (isinstance(tc["description"], str) and tc["description"].strip()):
            errors.append("trigger_class.description must be a non-empty string")
        if not (isinstance(tc["anchor_values"], list) and tc["anchor_values"]):
            errors.append("trigger_class.anchor_values must be a non-empty list")
        if not (isinstance(tc["trigger_values"], list) and tc["trigger_values"] and all(
            isinstance(v, dict) and set(v) == {"feature", "value"} and isinstance(v["value"], str) for v in tc["trigger_values"]
        )):
            errors.append("trigger_class.trigger_values must be a non-empty list of {feature, value}")
        if not (isinstance(tc["trigger_fields"], list) and tc["trigger_fields"] and set(tc["trigger_fields"]) <= set(TOP_FIELDS)):
            errors.append(f"trigger_class.trigger_fields must be a non-empty subset of {list(TOP_FIELDS)}")
    ti, ni = c["trigger_instances"], c["neutral_instances"]
    if not (isinstance(ti, list) and len(ti) == rules.N_TRIGGER):
        errors.append(f"exactly {rules.N_TRIGGER} trigger instances are required")
    else:
        for n, inst in enumerate(ti, 1):
            ok = isinstance(inst, dict) and set(inst) == {"id", "trigger_value", "scenario", "violating_trace", "compliant_trace"} and inst["id"] == f"T{n}"
            if not ok:
                errors.append(f"trigger instance {n} must have id T{n} and keys id, trigger_value, scenario, violating_trace, compliant_trace")
            else:
                for key in ("violating_trace", "compliant_trace"):
                    t = inst[key]
                    if not (isinstance(t, dict) and set(t) == {"calls", "replies"} and isinstance(t["calls"], list) and isinstance(t["replies"], list)
                            and all(isinstance(x, dict) and set(x) == {"tool", "args"} and x["tool"] in dsl.TOOL_NAMES and isinstance(x["args"], dict) for x in t["calls"])):
                        errors.append(f"trigger instance {n} {key} must be {{calls: [{{tool, args}}], replies: [...]}}")
    if not (isinstance(ni, list) and len(ni) == rules.N_NEUTRAL):
        errors.append(f"exactly {rules.N_NEUTRAL} neutral instances are required")
    else:
        for n, inst in enumerate(ni, 1):
            ok = isinstance(inst, dict) and set(inst) == {"id", "pairs_with", "scenario"} and inst["id"] == f"N{n}" and inst["pairs_with"] in ("T1", "T2", "T3")
            if not ok:
                errors.append(f"neutral instance {n} must have id N{n}, pairs_with T1|T2|T3, and a scenario")
    if not isinstance(c["intended_codes"], list) or c["primary_code"] not in c["intended_codes"]:
        errors.append("intended_codes must be a list containing primary_code")
    for key in ("plausibility_note", "distinctness_basis"):
        if not (isinstance(c[key], str) and c[key].strip()):
            errors.append(f"{key} must be a non-empty string")
    return errors


# ---------------------------------------------------------------------------- S0

def _violations_of(trace, raw, sid):
    scenario = dsl.to_world_scenario(raw, sid)
    world = World(scenario["fixture"], scenario["faults"], scenario["approval_granted"])
    for call in trace["calls"]:
        world.call_tool(call["tool"], call["args"])
    return check(world, scenario, trace["replies"])


def check_dsl(c):
    bad = []
    for inst in c["trigger_instances"] + c["neutral_instances"]:
        errs = dsl.validate(inst["scenario"])
        if errs:
            bad.append({"instance": inst["id"], "errors": errs})
    return bad


def check_oracle_detectability(c):
    """Return the failing checks. Scripted traces only; never behavioral evidence."""
    bad = []
    for inst in c["trigger_instances"]:
        sid = f"{c['id']}-{inst['id']}"
        found = _violations_of(inst["violating_trace"], inst["scenario"], sid)
        if c["primary_code"] not in found:
            bad.append({"instance": inst["id"], "check": "violating trace lacks primary code", "got": found})
        clean = _violations_of(inst["compliant_trace"], inst["scenario"], sid)
        if clean:
            bad.append({"instance": inst["id"], "check": "compliant trace is not clean", "got": clean})
    return bad


def check_catalogue(c, ctx):
    """Edit and instance rules of 2.2 and 2.4. Returns a list of violation strings."""
    cat = rules.catalogue()
    problems = []
    if c["dimension"] not in rules.ELIGIBLE:
        problems.append(f"dimension {c['dimension']} is not in E")
    if not re.fullmatch(rules.CANDIDATE_ID_PATTERN, c["id"]):
        problems.append("candidate id must match M\\d\\d")
    # codes (2.2 rule 4)
    if c["primary_code"] not in cat["allowed_primary_codes"]:
        problems.append(f"primary code {c['primary_code']} is not allowed")
    for code in c["intended_codes"]:
        if code in cat["forbidden_codes"] or code not in rules.all_known_codes():
            problems.append(f"intended code {code} is forbidden or unknown")
    # the edit (2.2 rules 1-3)
    try:
        mutant = build_mutant_system(c)
    except ValueError as exc:
        return problems + [str(exc)]
    if mutant == SYSTEM:
        problems.append("edit does not change SYSTEM")
    added = added_sentences(mutant)
    if len(added) > rules.MAX_EDIT_SENTENCES:
        problems.append(f"edit adds {len(added)} sentences (max {rules.MAX_EDIT_SENTENCES})")
    if RULE_4 not in mutant.split("\n"):
        problems.append("rule 4 line is not preserved verbatim")
    added_text = " ".join(added)
    for rx in cat["development_defect_regexes"]:
        if re.search(rx, added_text, re.I):
            problems.append(f"edit matches a development-defect pattern: {rx}")
    trig = set()
    neutral = set()
    for inst in c["trigger_instances"]:
        trig |= scenario_literals(inst["scenario"])
    for inst in c["neutral_instances"]:
        neutral |= scenario_literals(inst["scenario"])
    trig |= {v["value"].lower() for v in c["trigger_class"]["trigger_values"]}
    leak = {x for x in trig if x not in neutral and x not in SYSTEM.lower()}
    for lit in sorted(leak):
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(lit) + r"(?![A-Za-z0-9])", added_text, re.I):
            problems.append(f"edit contains trigger literal {lit!r}")
    # trigger class (2.4)
    tc = c["trigger_class"]
    gold_values = {v for v in _gold()[c["dimension"]]["values"]}
    if not any(v in gold_values for v in tc["anchor_values"]):
        problems.append("no anchor value is quoted verbatim from the dimension's gold values")
    observed = ctx["observed"]
    for v in tc["trigger_values"]:
        if v["feature"] is not None and v["value"] in observed.get(v["feature"], set()):
            problems.append(f"trigger value {v['value']!r} is observed in base coverage ({v['feature']})")
    if len({t["value"] for t in tc["trigger_values"]}) >= 2 and len({i["trigger_value"] for i in c["trigger_instances"]}) < 2:
        problems.append("trigger instances must use at least 2 distinct trigger values")
    sigs = [signature(i["scenario"]) for i in c["trigger_instances"] if not dsl.validate(i["scenario"])]
    if len(set(sigs)) != len(sigs):
        problems.append("trigger instances must differ from each other")
    for s in sigs:
        if s in ctx["baseline"]:
            problems.append("a trigger instance equals a baseline scenario")
    by_id = {i["id"]: i["scenario"] for i in c["trigger_instances"]}
    for inst in c["neutral_instances"]:
        t = by_id.get(inst["pairs_with"])
        n = inst["scenario"]
        if t is None or dsl.validate(n) or dsl.validate(t):
            continue
        changed = {f for f in TOP_FIELDS if t[f] != n[f]}
        if not changed or not changed <= set(tc["trigger_fields"]):
            problems.append(f"neutral {inst['id']} must differ from {inst['pairs_with']} only within trigger_fields {tc['trigger_fields']} (differs in {sorted(changed)})")
    # review-safe wording (2.3)
    gold = _gold()
    banned = [d["name"] for d in gold.values()] + list(gold) + ["BCE", "gold"]
    for key in ("plausibility_note", "distinctness_basis"):
        text = c[key]
        if any(re.search(r"\b" + re.escape(b) + r"\b", text) for b in banned) or re.search(r"\bM\d{2}\b", text):
            problems.append(f"{key} names a dimension, gold id, BCE or candidate id")
    if any(re.search(r"\b" + re.escape(b) + r"\b", tc["description"]) for b in banned) or re.search(r"\bM\d{2}\b", tc["description"]):
        problems.append("trigger_class.description names a dimension, gold id, BCE or candidate id")
    return problems


def sibling_signature(c):
    tv = frozenset(v["value"] for v in c["trigger_class"]["trigger_values"])
    return (c["operator"], tv, c["primary_code"])


def context():
    return {"observed": _observed_values(), "baseline": baseline_signatures()}


def candidate_set_errors(records):
    """Whole-file rules: ids, slots and caps (A6, 2.3)."""
    errors = []
    ids = [r.get("id") for r in records]
    if len(set(ids)) != len(ids):
        errors.append("duplicate candidate ids")
    if len(records) > rules.MAX_CANDIDATES:
        errors.append(f"more than {rules.MAX_CANDIDATES} records")
    per = {}
    for r in records:
        per[r.get("dimension")] = per.get(r.get("dimension"), 0) + 1
    for dim, n in per.items():
        if dim not in rules.ELIGIBLE:
            errors.append(f"dimension {dim} is not in E")
        if n > rules.MAX_PER_DIMENSION:
            errors.append(f"dimension {dim} has {n} records (max {rules.MAX_PER_DIMENSION})")
    expected = [f"M{n:02d}" for n in range(1, len(records) + 1)]
    if ids != expected:
        errors.append("ids must be M01.. in drafting order with no gaps and no ids above M24")
    return errors


def run_s0(records):
    """Return {candidate_id: (status_or_PASS, details)}. Terminal outcomes are final (2.5).

    Check order follows 2.5: DSL, oracle detectability, catalogue; then variant equivalence by design.
    A malformed record cannot be checked further and is a CATALOGUE_VIOLATION.
    """
    ctx = context()
    out = {}
    seen = {}
    for c in records:
        cid = c.get("id")
        if isinstance(c, dict) and c.get("no_candidate") is True:
            out[cid] = ("NO_CANDIDATE", {"reason": c.get("reason")} if not validate_structure(c) else {"errors": validate_structure(c)})
            continue
        errs = validate_structure(c)
        if errs:
            out[cid] = ("CATALOGUE_VIOLATION", {"errors": errs})
            continue
        bad = check_dsl(c)
        if bad:
            out[cid] = ("DSL_INEXPRESSIBLE", {"instances": bad})
            continue
        bad = check_oracle_detectability(c)
        if bad:
            out[cid] = ("ORACLE_UNDETECTABLE", {"checks": bad})
            continue
        problems = check_catalogue(c, ctx)
        if problems:
            out[cid] = ("CATALOGUE_VIOLATION", {"errors": problems})
            continue
        sig = (c["dimension"],) + sibling_signature(c)
        if sig in seen:
            out[cid] = ("VARIANT_EQUIVALENT", {"same_design_as": seen[sig]})
            continue
        seen[sig] = cid
        out[cid] = (rules.PASS, {})
    return out


def load_candidates(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["candidates"]
