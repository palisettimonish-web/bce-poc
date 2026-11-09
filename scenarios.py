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
