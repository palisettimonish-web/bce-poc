from oracle import check
from world import World


def scenario(**changes):
    base = {"customer_valid": True, "status": "captured", "amount": 10_000}
    base.update(changes)
    return base


def world(valid=True, status="captured", amount=10_000):
    return World(
        {"customers": [{"id": "C1", "valid": valid}], "payments": [{"id": "P1", "customer_id": "C1", "amount": amount, "status": status}]}
    )


def test_rejects_refund_for_invalid_customer():
    w = world(valid=False)
    w.call_tool("issue_refund", {"payment_id": "P1"})
    assert "R1_INVALID_CUSTOMER_REFUNDED" in check(w, scenario(customer_valid=False), [])


def test_requires_approval_for_large_refund():
    w = world(amount=60_000)
    w.call_tool("issue_refund", {"payment_id": "P1"})
    assert "R5_NO_APPROVAL" in check(w, scenario(amount=60_000), [])


def test_flags_missing_customer_check():
    w = world()
    assert "EXPOSURE_CUSTOMER_NOT_CHECKED" in check(w, scenario(), [])


def test_flags_missing_payment_check_after_valid_customer():
    w = world()
    w.call_tool("get_customer", {"customer_id": "C1"})
    violations = check(w, scenario(), [])
    assert "EXPOSURE_PAYMENT_NOT_CHECKED" in violations
    assert "EXPOSURE_CUSTOMER_NOT_CHECKED" not in violations


def test_flags_approval_requested_at_threshold():
    w = world(amount=50_000)
    w.call_tool("request_approval", {"payment_id": "P1"})
    assert "R5B_UNNECESSARY_APPROVAL" in check(w, scenario(amount=50_000), [])


def test_allows_approval_above_threshold():
    w = world(amount=60_000)
    w.call_tool("request_approval", {"payment_id": "P1"})
    assert "R5B_UNNECESSARY_APPROVAL" not in check(w, scenario(amount=60_000), [])
