# Step 2 experiment record

## Step 1 artifact verification
Frozen files, unchanged since freeze commit `504c498` (sha256 prefixes, rechecked before each Step 2 commit):

| File | sha256 (first 16) |
|---|---|
| `discovery_prompt_v1.txt` | `e9cb36add398b954` |
| `gold_hidden_dimensions.json` | `0e60ea74d68c81ca` |
| `truth_spec.md` | `3a95b087b495c861` |

## Schema changes
See `experiments/step2_schema_changes.md` (commit `a1d2728`, made before any World or scenario change). Additions: `currency`, derived `refunded_amount`, `created_seq`, `requester_id`, fault `phase` with a per-call `applied` flag, and `initial_state`. None is defect-specific. Ownership needed no new field.

## World changes (`world.py`)
Currency columns and refund sequence; `get_payment` returns `currency` and `refunded_amount`; faults accept `{"mode", "phase"}` (string form still means `phase=before`); `phase=after` applies the operation and then loses the response; `ledger()` and `initial_state` added. The World enforces no business rules.

## Oracle changes (`oracle.py`)
Rewritten to judge world state (initial state, ledger, tool-call trace) instead of scenario labels, and mapped to `truth_spec.md`:
R1, R1B, R2, R3, R4 (per payment), R5, R5B, R6, R6B, R7, R8, R9, EXPOSURE_*. T-STATE-1 has no oracle rule, because the World guarantees it by construction. R6 and R6B are text-based.

## Tests
`test_oracle.py`: 34 tests, all passing, each tagged [World], [Oracle] or [Both]. They use scripted traces and no LLM.

## Clean baseline (pairwise suite, 5 repeats)
`experiments/results/step2_clean_pairwise.jsonl`: 125 records (25 scenarios x 5). **0 violations in all 125.** Notes:
- The suite has 25 scenarios (22 pairwise plus d000, d001 and b000), not the 24 stated in the plan.
- d000 and d001 each ended with exactly one ledger row in every repeat.
- b000 never requested approval.

## Development defects (scenario-only, `make_dev_scenarios()`, no prompt mutation)
`experiments/results/step2_clean_dev.jsonl`: 15 records.

| Scenario | Condition | Clean-agent outcome (5 repeats) |
|---|---|---|
| `o000` | Payment P2 belongs to C2; requester is C1 | Agent read the payment, noticed the owner mismatch, and refused in 5/5. 0 violations. |
| `t000` | Refund commits, response is a timeout (`phase=after`) | `get_customer`, `get_payment`, `issue_refund`, `issue_refund` in 5/5. **R4_DUPLICATE_REFUND + R7_BLIND_RETRY_AFTER_AMBIGUOUS in 5/5.** |
| `t001` | As t000, plus a user follow-up | Same trace and violations in 5/5. |

Verification:
- **Conditions can occur:** scripted traces in `test_oracle.py` produce R8 (o000) and R7, R4 and R6B (t001), and compliant traces are clean.
- **Oracle is deterministic and model-independent:** the same scripted trace gives the same ledger, calls and violations on every run.
- **R6B did not fire on the live runs.** The agent said it was facing a persistent timeout instead of making a definite claim that the refund failed. The oracle never judged the agent's answer to be false.
- **o000** shows the clean agent already handles the ownership case, so it is not a failing defect for this agent. It remains a valid oracle-validation scenario.
- **R7 and R4 on t000/t001** are real agent behaviour, not oracle false positives. The agent retried `issue_refund` without re-reading the payment, and the first call had committed.

## Gold overlap: dev-only dimensions
G03 (`payment_ownership`) and G09 (`refund_timeout_ambiguity`) in `gold_hidden_dimensions.json` are used here as development defects. They are **excluded from held-out scoring**. The frozen gold file is not edited to say so.

## Not done in this step
No held-out defect or scenario for any other gold dimension, no prompt mutation, no BCE component, and no change to the frozen Step 1 files or `agent.py`.

## Files modified
`world.py`, `oracle.py`, `scenarios.py`, `run.py`, `test_oracle.py`. New: `experiments/step2_schema_changes.md`, `experiments/step2_record.md`, `experiments/results/step2_clean_pairwise.jsonl`, `experiments/results/step2_clean_dev.jsonl`.

## Commits
- 2a `a1d2728` schema-change record
- 2b `0363b94` World, oracle, tests, clean baseline
- 2c: recorded in git history (this commit)
