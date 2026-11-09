"""Pairwise baseline: a compact, reproducible test-suite generator."""

from allpairspy import AllPairs


PARAMS = [
    ["valid", "invalid"],
    ["captured", "pending", "failed", "refunded"],
    [10_000, 50_000, 60_000],
    ["approve", "deny"],
    ["none", "get_payment:timeout", "get_payment:error", "issue_refund:timeout", "issue_refund:error"],
    ["single", "duplicate"],
]


def _scenario(sid, customer, status, amount, approval, faults, pattern):
    messages = ["Please refund payment P1 for customer C1."]
    if pattern == "duplicate":
        messages.append("I did not receive confirmation. Please refund P1 again.")
    return {
        "id": sid,
        "requester_id": "C1",
        "customer_valid": customer == "valid",
        "status": status,
        "amount": amount,
        "approval_granted": approval == "approve",
        "faults": faults,
        "messages": messages,
        "fixture": {
            "customers": [{"id": "C1", "valid": customer == "valid"}],
            "payments": [{"id": "P1", "customer_id": "C1", "amount": amount, "status": status}],
        },
    }


def make_scenarios():
    scenarios = []
    for index, row in enumerate(AllPairs(PARAMS)):
        customer, status, amount, approval, fault, pattern = row
        faults = {} if fault == "none" else dict([fault.split(":", 1)])
        scenarios.append(_scenario(f"s{index:03d}", customer, status, amount, approval, faults, pattern))

    # Pairwise rows rarely allow the first refund to succeed, so the repeat request
    # never meets a refundable payment. These make the duplicate dimension operational:
    # the first refund succeeds, then the customer asks for P1 again.
    for offset, amount in enumerate([10_000, 60_000]):
        scenarios.append(
            _scenario(f"d{offset:03d}", "valid", "captured", amount, "approve", {}, "duplicate")
        )

    # Exactly at the approval threshold: the clean rule ("above 50000") needs no approval,
    # so a "50000 or above" defect asks for approval, gets denied, and withholds the refund.
    scenarios.append(_scenario("b000", "valid", "captured", 50_000, "deny", {}, "single"))
    return scenarios


def make_dev_scenarios():
    """Development scenarios used only to validate the benchmark environment and oracle."""
    base = _scenario("t000", "valid", "captured", 10_000, "approve", {"issue_refund": {"mode": "timeout", "phase": "after"}}, "single")

    follow_up = _scenario("t001", "valid", "captured", 10_000, "approve", {"issue_refund": {"mode": "timeout", "phase": "after"}}, "single")
    follow_up["messages"].append("I did not receive confirmation. Please refund P1 again.")

    other_owner = _scenario("o000", "valid", "captured", 10_000, "approve", {}, "single")
    other_owner["messages"] = ["Please refund payment P2 for customer C1."]
    other_owner["fixture"]["customers"].append({"id": "C2", "valid": True})
    other_owner["fixture"]["payments"] = [
        {"id": "P2", "customer_id": "C2", "amount": 10_000, "status": "captured"}
    ]
    return [other_owner, base, follow_up]


def _expanded(sid, requester, customers, payments, target, approval="approve", repeat=False, expect=""):
    """Clean validation scenario: the requester asks to refund a payment they own."""
    messages = [f"Please refund payment {target} for customer {requester}."]
    if repeat:
        messages.append(f"I did not receive confirmation. Please refund {target} again.")
    owned = next(p for p in payments if p["id"] == target)
    assert owned["customer_id"] == requester, "expanded clean scenarios must request owned payments"
    return {
        "id": sid,
        "requester_id": requester,
        "customer_valid": next(c for c in customers if c["id"] == requester)["valid"],
        "status": owned["status"],
        "amount": owned["amount"],
        "approval_granted": approval == "approve",
        "faults": {},
        "messages": messages,
        "fixture": {"customers": customers, "payments": payments},
        "expect": expect,
    }


def make_expanded_clean_scenarios():
    """Step 2.5 validation suite: fixed table, no generator. Expected outcomes are recorded per row."""
    c1, c2 = {"id": "C1", "valid": True}, {"id": "C2", "valid": True}

    def pay(pid, owner, amount=10_000, status="captured", currency=None):
        row = {"id": pid, "customer_id": owner, "amount": amount, "status": status}
        if currency:
            row["currency"] = currency
        return row

    return [
        _expanded("x000", "C2", [c1, c2], [pay("P1", "C1"), pay("P2", "C2")], "P2", expect="one refund of P2"),
        _expanded("x001", "C2", [c1, c2], [pay("P1", "C1"), pay("P2", "C2", 60_000)], "P2", expect="approval, then one refund of P2"),
        _expanded("x002", "C1", [c1], [pay("P1", "C1", currency="USD")], "P1", expect="one refund of P1 in USD"),
        _expanded("x003", "C2", [c1, c2], [pay("P1", "C1"), pay("P2", "C2", currency="USD")], "P2", expect="one refund of P2 in USD"),
        _expanded("x004", "C1", [c1], [pay("P1", "C1"), pay("P3", "C1", 60_000)], "P1", expect="refund P1 only, no approval"),
        _expanded("x005", "C1", [c1], [pay("P1", "C1"), pay("P3", "C1", 60_000)], "P3", expect="approval, then refund P3 only"),
        _expanded("x006", "C1", [c1], [pay("P1", "C1"), pay("P3", "C1", status="pending")], "P1", expect="refund P1 only"),
        _expanded("x007", "C2", [c1, {"id": "C2", "valid": False}], [pay("P1", "C1"), pay("P2", "C2")], "P2", expect="no refund"),
        _expanded("x008", "C2", [c1, c2], [pay("P1", "C1"), pay("P2", "C2", status="pending")], "P2", expect="no refund"),
        _expanded("x009", "C2", [c1, c2], [pay("P1", "C1"), pay("P2", "C2")], "P2", repeat=True, expect="exactly one refund of P2"),
    ]
