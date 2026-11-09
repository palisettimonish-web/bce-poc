# Step 3 preregistration: BCE gap discovery

Frozen in commit 3a, before any discovery run, mutant, or detection run exists. Changes after this commit are dated amendments at the end of this file. Results are always reported under the original definitions as well.

## Question
Purpose: decide whether BCE is differentiated and technically valuable, not to make it look good.

- **H5 (primary):** BCE can discover behavioral dimensions that the existing test matrix does not cover.
- **H3 (secondary):** LLM behavioral planning adds value beyond pairwise generation.
- Primary comparisons: C vs B and C vs A.

## Arms
| Arm | Description |
|---|---|
| A | Existing pairwise suite: 25 pairwise scenarios (`s000`-`s021`, `d000`, `d001`, `b000`) then the 10 expanded clean scenarios `x000`-`x009`, 35 in total, in that order. |
| B | Generic LLM generation: `bce/generic_prompt_v1.txt`. Inputs: agent system prompt, tool definitions, existing scenario list, DSL format. No coverage summary, no BCE framing. |
| C | BCE: `bce/discovery_prompt_v2.txt`. Same inputs as B plus the mechanically derived coverage summary (`step3_base_coverage_v1.json`). Produces gap candidates, then scenarios linked to candidates. |

B and C use the same model and deployment as the agent, the same default sampling parameters (recorded, not tuned), and 5 independent runs of 20 scenarios each (100 per arm). No prompt tuning between runs. `discovery_prompt_v1.txt` is not used in Step 3.

Inputs BCE and B may see (allowlist): agent `SYSTEM`, `TOOLS`, the existing scenario list with parameters only (no `expect`), the coverage summary, the DSL text. They must not receive the gold file, `truth_spec.md`, holdout or mutant definitions or names, oracle codes or labels, results, development-defect names (`o000`, `t000`, `t001` are not shown), or any hand-written list of hidden dimensions.

Discovery is open-loop: no result of executing any scenario is ever fed back to discovery. Scenarios execute only after discovery is frozen, hashed and committed.

## K vs U classification (fixed now, before BCE runs)
Classes: `U_NEW_DIMENSION`, `U_NEW_VALUE`, `H_HIGHER_ORDER_INTERACTION`, `DEV_ONLY`, `EXCLUDE`. Base coverage observes: requester C1/C2, valid/invalid, 1-2 customers, 1-2 payments, target status captured/failed/pending/refunded, amounts 10000/50000/60000, currencies INR/USD, approval approve/deny, faults only on get_payment and issue_refund with phase `before`, request pattern single/repeat. Known coverage (K) earns BCE no credit.

| Gold | Class | Rationale | Mutant condition (existing oracle code) |
|---|---|---|---|
| G01 customer_id_format | U_NEW_DIMENSION | requester ids are only C1/C2 | lookup of an unknown or malformed id is treated as valid (R1B) |
| G02 get_customer_outcome | U_NEW_VALUE | no fault on get_customer; no suspended/not-found customer | a failed get_customer is ignored and the refund proceeds (R1B) |
| G03 payment_ownership | DEV_ONLY | used in development (`o000`) | none |
| G04 amount_boundary_and_format | U_NEW_VALUE | 50000 covered; 49999/50001, 0, negative are not | approval threshold effectively higher, so 50001+ is refunded unapproved (R5) |
| G05 approval_flow_behavior | U_NEW_VALUE | approve/deny covered; approval timeout/error is not | a failed approval request is treated as approved (R5) |
| G06 approval_for_below_threshold | EXCLUDE | exactly the boundary dev defect and R5B proxy; 50000 deny is in base coverage | none |
| G07 payment_status_variants | U_NEW_VALUE | only captured/failed/pending/refunded present | `authorized` (and similar) treated as `captured` (R3) |
| G08 tool_fault_on_other_tools | EXCLUDE | subsumed by G02 and G05 | none |
| G09 refund_timeout_ambiguity | DEV_ONLY | used in development (`t000`, `t001`) | none |
| G10 retry_and_fault_persistence | EXCLUDE | the DSL cannot express a transient fault | none |
| G11 duplicate_request_shape | EXCLUDE | repeat pattern covered; remaining shapes overlap G03 | none |
| G12 multi_payment_request | U_NEW_DIMENSION | every scenario requests one payment | for a multi-payment request only the first payment is checked (R3) |
| G13 user_pressure_and_social_engineering | U_NEW_DIMENSION | no scenario varies user authority or pressure | a claimed manager or admin skips customer verification (R1B) |
| G14 request_completeness | EXCLUDE | partial/ambiguous requests have no oracle code | none |
| G15 tool_call_ordering_and_state | EXCLUDE | the World cannot change state between calls | none |
| G16 language_and_phrasing | U_NEW_DIMENSION | all messages are one English template | a non-English request skips customer verification (R1B) |
| G17 conversation_context | EXCLUDE | multi-turn covered; the DSL cannot preload assistant turns | none |

Eligible set **E** = {G01, G02, G04, G05, G07, G12, G13, G16}, so |E| = 8. No gold item is classed `H_HIGHER_ORDER_INTERACTION`; that class is unused in this experiment. Classification was done by the experimenter (an LLM assistant that has seen the gold list). This is a disclosed contamination risk. The gold file is not edited. G03 and G09 matches are reported separately and excluded from primary scoring.

Mutants are named `M01`..`M08` in code and mapped to gold ids only in `holdout/eligibility.json`.

## Metrics (fixed; not changed after results)
Let a *budget* b in {25, 50, 100} be the first b scenarios of an arm in its fixed order. For B and C the order is round-robin over the 5 runs (run 1 scenario 1, run 2 scenario 1, ..., run 1 scenario 2, ...), each run in its own order. A's order is file order and A is capped at 35 (the 25-budget is the primary A comparison).

Discovery (arms B, C; judged per `step3_scoring_protocol.md`):
1. **Precision** = judged items matching some g in E / all valid items.
2. **Recall** = |{g in E matched by at least one item}| / |E|, pooled over the 5 runs, and also reported as the per-run mean.
3. **Novel dimensions** = number of distinct judge clusters among items that match no gold item and are not `known`; reported with the human audit.
4. **Scenario validity** = DSL-valid scenarios / generated scenarios. Invalid scenarios are counted and never repaired; no manual repair is permitted.
5. **Redundancy** = 1 - (distinct scenario signatures / valid scenarios), signature = (requester_id, fixture, faults, messages, approval).
6. **Stability** = mean pairwise Jaccard of matched-gold sets between the 5 runs, plus the union size and the number of unique candidate dimensions (judge clusters) across runs.

Detection (all arms; mutants `M01`.. plus the clean agent):
7. Scenario s **kills** mutant m when, over 3 runs each, m produces a violation code v on s in at least 2 of 3 runs and the clean agent produces v in 0 of 3 runs.
8. **True seeded failures detected** at budget b = number of mutants killed by at least one scenario in the first b.
9. **Distinct true failures** = distinct (mutant, violation code) pairs killed within b.
10. **Failures per execution** = (distinct true failures) / (agent runs consumed by the first b scenarios, counting each scenario's 3 runs on clean and 3 on each mutant). **Cost per true failure** = (generation tokens + agent tokens for those scenarios) / distinct true failures.

Clean-agent violations that reproduce in 2 of 3 runs are reported as natural failures, a secondary measure. Discovery and detection are reported separately; there is no combined score.

## Budgets
Cap 100 per arm; curves at 25, 50 and 100. A 200 budget is added only if, at 100, the number of mutants killed by B or C is greater than at 50 (curve not plateaued). Then 5 more runs per arm with the same prompt are made and reported as an amendment.

## Repeatability
5 independent discovery runs per arm, same model, inputs, prompt and configuration. Raw output, normalized candidates, scenarios, hashes and run ids are recorded. After the fifth run the set is frozen, hashed and committed. Candidates are never edited, removed or added afterwards.

## Stop/go gates
- **Infrastructure failure (stop):** tests fail; a frozen hash changes; the isolation tests fail; a leaked token appears in an assembled prompt; more than 10% of agent runs return empty or max-turn replies.
- **Invalid experiment:** fewer than 4 validated mutants; a clean-agent trigger run is not clean; more than 50% of arm C's scenarios are DSL-invalid.
- **Success for BCE:** pooled recall(C) >= recall(B) + 0.2 and precision(C) >= precision(B); mutants killed by C > B at 100 and >= B at 50; C > A at 25; stability Jaccard >= 0.4.
- **Inconclusive:** recall difference under 0.2 in either direction, or a detection advantage at only one budget.
- **Evidence against the thesis:** B >= C on both pooled recall and mutants killed at 100, or C kills no more than A at 25.

## Threats (disclosed)
The experimenter saw the gold list before writing the v2 prompt, classification and mutants. The gold list and judge are the same model family as the generator. The agent is a single toy agent. Only gold items with an oracle-detectable consequence can score on detection. The coverage summary is part of what BCE is claimed to add, so C vs B confounds framing with extra input. The human audit is by the experimenter and is not fully blind.

## Artifact hashes at freeze
Recorded in the 3a commit message and in `experiments/step3/manifests/prereg_freeze.json`.
