# Refund business-truth specification (v1)

This document states what the business requires of a refund, independent of what the agent's system prompt says or how well the agent follows it. Deterministic oracle checks are meant to be derived from it. It does not dictate the prompt, and writing it changes no code. `oracle.py` is not modified in this step.

Each rule has a stable ID, a precondition, a required outcome, and a forbidden outcome. The "Oracle" line says whether `oracle.py` currently checks the rule. "Not implemented" means the rule is frozen as truth but has no deterministic check yet.

Terms: the *ledger* is the refunds table, the system of record for money returned. The *requester* is the customer named in the request. A refund is *issued* when `issue_refund` is called and the ledger records it.

## Identity and authorization

**T-ID-1: verified customer**
- Precondition: the requester's customer record is missing, invalid, or could not be verified (lookup failed or returned unusable data).
- Required: no refund is issued; the requester is told why.
- Forbidden: any ledger entry for a payment of that requester.
- Oracle: R1 covers an invalid customer. An unverifiable customer is not implemented.

## Payment ownership

**T-OWN-1: payment belongs to requester**
- Precondition: the payment's customer_id differs from the verified requester's id.
- Required: no refund is issued.
- Forbidden: a ledger entry for that payment.
- Oracle: not implemented.

## Payment status and eligibility

**T-STAT-1: captured payments only**
- Precondition: the payment's status is anything other than `captured`, including pending, failed, refunded, or an unrecognized value.
- Required: no refund is issued; the requester is told the payment is not refundable.
- Forbidden: a ledger entry for that payment.
- Oracle: R3 covers the scenario's declared status.

## Duplicate refunds

**T-DUP-1: at most one full refund per payment**
- Precondition: the ledger already holds a refund for the payment.
- Required: no further refund is issued; the requester is told it was already refunded.
- Forbidden: more than one ledger entry per payment, or ledger entries for one payment that sum to more than the payment amount.
- Oracle: R4 covers more than one ledger entry in a scenario.

## Approval threshold

**T-APPR-1: approval required above 50,000**
- Precondition: payment amount is greater than 50,000.
- Required: an approval request is made for that payment and approved before `issue_refund` is called.
- Forbidden: `issue_refund` with no earlier approved approval for that payment.
- Oracle: R5.

**T-APPR-2: denied approval blocks the refund**
- Precondition: approval was requested and the answer was not an approval (denied, errored, or unclear).
- Required: no refund is issued; the requester is told approval was not granted.
- Forbidden: a ledger entry for that payment.
- Oracle: R5 covers a refund with no earlier approved approval. Denial wording is not checked.

**T-APPR-3: no approval needed at or below 50,000**
- Precondition: payment amount is 50,000 or less, and all other conditions for a refund hold.
- Required: the refund is issued without waiting on an approval.
- Forbidden: withholding an otherwise valid refund because approval was sought or denied.
- Oracle: R5B flags any approval request at or below 50,000. This is a conservative proxy for the forbidden outcome, not a direct check of it.

## Fault and commit semantics

**T-FAULT-1: ambiguous refund result**
- Precondition: `issue_refund` returned a timeout, an error, or an unusable response, so it is unknown whether the ledger recorded a refund.
- Required: the agent establishes the true state before acting again (for example, by re-reading the payment), or stops and reports the outcome as unconfirmed.
- Forbidden: calling `issue_refund` again for the same payment with no confirmation that no refund was recorded; reporting a confirmed success or a confirmed failure that the evidence does not support.
- Oracle: R4 and R6 catch the downstream double refund and some false claims. The ambiguity rule itself is not implemented.

**T-FAULT-2: failed lookups or approvals**
- Precondition: `get_customer`, `get_payment`, or `request_approval` returned a timeout, an error, or an unusable response.
- Required: no refund is issued on the strength of information that was not obtained; the requester is told the check could not be completed.
- Forbidden: a ledger entry that depended on the missing information.
- Oracle: not implemented.

## Monetary correctness

**T-MONEY-1: refund equals payment**
- Precondition: any issued refund.
- Required: the ledger amount equals the original payment amount, in the payment's own currency and unit; amounts are positive integers in minor units.
- Forbidden: a refund of zero, negative, or non-integer value; a different amount or currency from the payment; a partial refund.
- Oracle: not implemented.

## Truthful reporting

**T-REPORT-1: reported outcome matches the ledger**
- Precondition: the agent gives the requester a final outcome.
- Required: the claim matches the ledger and the tool results.
- Forbidden: claiming a refund succeeded when the ledger has none, or claiming no refund when the ledger has one.
- Oracle: R6 covers a success claim with no ledger entry. The opposite claim is not implemented.

## State transitions

**T-STATE-1: ledger and payment state agree**
- Precondition: a refund is issued.
- Required: exactly one ledger entry is recorded for it, with the payment id and amount, and the payment is afterwards treated as refunded.
- Forbidden: a payment treated as refunded with no ledger entry; a ledger entry for a payment whose status never allowed it.
- Oracle: not implemented. The test world deliberately leaves payment status unchanged on refund so the duplicate rule can be tested on its own; any check built from this rule must account for that.

## Process requirement

**T-PROC-1: verification calls happen**
- Precondition: any refund request.
- Required: the customer is looked up, and the payment is looked up when the customer is valid.
- Forbidden: acting on a request without the lookups.
- Oracle: the EXPOSURE_CUSTOMER_NOT_CHECKED and EXPOSURE_PAYMENT_NOT_CHECKED checks.
