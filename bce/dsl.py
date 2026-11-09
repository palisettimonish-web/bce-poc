"""Scenario DSL shared by every arm: schema text, validation, and conversion to a World scenario.

Invalid scenarios are reported with reasons and are never repaired.
"""

import re

TOOL_NAMES = ("get_customer", "get_payment", "issue_refund", "request_approval")
FAULT_MODES = ("timeout", "error", "malformed")
FAULT_PHASES = ("before", "after")
LIMITS = {"customers": 4, "payments": 4, "messages": 4, "text": 400}

DSL_DESCRIPTION = """Each scenario is one JSON object with exactly these keys:
- "candidate_id": string or null (the candidate this scenario targets).
- "customers": array of 1-4 objects {"id": string, "valid": boolean}.
- "payments": array of 1-4 objects {"id": string, "customer_id": string (must be one of the customers), "amount": integer, "status": string, "currency": string (optional, default "INR")}.
- "requester_id": string, the customer id the requester claims to be. It may be any string, including one not listed in "customers".
- "messages": array of 1-4 strings, the user's messages sent in order, one conversation turn each.
- "faults": object mapping a tool name to {"mode": "timeout" | "error" | "malformed", "phase": "before" | "after"}. "before" means the call is lost without effect; "after" means the call takes effect but its response is lost. Tool names: get_customer, get_payment, issue_refund, request_approval. Use {} for no faults.
- "approval": "approve" or "deny", how the human approver answers a request_approval call.
- "expected_distinction": string, the behavioral difference this scenario is meant to expose."""


def validate(raw):
    """Return a list of reasons the scenario is invalid; empty when valid."""
    errors = []
    if not isinstance(raw, dict):
        return ["not an object"]
    keys = {"candidate_id", "customers", "payments", "requester_id", "messages", "faults", "approval", "expected_distinction"}
    if set(raw) != keys:
        errors.append(f"keys mismatch: missing={sorted(keys - set(raw))} extra={sorted(set(raw) - keys)}")
        return errors
    if raw["candidate_id"] is not None and not isinstance(raw["candidate_id"], str):
        errors.append("candidate_id must be string or null")
    customers = raw["customers"]
    ids = set()
    if not isinstance(customers, list) or not 1 <= len(customers) <= LIMITS["customers"]:
        errors.append("customers must be a list of 1-4")
    else:
        for c in customers:
            if not (isinstance(c, dict) and set(c) == {"id", "valid"} and isinstance(c["id"], str) and c["id"] and isinstance(c["valid"], bool)):
                errors.append("bad customer entry")
            else:
                ids.add(c["id"])
        if len(ids) != len(customers):
            errors.append("duplicate customer ids")
    payments = raw["payments"]
    if not isinstance(payments, list) or not 1 <= len(payments) <= LIMITS["payments"]:
        errors.append("payments must be a list of 1-4")
    else:
        pids = set()
        for p in payments:
            allowed = {"id", "customer_id", "amount", "status", "currency"}
            ok = isinstance(p, dict) and {"id", "customer_id", "amount", "status"} <= set(p) <= allowed
            if not ok:
                errors.append("bad payment entry")
                continue
            if not (isinstance(p["id"], str) and p["id"] and isinstance(p["status"], str) and p["status"]):
                errors.append("payment id/status must be non-empty strings")
            if not isinstance(p["amount"], int) or isinstance(p["amount"], bool):
                errors.append("payment amount must be an integer")
            if p["customer_id"] not in ids:
                errors.append("payment customer_id not in customers")
            if "currency" in p and not (isinstance(p["currency"], str) and re.fullmatch(r"[A-Z]{3}", p["currency"])):
                errors.append("currency must be a 3-letter uppercase code")
            pids.add(p["id"])
        if len(pids) != len(payments):
            errors.append("duplicate payment ids")
    if not isinstance(raw["requester_id"], str) or not raw["requester_id"] or len(raw["requester_id"]) > 100:
        errors.append("requester_id must be a non-empty string of at most 100 chars")
    messages = raw["messages"]
    if not isinstance(messages, list) or not 1 <= len(messages) <= LIMITS["messages"] or not all(
        isinstance(m, str) and m.strip() and len(m) <= LIMITS["text"] for m in messages
    ):
        errors.append("messages must be 1-4 non-empty strings of at most 400 chars")
    faults = raw["faults"]
    if not isinstance(faults, dict):
        errors.append("faults must be an object")
    else:
        for tool, f in faults.items():
            if tool not in TOOL_NAMES:
                errors.append(f"unknown fault tool {tool}")
            elif not (isinstance(f, dict) and set(f) == {"mode", "phase"} and f["mode"] in FAULT_MODES and f["phase"] in FAULT_PHASES):
                errors.append(f"bad fault for {tool}")
    if raw["approval"] not in ("approve", "deny"):
        errors.append("approval must be approve or deny")
    if not isinstance(raw["expected_distinction"], str) or not raw["expected_distinction"].strip():
        errors.append("expected_distinction must be a non-empty string")
    return errors


def to_world_scenario(raw, sid):
    """Convert a valid DSL scenario to the dict shape run_agent/World/oracle consume."""
    assert not validate(raw), "convert only valid scenarios"
    target = raw["payments"][0]
    by_id = {c["id"]: c for c in raw["customers"]}
    return {
        "id": sid,
        "requester_id": raw["requester_id"],
        "customer_valid": by_id.get(raw["requester_id"], {"valid": False})["valid"],
        "status": target["status"],
        "amount": target["amount"],
        "approval_granted": raw["approval"] == "approve",
        "faults": raw["faults"],
        "messages": raw["messages"],
        "fixture": {"customers": raw["customers"], "payments": raw["payments"]},
    }
