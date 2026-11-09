# Step 2.5 record: expanded clean baseline (pre-BCE validation gate)

## Purpose
Check that the expanded World and oracle behave correctly on generic, non-held-out dimensions that the 25-scenario pairwise suite barely exercised. It is a validation gate, not the BCE experiment.

## Frozen artifacts
Unchanged since `504c498` (sha256 prefixes checked before this commit): `discovery_prompt_v1.txt` `e9cb36add398b954`, `gold_hidden_dimensions.json` `0e60ea74d68c81ca`, `truth_spec.md` `3a95b087b495c861`. `agent.py`, `world.py` and `oracle.py` are also unchanged.

## Expanded dimensions (chosen from the World schema and `truth_spec.md` only)
| Dimension | Values | Why generic | Previously covered |
|---|---|---|---|
| Requester identity | C1, C2 (two customers, each owning one payment) | Real systems have many customers | C1 only |
| Requester validity | valid, invalid (non-C1) | T-ID-1 | invalid C1 only |
| Sibling payments | none, or a second payment of the same customer that the request doesn't name | A customer normally has several payments | none |
| Payment currency | INR, USD (at 10,000 only) | The World stores currency; T-MONEY-1 | INR only |

Excluded on purpose: currency at 60,000 (the spec does not say whether the approval threshold depends on currency, which would be an ambiguous case), faults on `get_customer`/`request_approval`, boundary amounts other than those already used, malformed identifiers, and multi-payment requests. The gold file was not read to choose any of this. Currency and the two-customer topology were flagged to the user as only partly aligned with remembered Step 1 content, and were approved.

## Scenario suite (10 scenarios, hand-enumerated; `make_expanded_clean_scenarios()`)
Every scenario requests a payment owned by the requester. No timeout fault, so `t000`/`t001` stay out, and no ownership mismatch, so `o000` stays out. Each row stores its expected outcome in the `expect` field before the run.

| ID | Setup | Expected |
|---|---|---|
| x000 | C2 asks for own P2 (C1/P1 also exist) | one refund of P2 |
| x001 | as x000, 60,000, approval granted | approval, then one refund |
| x002 | C1, USD 10,000 | one refund in USD |
| x003 | C2, USD 10,000 | one refund in USD |
| x004 | C1 has P1 and sibling P3 (60,000); asks for P1 | refund P1 only, no approval |
| x005 | same world; asks for P3, approval granted | approval, then refund P3 only |
| x006 | C1 asks for P1; sibling P3 pending | refund P1 only |
| x007 | C2 invalid asks for own P2 | no refund |
| x008 | C2 asks for own pending P2 | no refund |
| x009 | C2 asks for P2 twice | exactly one refund |

The existing 25-scenario pairwise suite is unchanged.

## Results
`experiments/results/step2_5_clean_expanded.jsonl`: 50 executions (10 scenarios x 5), **0 violations**. Each record has the scenario parameters, tool calls, replies and oracle output.

Outcome check beyond "zero violations": every scenario matched its expectation in all 5 repeats.
- Ledger size was 1 for x000-x006 and x009, and 0 for x007 and x008.
- The correct payment was refunded each time (x004 refunded P1 only, x005 refunded P3 only).
- Approval was requested exactly once in x001 and x005, and never elsewhere.
- Refunds in x002 and x003 were in USD (10 of 10).
- No empty replies and no max-turn replies.

Violations to classify: none.

Tests: 42 passed. The new tests are scripted traces on these topologies: compliant traces are clean, and wrong-sibling, wrong-owner, invalid-requester, pending and duplicate cases are each flagged.

## Decision
**PASS — proceed to Step 3**

## Contamination check
- No gold dimension was used to choose scenarios, and the gold file was not read in this step.
- No held-out defect was implemented.
- No prompt mutation was performed, and `agent.py` is unchanged.
- No BCE component was added.
- The frozen Step 1 files were unchanged.
- Residual risk: the Step 1 content passed through the same session earlier, so the choice of dimensions is not blind to it.

## Files changed
`scenarios.py` (`_expanded`, `make_expanded_clean_scenarios`), `run.py` (`expanded` suite, `scenario_params` in records), `test_oracle.py`. New: this record and the result file.
