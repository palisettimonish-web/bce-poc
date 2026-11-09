# Step 3 preregistration: BCE gap discovery

Frozen in commit 3a, before any discovery run, mutant, or detection run exists. **See Amendment 1 at the end of this file (2026-11-10), made before any experiment run.** Changes after this commit are dated amendments at the end of this file. Results are always reported under the original definitions as well.

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

---

# Amendment 1 (2026-11-10): protocol clarification before any experiment run

This amendment is made after commits 3a (`27b9ac7`) and 3b (`3551421`) and **before** any Step 3 discovery call, mutant, trigger scenario, or detection run. At the time of writing no file exists under `experiments/step3/` other than the manifest, and no `holdout/` directory exists. Everything above this line is the original 3a freeze and is unchanged. Where Amendment 1 and the text above differ in wording, Amendment 1 governs the interpretation; where it is silent, the original text stands. Results are also reported under the original definitions where they can be computed.

Not changed: H5/H3, the arms, open-loop discovery, gold classification and set E, the oracle, the 35 baseline scenarios, 5 runs x 20 scenarios, budgets 25/50/100, the 3-clean + 3-mutant repetition and 2/3 mutant, 0/3 clean kill rule, the 20% human audit, the kappa threshold (0.6), and all numeric gate thresholds.

## A1. Generation configuration is frozen before the first discovery call
Before the first Step 3 discovery call, the exact generation configuration is written to `experiments/step3/manifests/generation_config.json`, hashed, and committed. It records every applicable field, and for each field either its value or an explicit status:
- provider; model/deployment; API version, if applicable
- temperature; top_p; max output tokens; seed, if supported
- reasoning configuration, if applicable; response-format configuration, if applicable

A parameter the provider or model does not support, or that the provider controls, is recorded as `"unsupported"` or `"provider-controlled"`. No value is invented to fill a field. Arms B and C use the identical configuration. No parameter is changed after any discovery output is observed. The configuration file's hash is added to every run record.

## A2. Four separate budgets (never conflated)
| Budget | Quantity | Used for |
|---|---|---|
| Discovery budget | Number of generated scenario outputs (invalid ones occupy their slot) | The 25/50/100 curves, unchanged |
| Agent execution budget | Actual agent executions in detection: scenarios x (clean + each evaluated mutant variant) x repeats, counted explicitly | Failures per execution |
| Evaluation budget | Judge calls, judge items, and human-reviewed items for discovery adjudication | Reported separately |
| Financial/token cost | Actual generation, agent and evaluation tokens and/or API cost, when the provider reports them | Cost per true failure |

Metric 10 ("failures per execution") uses the agent execution budget. "Cost per true failure" uses the financial/token cost. "Budget" in the metric definitions and gates above means the discovery budget unless stated otherwise.

## A3. Arm A
Arm A is the fixed 35-scenario baseline, in the stated order, unchanged. It is not a generative arm and consumes no generation budget. A@25 is the first 25 scenarios of that fixed suite. B@25 and C@25 are the first 25 generated scenarios under the preregistered round-robin ordering. Repeating an Arm A scenario creates no new coverage. Arm A is a fixed baseline comparison, not an equivalent generative process.

## A4. Detection metrics: dimension-level is primary
The primary detection unit is the eligible gold dimension (set E, |E| = 8), not the mutant variant, because variants of one dimension are not independent behavioral dimensions.

- **Primary: dimension-level detection rate** at discovery budget b = (number of dimensions in E for which at least one validated mutant variant is killed, by the kill rule, by a scenario within the first b of the arm) / |E|. The denominator is always 8. The report also states how many dimensions have no validated variant, and the rate over only dimensions that have at least one.
- **Secondary: variant-level kill rate** = (validated variants killed by the arm within b) / (validated variants evaluated by the arm).
- A per-dimension detection table (dimension, class, validated variants, variants killed, detected yes/no, per arm and per budget) is always reported.
- Existing metrics 8 and 9 (mutants killed, distinct true failures) are retained and reclassified as secondary. Raw counts and rates are always reported with any ratio.

## A5. Reporting by gold class
Discovery results (precision, recall, matched sets) and detection results are broken out separately for `U_NEW_DIMENSION` (G01, G12, G13, G16) and `U_NEW_VALUE` (G02, G04, G05, G07). `H_HIGHER_ORDER_INTERACTION` is reported only if any item becomes eligible (none is eligible now). `DEV_ONLY` and `EXCLUDE` stay out of headline scoring. The classification is unchanged from the table above.

## A6. Mutant design preferred for 3c (not implemented now)
- Keep the 8 eligible dimensions. Attempt up to 3 mechanically distinct mutant variants per dimension, targeting up to 24 validated variants.
- The variants are not 24 independent dimensions. The primary analysis is at the 8-dimension level; variants are secondary replication/robustness checks within a dimension.
- If a dimension cannot support 3 distinct, non-equivalent, oracle-detectable variants, no artificial variant is invented. The actual validated number is recorded. The gold set is not changed to raise the sample size.
- Variant ids are opaque (`M01`...); the mapping variant -> gold id lives only in `holdout/eligibility.json`.

## A7. Mutant validation requirements for 3c
A variant enters the main experiment only if all of the following hold:
1. The clean agent passes the corresponding trigger scenario.
2. The mutant actually changes the intended behavior.
3. The existing deterministic oracle detects the intended violation.
4. The mutant is non-equivalent to the clean agent for the intended trigger.
5. The mutant is specific enough to represent the intended gold dimension.
6. No new oracle rule is added for the mutant.

Invalid, equivalent or undetectable variants are excluded from the detection set and reported with the reason. They are not replaced with hand-picked variants after any BCE/B/C result is seen.

## A8. Interpretation of the success gates
The numeric thresholds are unchanged. They are preregistered practical POC gates, not claims of statistical significance, and no statistical test or confidence threshold is added. Raw dimension counts and rates are always reported beside them. Wherever a gate above says "mutants killed", it is evaluated at the dimension level first (A4); variant-level counts cannot substitute for dimension-level detection. The invalid-experiment gate "fewer than 4 validated mutants" is read as: fewer than 4 dimensions in E with at least one validated variant. The "200 budget" plateau rule is read the same way (dimension-level detection at 100 versus 50).

## A9. Files changed by this amendment
`experiments/step3_preregistration.md` (this section appended; one pointer line at the top), `experiments/step3_scoring_protocol.md` (Amendment 1 section appended), and the new manifest `experiments/step3/manifests/prereg_amendment1_freeze.json`. The 3a manifest `prereg_freeze.json` is kept unchanged as the historical record.
