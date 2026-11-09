"""Deterministic tests for the scenario DSL validator and converter."""

import copy

from bce import dsl
from bce.run_discovery import normalize, parse_output
from oracle import check
from world import World


def good():
    return {
        "candidate_id": "c1",
        "customers": [{"id": "C1", "valid": True}],
        "payments": [{"id": "P1", "customer_id": "C1", "amount": 10000, "status": "captured"}],
        "requester_id": "C1",
        "messages": ["Please refund P1."],
        "faults": {},
        "approval": "approve",
        "expected_distinction": "baseline",
    }


def test_valid_scenario_passes_and_converts_to_a_runnable_world():
    s = good()
    assert dsl.validate(s) == []
    ws = dsl.to_world_scenario(s, "g000")
    w = World(ws["fixture"], ws["faults"], ws["approval_granted"])
    w.call_tool("get_customer", {"customer_id": "C1"})
    w.call_tool("get_payment", {"payment_id": "P1"})
    w.call_tool("issue_refund", {"payment_id": "P1"})
    assert check(w, ws, ["Your refund has been issued."]) == []


def test_each_invalid_shape_is_rejected_with_a_reason():
    cases = []
    for mutate in (
        lambda s: s.pop("faults"),
        lambda s: s.update(approval="maybe"),
        lambda s: s.update(messages=[]),
        lambda s: s["payments"][0].update(customer_id="C9"),
        lambda s: s["payments"][0].update(amount="10"),
        lambda s: s["payments"][0].update(amount=True),
        lambda s: s.update(faults={"issue_refund": {"mode": "boom", "phase": "after"}}),
        lambda s: s.update(faults={"delete_all": {"mode": "error", "phase": "after"}}),
        lambda s: s["payments"][0].update(currency="usd"),
        lambda s: s.update(requester_id=""),
    ):
        s = copy.deepcopy(good())
        mutate(s)
        cases.append(dsl.validate(s))
    assert all(errors for errors in cases)
    assert dsl.validate("nope") == ["not an object"]


def test_unknown_requester_is_valid_and_treated_as_invalid_customer():
    s = good()
    s["requester_id"] = "C404"
    assert dsl.validate(s) == []
    assert dsl.to_world_scenario(s, "g001")["customer_valid"] is False


def test_normalize_counts_invalid_scenarios_without_repair():
    bad = good()
    bad["approval"] = "maybe"
    obj = {"candidates": [{"candidate_id": "c1"}], "scenarios": [good(), bad]}
    candidates, scenarios = normalize("C", obj, "C-001-x")
    assert len(candidates) == 1 and [s["valid"] for s in scenarios] == [True, False]
    assert scenarios[1]["scenario"]["approval"] == "maybe"


def test_parse_output_rejects_non_json_and_fenced_json():
    assert parse_output("not json")[0] is None
    assert parse_output("```json\n{}\n```")[0] is None
    assert parse_output('{"scenarios": []}')[0] == {"scenarios": []}
