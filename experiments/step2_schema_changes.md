# Step 2 schema changes

Written and committed before any World change or development scenario exists. Every addition is justified by the general refund/payment domain model. The test applied to each field: *would a production refund/payment system reasonably have this field even if no benchmark had ever been considered?*

## Existing schema (before Step 2)

| Table / structure | Columns / shape |
|---|---|
| `customers` | `id`, `valid` |
| `payments` | `id`, `customer_id`, `amount`, `status` |
| `refunds` | `id` (autoincrement), `payment_id`, `amount` |
| faults | `{tool_name: "timeout" \| "error" \| "malformed"}`; the fault replaces the result before the operation runs |
| call log | `{tool, args, result}` per call |
| scenario | requester is hard-coded as customer `C1` in the request text |

## New schema

| Field | Location | Meaning | Why naturally required by domain | New or existing | Defect-specific? |
|---|---|---|---|---|---|
| `currency` | `payments`, `refunds` | ISO currency code of the money amount | Every payment and refund is denominated in a currency; a refund must be in the payment's currency | New | No |
| `refunded_amount` | Derived from `refunds`; returned by `get_payment` | Total already refunded against the payment | Payment APIs expose an amount-refunded figure so that callers can see refund state | New (derived, not stored) | No |
| `created_seq` | `refunds` | Monotonic logical clock value at creation | Ledger entries are ordered in time; a logical clock keeps runs reproducible without wall-clock time | New | No |
| `requester_id` | Scenario input; named in the request text | The customer on whose behalf the request is made | Every support request has a requester; it was previously hard-coded to `C1` | New (was implicit) | No |
| fault `phase` (`before` / `after`) | Fault configuration; `applied` flag on each call-log entry | Whether a transport fault hit the request (operation not applied) or the response (operation applied, response lost) | Any networked tool call can lose its request or its response; this applies to every tool, not only refunds | New | No |
| `initial_state` | `World` (read-only snapshot of the fixture) | State at the start of the scenario | Lets a judge compare the final state against the starting state without relying on scenario labels | New | No |

Notes:
- Payment ownership is already represented by the existing `payments.customer_id`, so no new field is added for it.
- String fault configs (`"timeout"`, `"error"`, `"malformed"`) keep their old meaning, which is `phase = before`. Existing scenarios behave the same.
- The World continues to enforce no business rules. Judging is the oracle's job.

## Deliberately not added

Idempotency keys, retry persistence or retry counters, partial refunds, multiple currencies inside fixtures, approval timeouts, customer status beyond valid or invalid, and time-based data. None is needed to represent the frozen `truth_spec.md` rules.

## Truth-spec concepts: representable after the change

T-ID-1, T-OWN-1, T-STAT-1, T-DUP-1, T-APPR-1, T-APPR-2, T-APPR-3 (proxy), T-FAULT-1, T-FAULT-2, T-MONEY-1, T-REPORT-1 (partly, text-based), T-PROC-1.

## Truth-spec concepts: still not representable

- T-STATE-1: the World guarantees it by construction, so there is no oracle rule to write.
- T-REPORT-1 failure-claim wording: this depends on free text and is only approximated.
- T-APPR-3 "forbidden: withholding an otherwise valid refund": only approximated by checking that no approval was requested at or below 50,000.
