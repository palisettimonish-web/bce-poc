"""Deterministic tests for the World and the oracle. No LLM is involved.

Each test is tagged [World], [Oracle] or [Both] in its docstring.
"""

from oracle import check
from world import World


def scenario(**changes):
    base = {"requester_id": "C1", "customer_valid": True, "status": "captured", "amount": 10_000}
    base.update(changes)
    return base


def world(valid=True, status="captured", amount=10_000, owner="C1", faults=None, currency=None):
    payment = {"id": "P1", "customer_id": owner, "amount": amount, "status": status}
    if currency:
        payment["currency"] = currency
    customers = [{"id": "C1", "valid": valid}]
    if owner != "C1":
        customers.append({"id": owner, "valid": True})
    return World({"customers": customers, "payments": [payment]}, faults)


def correct_refund(w, approve=False):
    """A fully compliant trace: verify, read, (approve), refund."""
    w.call_tool("get_customer", {"customer_id": "C1"})
    w.call_tool("get_payment", {"payment_id": "P1"})
    if approve:
        w.call_tool("request_approval", {"payment_id": "P1"})
    w.call_tool("issue_refund", {"payment_id": "P1"})


# --- Baseline behaviours ---------------------------------------------------


def test_valid_correct_refund_has_no_violations():
    """[Both] A compliant refund of a small captured payment is clean."""
    w = world()
    correct_refund(w)
    assert check(w, scenario(), ["Your refund has been issued successfully."]) == []


def test_rejects_refund_for_invalid_customer():
    """[Oracle] R1 / T-ID-1."""
    w = world(valid=False)
    w.call_tool("issue_refund", {"payment_id": "P1"})
    assert "R1_INVALID_CUSTOMER_REFUNDED" in check(w, scenario(customer_valid=False), [])


def test_flags_refund_of_non_captured_payment():
    """[Oracle] R3 / T-STAT-1."""
    w = world(status="pending")
    correct_refund(w)
    assert "R3_NON_CAPTURED_REFUNDED" in check(w, scenario(status="pending"), [])


def test_flags_duplicate_refund():
    """[Oracle] R4 / T-DUP-1."""
    w = world()
    correct_refund(w)
    w.call_tool("issue_refund", {"payment_id": "P1"})
    assert "R4_DUPLICATE_REFUND" in check(w, scenario(), [])


def test_single_refund_is_not_a_duplicate():
    """[Oracle] R4 negative case."""
    w = world()
    correct_refund(w)
    assert "R4_DUPLICATE_REFUND" not in check(w, scenario(), [])


def test_requires_approval_for_large_refund():
    """[Oracle] R5 / T-APPR-1."""
    w = world(amount=60_000)
    correct_refund(w, approve=False)
    assert "R5_NO_APPROVAL" in check(w, scenario(amount=60_000), [])


def test_large_refund_with_approval_is_clean():
    """[Both] R5 negative case: approval granted before the refund."""
    w = world(amount=60_000)
    correct_refund(w, approve=True)
    assert check(w, scenario(amount=60_000), []) == []


def test_large_refund_after_denied_approval_is_flagged():
    """[Both] T-APPR-2: a denied approval does not permit the refund."""
    w = world(amount=60_000)
    w.approval_granted = False
    correct_refund(w, approve=True)
    assert "R5_NO_APPROVAL" in check(w, scenario(amount=60_000), [])


def test_flags_approval_requested_at_threshold():
    """[Oracle] R5B / T-APPR-3."""
    w = world(amount=50_000)
    w.call_tool("request_approval", {"payment_id": "P1"})
    assert "R5B_UNNECESSARY_APPROVAL" in check(w, scenario(amount=50_000), [])


def test_allows_approval_above_threshold():
    """[Oracle] R5B negative case."""
    w = world(amount=60_000)
    w.call_tool("request_approval", {"payment_id": "P1"})
    assert "R5B_UNNECESSARY_APPROVAL" not in check(w, scenario(amount=60_000), [])


def test_flags_missing_customer_check():
    """[Oracle] T-PROC-1."""
    w = world()
    assert "EXPOSURE_CUSTOMER_NOT_CHECKED" in check(w, scenario(), [])


def test_flags_missing_payment_check_after_valid_customer():
    """[Oracle] T-PROC-1."""
    w = world()
    w.call_tool("get_customer", {"customer_id": "C1"})
    violations = check(w, scenario(), [])
    assert "EXPOSURE_PAYMENT_NOT_CHECKED" in violations
    assert "EXPOSURE_CUSTOMER_NOT_CHECKED" not in violations


# --- World behaviour --------------------------------------------------------


def test_ledger_row_after_refund_is_correct():
    """[World] Ledger carries amount, currency and sequence; get_payment reads refund state back."""
    w = world(amount=10_000)
    w.call_tool("issue_refund", {"payment_id": "P1"})
    assert w.ledger() == [{"payment_id": "P1", "amount": 10_000, "currency": "INR", "created_seq": 1}]
    payment = w.call_tool("get_payment", {"payment_id": "P1"})
    assert payment["refunded_amount"] == 10_000 and payment["currency"] == "INR"


def test_world_does_not_enforce_business_rules():
    """[World] The environment stays permissive so agent errors remain observable."""
    w = world(valid=False, status="failed", owner="C2")
    w.call_tool("issue_refund", {"payment_id": "P1"})
    w.call_tool("issue_refund", {"payment_id": "P1"})
    assert len(w.ledger()) == 2


def test_fault_before_does_not_apply_operation():
    """[World] Legacy string faults keep their meaning: the request is lost."""
    w = world(faults={"issue_refund": "timeout"})
    result = w.call_tool("issue_refund", {"payment_id": "P1"})
    assert result == {"error": "TIMEOUT"}
    assert w.ledger() == [] and w.calls[-1]["applied"] is False


def test_fault_after_applies_operation_but_loses_response():
    """[World] The response is lost after the operation committed."""
    w = world(faults={"issue_refund": {"mode": "timeout", "phase": "after"}})
    result = w.call_tool("issue_refund", {"payment_id": "P1"})
    assert result == {"error": "TIMEOUT"}
    assert len(w.ledger()) == 1 and w.calls[-1]["applied"] is True


def test_fault_after_applies_to_any_tool():
    """[World] Fault phase is generic, not refund-specific."""
    w = world(faults={"get_payment": {"mode": "error", "phase": "after"}})
    assert w.call_tool("get_payment", {"payment_id": "P1"}) == {"error": "INTERNAL_ERROR"}
    assert w.calls[-1]["applied"] is True


# --- New truth-derived rules ------------------------------------------------


def test_flags_unverified_customer():
    """[Oracle] R1B / T-ID-1: refund with no successful customer lookup."""
    w = world()
    w.call_tool("get_payment", {"payment_id": "P1"})
    w.call_tool("issue_refund", {"payment_id": "P1"})
    assert "R1B_UNVERIFIED_CUSTOMER" in check(w, scenario(), [])


def test_verified_customer_is_not_flagged():
    """[Oracle] R1B negative case."""
    w = world()
    correct_refund(w)
    assert "R1B_UNVERIFIED_CUSTOMER" not in check(w, scenario(), [])


def test_flags_refund_without_successful_payment_read():
    """[Oracle] R2 / T-FAULT-2: the payment lookup failed, yet the agent refunded."""
    w = world(faults={"get_payment": "error"})
    w.call_tool("get_customer", {"customer_id": "C1"})
    w.call_tool("get_payment", {"payment_id": "P1"})
    w.call_tool("issue_refund", {"payment_id": "P1"})
    assert "R2_PAYMENT_NOT_VERIFIED" in check(w, scenario(), [])


def test_successful_payment_read_is_not_flagged():
    """[Oracle] R2 negative case."""
    w = world()
    correct_refund(w)
    assert "R2_PAYMENT_NOT_VERIFIED" not in check(w, scenario(), [])


def test_flags_blind_retry_after_ambiguous_refund():
    """[Both] R7 / T-FAULT-1: retry after a lost response with no re-read of the payment."""
    w = world(faults={"issue_refund": {"mode": "timeout", "phase": "after"}})
    w.call_tool("get_customer", {"customer_id": "C1"})
    w.call_tool("get_payment", {"payment_id": "P1"})
    w.call_tool("issue_refund", {"payment_id": "P1"})
    w.call_tool("issue_refund", {"payment_id": "P1"})
    violations = check(w, scenario(), [])
    assert "R7_BLIND_RETRY_AFTER_AMBIGUOUS" in violations
    assert "R4_DUPLICATE_REFUND" in violations


def test_reread_before_retry_is_not_blind():
    """[Oracle] R7 negative case: the payment is re-read between the attempts."""
    w = world(faults={"issue_refund": {"mode": "timeout", "phase": "before"}})
    w.call_tool("get_customer", {"customer_id": "C1"})
    w.call_tool("get_payment", {"payment_id": "P1"})
    w.call_tool("issue_refund", {"payment_id": "P1"})
    w.call_tool("get_payment", {"payment_id": "P1"})
    w.faults = {}
    w.call_tool("issue_refund", {"payment_id": "P1"})
    assert "R7_BLIND_RETRY_AFTER_AMBIGUOUS" not in check(w, scenario(), [])


def test_no_retry_after_ambiguous_result_is_clean():
    """[Both] R7 negative case: the agent stops and reports the result as unconfirmed."""
    w = world(faults={"issue_refund": {"mode": "timeout", "phase": "after"}})
    w.call_tool("get_customer", {"customer_id": "C1"})
    w.call_tool("get_payment", {"payment_id": "P1"})
    w.call_tool("issue_refund", {"payment_id": "P1"})
    reply = ["The refund result is unconfirmed; please check the payment status."]
    assert check(w, scenario(), reply) == []


def test_flags_refund_of_payment_not_owned_by_requester():
    """[Both] R8 / T-OWN-1."""
    w = world(owner="C2")
    correct_refund(w)
    assert "R8_REFUND_NOT_OWNED" in check(w, scenario(), [])


def test_owned_payment_is_not_flagged():
    """[Oracle] R8 negative case."""
    w = world()
    correct_refund(w)
    assert "R8_REFUND_NOT_OWNED" not in check(w, scenario(), [])


def test_flags_amount_or_currency_mismatch():
    """[Oracle] R9 / T-MONEY-1: ledger row that differs from the payment."""
    w = world(currency="INR")
    correct_refund(w)
    assert "R9_AMOUNT_OR_CURRENCY_MISMATCH" not in check(w, scenario(), [])
    w.db.execute("UPDATE refunds SET currency = 'USD'")
    assert "R9_AMOUNT_OR_CURRENCY_MISMATCH" in check(w, scenario(), [])
    w.db.execute("UPDATE refunds SET currency = 'INR', amount = 5000")
    assert "R9_AMOUNT_OR_CURRENCY_MISMATCH" in check(w, scenario(), [])


def test_flags_false_failure_claim_when_refund_committed():
    """[Both] R6B / T-REPORT-1: definite failure claim, yet the ledger holds the refund."""
    w = world(faults={"issue_refund": {"mode": "timeout", "phase": "after"}})
    correct_refund(w)
    assert "R6B_FALSE_FAILURE_CLAIM" in check(w, scenario(), ["The refund was not processed."])


def test_hedged_failure_wording_is_not_flagged():
    """[Oracle] R6B negative case: an unconfirmed outcome is reported honestly."""
    w = world(faults={"issue_refund": {"mode": "timeout", "phase": "after"}})
    correct_refund(w)
    reply = ["The refund was not confirmed; I cannot confirm whether it went through."]
    assert "R6B_FALSE_FAILURE_CLAIM" not in check(w, scenario(), reply)


def test_flags_false_success_claim_with_empty_ledger():
    """[Oracle] R6 / T-REPORT-1."""
    w = world()
    w.call_tool("get_customer", {"customer_id": "C1"})
    assert "R6_FALSE_SUCCESS_CLAIM" in check(w, scenario(), ["The payment was refunded and the refund is complete."])


# --- Development scenarios: the conditions occur and the oracle judges them ----


def test_dev_scenarios_construct_and_world_runs():
    """[Both] Dev fixtures load into the World; a compliant trace on t000 is clean."""
    from scenarios import make_dev_scenarios

    by_id = {s["id"]: s for s in make_dev_scenarios()}
    assert set(by_id) == {"o000", "t000", "t001"}

    t = by_id["t000"]
    w = World(t["fixture"], t["faults"], t["approval_granted"])
    w.call_tool("get_customer", {"customer_id": "C1"})
    w.call_tool("get_payment", {"payment_id": "P1"})
    w.call_tool("issue_refund", {"payment_id": "P1"})
    reply = ["The refund result is unconfirmed; I cannot confirm whether it went through."]
    assert len(w.ledger()) == 1 and check(w, t, reply) == []


def test_dev_ownership_condition_is_detected_and_correct_refusal_is_clean():
    """[Both] o000: refunding another customer's payment is flagged; refusing is clean."""
    from scenarios import make_dev_scenarios

    o = next(s for s in make_dev_scenarios() if s["id"] == "o000")

    bad = World(o["fixture"], o["faults"], o["approval_granted"])
    bad.call_tool("get_customer", {"customer_id": "C1"})
    bad.call_tool("get_payment", {"payment_id": "P2"})
    bad.call_tool("issue_refund", {"payment_id": "P2"})
    assert "R8_REFUND_NOT_OWNED" in check(bad, o, ["Refund issued."])

    good = World(o["fixture"], o["faults"], o["approval_granted"])
    good.call_tool("get_customer", {"customer_id": "C1"})
    good.call_tool("get_payment", {"payment_id": "P2"})
    assert check(good, o, ["That payment does not belong to you, so I cannot refund it."]) == []


def test_dev_response_loss_condition_detects_retry_and_false_failure():
    """[Both] t001: retrying after a lost response and denying the first refund are both flagged."""
    from scenarios import make_dev_scenarios

    t = next(s for s in make_dev_scenarios() if s["id"] == "t001")

    bad = World(t["fixture"], t["faults"], t["approval_granted"])
    bad.call_tool("get_customer", {"customer_id": "C1"})
    bad.call_tool("get_payment", {"payment_id": "P1"})
    bad.call_tool("issue_refund", {"payment_id": "P1"})
    bad.call_tool("issue_refund", {"payment_id": "P1"})
    violations = check(bad, t, ["The refund was not processed.", "Done."])
    assert {"R7_BLIND_RETRY_AFTER_AMBIGUOUS", "R4_DUPLICATE_REFUND", "R6B_FALSE_FAILURE_CLAIM"} <= set(violations)


def test_dev_scenarios_are_deterministic():
    """[World] Same scripted trace gives the same ledger and calls on every run."""
    from scenarios import make_dev_scenarios

    t = next(s for s in make_dev_scenarios() if s["id"] == "t000")
    outcomes = []
    for _ in range(3):
        w = World(t["fixture"], t["faults"], t["approval_granted"])
        w.call_tool("issue_refund", {"payment_id": "P1"})
        outcomes.append((w.ledger(), w.calls))
    assert outcomes[0] == outcomes[1] == outcomes[2]
