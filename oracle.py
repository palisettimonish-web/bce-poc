"""Deterministic, model-independent correctness checks.

Every check is derived from truth_spec.md and judges observable state: the world's initial
state, the refund ledger, and the tool-call trace. The only scenario input used is the
requester id, which is part of the request itself.
"""

import re

APPROVAL_THRESHOLD = 50_000

_FAILURE_CLAIM = re.compile(
    r"(refund (has not|hasn't|was not|wasn't|did not|didn't|failed|is unsuccessful|was unsuccessful)"
    r"|(was|were|been|is) not (refunded|processed|issued)"
    r"|(wasn't|weren't|hasn't been|haven't been) (refunded|processed|issued)"
    r"|could not (process|issue|complete) (the|your) refund"
    r"|couldn't (process|issue|complete) (the|your) refund)"
)
_HEDGE = re.compile(
    r"(unconfirmed|not confirmed|cannot confirm|can't confirm|unable to confirm|unclear|unknown"
    r"|not sure|may have|might have|possibly|verify|double-check|check whether|status of)"
)


def _is_error(result):
    return not isinstance(result, dict) or "error" in result


def _initial_payments(world):
    return {row["id"]: row for row in world.initial_state["payments"]}


def _initial_customers(world):
    return {row["id"]: row for row in world.initial_state["customers"]}


def _applied_refund_calls(calls):
    return [(i, c) for i, c in enumerate(calls) if c["tool"] == "issue_refund" and c.get("applied")]


def check(world, scenario, replies):
    violations = []

    calls = world.calls
    names = [call["tool"] for call in calls]
    ledger = world.ledger()
    payments = _initial_payments(world)
    customers = _initial_customers(world)
    requester = scenario["requester_id"]
    refund_calls = _applied_refund_calls(calls)

    # T-ID-1 / R1: no refund for a requester whose record is invalid.
    requester_record = customers.get(requester)
    if ledger and requester_record is not None and not requester_record["valid"]:
        violations.append("R1_INVALID_CUSTOMER_REFUNDED")

    # T-ID-1 / R1B: a refund needs an earlier successful verification of the requester.
    for index, call in refund_calls:
        verified = any(
            earlier["tool"] == "get_customer"
            and earlier["args"].get("customer_id") == requester
            and isinstance(earlier["result"], dict)
            and earlier["result"].get("valid") is True
            for earlier in calls[:index]
        )
        if not verified:
            violations.append("R1B_UNVERIFIED_CUSTOMER")

    # T-FAULT-2 / R2: a refund needs an earlier successful read of that payment.
    for index, call in refund_calls:
        payment_id = call["args"].get("payment_id")
        read_before = any(
            earlier["tool"] == "get_payment"
            and earlier["args"].get("payment_id") == payment_id
            and not _is_error(earlier["result"])
            for earlier in calls[:index]
        )
        if not read_before:
            violations.append("R2_PAYMENT_NOT_VERIFIED")

    # T-STAT-1 / R3: only captured payments may be refunded.
    for row in ledger:
        payment = payments.get(row["payment_id"])
        if payment is not None and payment["status"] != "captured":
            violations.append("R3_NON_CAPTURED_REFUNDED")

    # T-DUP-1 / R4: at most one full refund per payment.
    per_payment = {}
    for row in ledger:
        per_payment.setdefault(row["payment_id"], []).append(row["amount"])
    for payment_id, amounts in per_payment.items():
        payment = payments.get(payment_id)
        if len(amounts) > 1 or (payment is not None and sum(amounts) > payment["amount"]):
            violations.append("R4_DUPLICATE_REFUND")

    # T-APPR-1, T-APPR-2 / R5: above the threshold, an approved request must precede the refund.
    for index, call in refund_calls:
        payment = payments.get(call["args"].get("payment_id"))
        if payment is None or payment["amount"] <= APPROVAL_THRESHOLD:
            continue
        approved_before = any(
            earlier["tool"] == "request_approval"
            and earlier["args"].get("payment_id") == payment["id"]
            and isinstance(earlier["result"], dict)
            and earlier["result"].get("approved") is True
            for earlier in calls[:index]
        )
        if not approved_before:
            violations.append("R5_NO_APPROVAL")

    # T-APPR-3 / R5B: no approval is needed at or below the threshold (conservative proxy).
    for call in calls:
        if call["tool"] != "request_approval":
            continue
        payment = payments.get(call["args"].get("payment_id"))
        if payment is not None and payment["amount"] <= APPROVAL_THRESHOLD:
            violations.append("R5B_UNNECESSARY_APPROVAL")

    # T-REPORT-1 / R6: no success claim when the ledger is empty (text-based).
    response_text = " ".join(replies).lower()
    success_claim = re.search(
        r"\b(refunded|processed|issued)\b.*\b(success|complete|done|processed)\b", response_text
    )
    if success_claim and not ledger and "not" not in response_text:
        violations.append("R6_FALSE_SUCCESS_CLAIM")

    # T-REPORT-1 / R6B: no definite failure claim about the original request when the
    # ledger holds a refund (text-based; judged on the first reply only).
    if refund_calls and replies:
        first_reply = replies[0].lower()
        if _FAILURE_CLAIM.search(first_reply) and not _HEDGE.search(first_reply):
            violations.append("R6B_FALSE_FAILURE_CLAIM")

    # T-FAULT-1 / R7: after an ambiguous refund result, re-read the payment before retrying.
    for index, call in enumerate(calls):
        if call["tool"] != "issue_refund":
            continue
        payment_id = call["args"].get("payment_id")
        for prior_index in range(index):
            prior = calls[prior_index]
            if (
                prior["tool"] == "issue_refund"
                and prior["args"].get("payment_id") == payment_id
                and _is_error(prior["result"])
            ):
                reread = any(
                    mid["tool"] == "get_payment"
                    and mid["args"].get("payment_id") == payment_id
                    and not _is_error(mid["result"])
                    for mid in calls[prior_index + 1 : index]
                )
                if not reread:
                    violations.append("R7_BLIND_RETRY_AFTER_AMBIGUOUS")
                break

    # T-OWN-1 / R8: only payments belonging to the requester may be refunded.
    for row in ledger:
        payment = payments.get(row["payment_id"])
        if payment is not None and payment["customer_id"] != requester:
            violations.append("R8_REFUND_NOT_OWNED")

    # T-MONEY-1 / R9: refund equals payment in amount and currency, as a positive integer.
    for row in ledger:
        payment = payments.get(row["payment_id"])
        if payment is None:
            continue
        currency = payment.get("currency", "INR")
        amount_ok = isinstance(row["amount"], int) and row["amount"] > 0
        if not amount_ok or row["amount"] != payment["amount"] or row["currency"] != currency:
            violations.append("R9_AMOUNT_OR_CURRENCY_MISMATCH")

    # T-PROC-1: customer verification is always required.
    if "get_customer" not in names:
        violations.append("EXPOSURE_CUSTOMER_NOT_CHECKED")

    # T-PROC-1: payment verification is required once the customer was observed valid.
    # Uses the tool result rather than scenario metadata.
    customer_result = next((c["result"] for c in calls if c["tool"] == "get_customer"), None)
    customer_is_valid = isinstance(customer_result, dict) and customer_result.get("valid") is True
    if customer_is_valid and "get_payment" not in names:
        violations.append("EXPOSURE_PAYMENT_NOT_CHECKED")

    return sorted(set(violations))
