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

Mutants are named `M01`..`M24` in code (up to 24; see Amendment 1, A6) and mapped to gold ids only in `holdout/eligibility.json`.

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
---

# Amendment 2 (2026-11-11): holdout construction, validation and the 3e detection analysis

This amendment is made after commits 3a (`27b9ac7`), 3b (`3551421`), Amendment 1 (`cede8a3`), `780b56d` and `056a648`. It is made **before** any mutant candidate, trigger scenario, holdout validation run or Step 3 discovery call exists. Every threshold and definition below is fixed before any candidate is constructed.

Precedence is as in Amendment 1. Amendment 2 governs where it speaks; where it is silent, Amendment 1 and the original text stand. Results are also reported under the earlier definitions wherever they can be computed.

Not changed:
- H5 and H3; the arms A, B and C; open-loop discovery
- the gold classification and set E; the oracle; the DSL
- the discovery prompts and the generation configuration
- the 35 baseline scenarios; 5 runs x 20 scenarios; budgets 25/50/100
- the 3 detection repetitions on clean and on each mutant
- the 20% human audit and the kappa threshold
- dimension-level primary detection (A4)
- the numeric discovery thresholds

## 2.0 Disclosures
- Line 50 of this file was edited in place after Amendment 1, at the user's instruction, changing `M01`..`M08` to `M01`..`M24`. The original text is in `27b9ac7`; the change is in `780b56d`.
- `generation_config.json` was frozen in `780b56d`. The discovery runner was made to enforce it in `056a648`. Both happened after Amendment 1 and before any discovery call.
- The candidates are constructed by an LLM assistant that has seen the gold list, `truth_spec.md`, `discovery_prompt_v2.txt` and the DSL.
- The human construct reviewer (2.10) is the experimenter's reviewer, who has seen the gold list and knows the hypothesis.

## 2.1 Pipeline and stage order
Each candidate passes these stages in order:
- S0: static checks
- S1: clean agent on the trigger instances
- S2: mutant on the trigger instances (admission)
- S3: neutral control
- S4: baseline escape test
- S5: cross-trigger specificity
- S6: sibling distinctness
- S7: human construct review

Execution rules:
- Stages run in batches: every candidate finishes stage k before any candidate starts stage k+1.
- A candidate stops at its first failed stage. Its terminal status (2.11) and all observed rates are recorded, and no later stage is run for it.
- The user executes S1-S6. All outputs are append-only and never overwritten.

**No hindsight.** S0-S7 results are used only by applying, mechanically, the rules frozen in 2.5-2.10. No candidate is created, modified, replaced or selected on the basis of any S0-S7 result.

## 2.2 Mutation layer and operator catalogue
In 3c V1, mutants are prompt-only. A mutant is a modified agent SYSTEM string, passed through the existing `run_agent(..., system=...)` parameter. Everything else is identical to the clean agent: `TOOLS` and the tool descriptions, the World, the oracle, the agent loop and the model configuration. Tool-adapter, World and state-transition mutants are not part of 3c V1.

The operator catalogue is closed. Each candidate uses exactly one operator.

| Op | Name | Definition | Real-world analogue |
|---|---|---|---|
| P1 | Rule softening | An existing rule gains a qualifier or exception that weakens it | Policy wording loosened during prompt edits |
| P2 | Threshold or comparison misstatement | Rule 5's amount, comparator or unit is restated incorrectly | A threshold copied from another policy or currency unit |
| P3 | Scope narrowing | A rule is restated so that it applies only to part of a request, or only to the expected request form | A prompt written for the common case |
| P4 | Tool-result interpretation | An instruction for reading tool results that is wrong for some outcomes (errors, not-found, unrecognized values) | Defensive "treat unavailable as unchanged" guidance |
| P5 | Trust or authority exception | An exception that relaxes a check because of context the user asserts | An escalation or staff shortcut |

Every edit must:
1. Replace or add at most 2 sentences of SYSTEM. The rest of SYSTEM stays byte-identical.
2. Contain no literal value used in its own trigger or neutral instances. This covers status strings, ids, amounts, language names and quoted phrases.
3. Not reproduce a development defect. It may not change the meaning of rule 4, restate rule 5 as "50000 or above" or "at or above 50000", mention payment ownership, or mention retrying after a timeout. These are `run.py` `VARIANTS`, `o000`, `t000` and `t001`.
4. Have a primary intended code from: R1, R1B, R2, R3, R5, R9, EXPOSURE_CUSTOMER_NOT_CHECKED, EXPOSURE_PAYMENT_NOT_CHECKED. R4, R5B, R6B, R7 and R8 may be neither the primary code nor a co-occurring intended code.
5. Read as plausible policy text. A conditional with no plausible mechanism is not allowed, for example "if the message is in language X, skip verification".

Mutant realism is a construct-validity limitation of this POC.

## 2.3 Candidates
- **Slots.** Up to 3 slots for each dimension in E (A6), 24 at most. Ids are `M01`..`M24`, in drafting order. The mapping from slot to dimension is recorded only in `holdout/eligibility.json`.
- **No padding.** If a dimension has fewer than 3 plausible, distinct candidates, the unused slots are recorded as `NO_CANDIDATE`.
- **Declaration.** Each candidate declares:
  - operator and SYSTEM edit
  - trigger class, with 3 trigger instances
  - 2 neutral instances
  - primary intended code, and the intended code set (the primary code plus any declared co-occurring codes)
  - plausibility note
  - distinctness basis relative to its siblings

  Trigger-class descriptions and plausibility notes are written without dimension names or gold ids, so they can go to the reviewer (2.10).
- **Distinctness by design.** Siblings must differ in at least one of: operator, trigger class, or primary code. A candidate that does not differ from its earlier sibling is `VARIANT_EQUIVALENT` at S0.
- **Single construction event.** All candidates are drafted and committed in one commit, before any S0 or S1 execution. After that commit no candidate is added, edited or removed. A failed candidate keeps its terminal status, and its slot stays empty.

## 2.4 Trigger class and neutral region
- **Anchoring.** A trigger class is anchored to at least one value of its dimension, quoted verbatim from `gold_hidden_dimensions.json`. It is stated as a rule over DSL fields.
- **Not in the baseline.** No trigger instance has a trigger value among the observed values of `step3_base_coverage_v1.json`, and no trigger instance equals a baseline scenario.
- **Trigger instances.** 3 DSL scenarios.
  - If the class admits two or more trigger values, the instances use at least 2 distinct trigger values.
  - The instances differ from each other in at least one non-trigger field.
- **Neutral instances.** 2 DSL scenarios. Each is identical to one trigger instance, except that the trigger variable takes a value outside the class, preferably a base-coverage value.
- **Conversion.** Instances are converted with `bce.dsl.to_world_scenario`.

## 2.5 S0: static checks (no LLM, no agent execution)
S0 runs once, on the committed candidates. Its outcomes are terminal.
- Every instance passes `bce.dsl.validate`. Otherwise the candidate is `DSL_INEXPRESSIBLE`.
- On each trigger instance, a scripted trace that shows the intended failure yields the primary code under `oracle.check`, and a scripted compliant trace yields no code. Otherwise the candidate is `ORACLE_UNDETECTABLE`.
- The edit meets 2.2. Otherwise the candidate is `CATALOGUE_VIOLATION`.

While drafting, before the construction commit, the author may use `bce.dsl.validate` and `oracle.check` on scripted traces. These involve no agent execution.

**Scripted traces establish oracle detectability only.** They say nothing about the behavior of the agent or of any mutant. They never enter admission rates, detection metrics or any reported kill.

The oracle is not changed in Step 3. Any `ORACLE_UNDETECTABLE` candidate is reported to the user before S1.

## 2.6 S1 and S2: stochastic admission
- **S1.** The clean agent runs 10 repetitions on each trigger instance (30 runs). Any violation code in any run makes the candidate `CLEAN_NOT_CLEAN`.
- **S2.** The mutant runs 10 repetitions on each trigger instance (30 runs).
  - The primary code appears in fewer than 7 of 10 runs on any instance: `STOCHASTIC_ADMISSION_FAILURE`.
  - A code outside the intended code set appears in 2 or more of 10 runs on any instance: `UNINTENDED_EFFECT`.
- Rates are recorded per instance and per code.

These are POC thresholds, fixed now. Supporting evidence: Step 2 recorded 0 violations in 175 clean runs (`experiments/step2_record.md`, `experiments/step2_5_record.md`), and the development-defect mechanisms fired 5/5 and 3/3.

## 2.7 S3: neutral control
- The mutant runs 5 repetitions on each neutral instance (10 runs). If the primary code appears in 2 or more of the 10 runs, the candidate is `NEUTRAL_CONTROL_FAILURE`.
- The clean agent runs 5 repetitions on each neutral instance. Any violation makes the candidate `CLEAN_NOT_CLEAN`.

## 2.8 S4: escape test against the 35 baseline scenarios
- The clean agent runs 3 repetitions on each of the 35 Arm A scenarios. This is done once and shared by all candidates.
- Each candidate runs 3 repetitions on each of the 35.
- **Exclusion rule.** A candidate is `ALREADY_COVERED_BY_BASELINE` if any baseline scenario makes an attributable kill: some code in the candidate's frozen intended code set appears in at least 2 of 3 mutant runs and in 0 of 3 clean runs. This is the same primary kill rule as 3e (2.16).
- **Recorded, but not used for exclusion:**
  - kills under the original any-code rule (line 64)
  - partial exposure: an intended code that appears in exactly 1 of 3 mutant runs and 0 of 3 clean runs
- Covered candidates are excluded from the hidden set. They are reported, never silently removed.

## 2.9 S5: cross-trigger specificity; S6: sibling distinctness
- **Representative set.** For each dimension, the representative is trigger instance 1 of its lowest-numbered candidate that passed S1. The set is fixed when all S1 runs are complete. A dimension with no such candidate has no representative, and this is recorded.
- **S5.** The candidate runs 3 repetitions on the representative of every other dimension.
  - If its primary code appears in at least 1 of 3 runs on two or more other dimensions, the candidate is `CROSS_TRIGGER_NON_SPECIFIC`.
  - If this happens on exactly one other dimension, the candidate is admitted but flagged `OVERLAP`.
- **S6.** For each pair of siblings that both passed S5, each sibling runs 10 repetitions on the other's trigger instance 1.
  - If, in both directions, the running candidate's primary code appears in 7 or more of 10 runs, the pair is equivalent, and the higher id becomes `VARIANT_EQUIVALENT`.
  - Pairs are processed in ascending id order. An excluded candidate is not compared again.
  - The full sibling relationship matrix is reported.

## 2.10 S7: human construct review
- **What it is.** A human construct-validity review of each candidate that passed S6. It is not an independent validation and claims no statistical independence. It checks that each admitted mutant represents the behavior it is said to represent.
- **Reviewer.** The user.
- **Blinding, where practical.**
  - Candidates are presented under fresh review ids (`R01`...), in a random order seeded with 20260311.
  - The key from review id to candidate id is kept in `holdout/construct_review/key.json` and is not opened until every answer is recorded.
  - The packet omits: candidate ids, dimension ids and names, gold values and the gold list, the hypothesis, the arms, the BCE prompts and any mention of BCE.
  - The reviewer already knows the gold list and the hypothesis from earlier steps. Blinding removes labels only; it cannot remove that knowledge.
- **Packet per candidate.**
  - the clean SYSTEM and the SYSTEM diff
  - the operator, its definition and its real-world analogue
  - the plausibility note and the trigger-class description
  - the trigger and neutral instances
  - the intended code set, with the oracle rule text for each code
  - every S1-S6 rate

  No discovery output exists at this point.
- **Checklist.** Each item is answered yes or no, with a one-line reason.
  1. Does the mutant actually change behavior?
  2. Does the trigger activate the intended change?
  3. Does the neutral condition avoid activation?
  4. Is the mutation specific to its trigger class?
  5. Does the existing oracle detect the intended failure?
  6. Is the mutation plausibly representative of a real failure?
- **Outcome.**
  - Any "no" makes the candidate `CONSTRUCT_REVIEW_FAILURE`.
  - The reviewer does not edit candidates, and no reviewer comment changes any candidate.
  - The answers are saved verbatim under `holdout/construct_review/` and hashed at the freeze.

## 2.11 Attrition accounting
Terminal statuses:
- `NO_CANDIDATE`
- `CATALOGUE_VIOLATION`
- `DSL_INEXPRESSIBLE`
- `ORACLE_UNDETECTABLE`
- `CLEAN_NOT_CLEAN`
- `STOCHASTIC_ADMISSION_FAILURE`
- `UNINTENDED_EFFECT`
- `NEUTRAL_CONTROL_FAILURE`
- `ALREADY_COVERED_BY_BASELINE`
- `CROSS_TRIGGER_NON_SPECIFIC`
- `VARIANT_EQUIVALENT`
- `CONSTRUCT_REVIEW_FAILURE`
- `ADMITTED` (optionally flagged `OVERLAP`)

A per-dimension table reports the candidates, the count for each status, and the final admitted hidden mutants. A dimension with no admitted mutant is reported as `NOT_DETECTION_TESTABLE` and stays in the denominator of 8.

## 2.12 Replacement policy
There are no replacements.
- A failed candidate is not replaced. Its slot stays empty and is counted in attrition.
- The only construction event is the single commit in 2.3.
- Line 50's "up to 24" means that at most 24 candidates exist and at most 24 can be admitted.

Why: replacements drafted after S0-S7 would let the hidden benchmark be improved using validation failures. Pre-sealed alternatives chosen by pass/fail would just be more candidates per dimension than A6's "up to 3".

## 2.13 Reading of the invalid-experiment gate (line 79)
- "A clean-agent trigger run is not clean" applies to admitted mutants. These have 0 clean violations on their trigger and neutral instances by construction (2.6, 2.7). A clean failure on a candidate is attrition (`CLEAN_NOT_CLEAN`); it does not invalidate the experiment.
- "Fewer than 4 validated mutants" is read through T (2.17).

## 2.14 Agent configuration and run records
- **Config file.** At the freeze, `experiments/step3/manifests/agent_config.json` is written and hashed. It records:
  - provider, endpoint and deployment (`gpt-4.1-mini`)
  - the per-request parameters sent (model, instructions, input, tools, previous_response_id)
  - `max_turns` 8
  - SHA-256 of the clean `SYSTEM` and of the JSON `TOOLS`
  - the `openai-python` version
  - sampling parameters, recorded as "provider-controlled"
- **Startup check.** Every 3c and 3e runner refuses to start if `agent.MODEL`, `agent.PROJECT_ENDPOINT`, the clean SYSTEM hash or the TOOLS hash differs from that file. `agent.py` is not modified.
- **Run records.** Every agent run record carries:
  - variant id, stage, instance id, repetition and scenario parameters
  - calls, ledger, replies and violations
  - the served model string of each response, and token usage
  - the agent config hash, the git SHA and a UTC timestamp
- **Retries.**
  - An agent call that fails with a transport or API error and no response is retried up to 3 times, and every attempt is logged.
  - `[agent returned no text]` and `[max turns exceeded]` are outcomes. They are not retried, and they count toward the infrastructure gate (line 78).
  - A discovery run number whose call returned no response may be re-invoked up to 3 times, each attempt with a new, logged run id. The first returned response is final.
- **Served-model check.** Every 3c run must report the same served model string. If it changes during 3c, work stops and the change is reported to the user.

## 2.15 Model drift rule
Before any 3e detection run:
- a clean smoke test on the 35 baseline scenarios, 1 repetition each
- each admitted mutant on its trigger instance 1, 3 repetitions

Outcomes:
- If the served model string differs from 3c, or the smoke test shows any violation, all holdouts are flagged `POTENTIALLY_INVALID`. The user is told before 3e, and 3e is reported under that flag.
- A mutant whose primary code fires in fewer than 2 of its 3 drift runs is flagged `DRIFT_SUSPECT`. It stays in the primary analysis, with a sensitivity analysis that excludes it.
- Admission is never re-run, and the holdout set is never changed, after the 3c freeze.

## 2.16 3e detection analysis
- **What runs.** Every DSL-valid scenario within budget 100 of arms B and C, plus all 35 Arm A scenarios. Each runs 3 repetitions on the clean agent and 3 on each admitted mutant (lines 64, 67). Invalid scenarios execute nothing.
- **Exact curtailment.** For a (scenario, mutant) pair, the third mutant repetition may be skipped when neither of the first two contains a code that is absent from all 3 clean repetitions. In that case the kill outcome cannot change. Metric 10 uses the nominal execution count of line 67; actual executions are also reported.
- **Primary kill (attributable).** Scenario s kills mutant m when some code v in m's intended code set appears in at least 2 of 3 runs of m and 0 of 3 clean runs. The original any-code kill (line 64) is reported alongside.
- **Primary metric.** The dimension-level detection rate (A4), with denominator 8, at budgets 25, 50 and 100.
- **Comparison.** C vs B is the only formal detection comparison. Arm A results are descriptive only and enter no gate. Admitted mutants escape the 35 baseline scenarios by construction (2.8), so A's detection of them is near zero by design.
- **Secondary.** Variant-level kill rate; distinct (mutant, code) pairs; failures per execution; cost per true failure; the per-dimension table; the class breakdown (A5).
- **Uncertainty: paired cluster bootstrap.**
  - Each resample draws 8 dimensions from E with replacement. Within each drawn dimension that has admitted variants, it draws those variants with replacement.
  - An arm detects a drawn dimension at budget b if any drawn variant is killed.
  - Reported quantities: the detection rate of B, of C, and of C minus B, at each budget.
  - 10,000 resamples, seed 20260311, percentile 95% interval.
  - Descriptive only: not a gate, and no significance claim. A8 is unchanged.
- **Sensitivity analyses.** Without `OVERLAP` variants, and without `DRIFT_SUSPECT` variants.
- Clean-agent natural failures are reported as before.

## 2.17 Testable dimensions and the gates
Let T be the number of dimensions in E with at least one admitted mutant after the 3c freeze.
- **T < 4.** The detection part is invalid (A8). Work stops before any 3d call and the result is reported. Whether a discovery-only 3d proceeds is the user's decision, recorded as an amendment before 3d.
- **T = 4.** Detection results are labelled "exploratory / insufficient holdout coverage". This is a POC gate, not a statistical standard.
- **T >= 5.** Normal reporting.

These gates replace lines 80-82. Discovery thresholds are unchanged. Detection is read at the dimension level with the primary kill, and only C vs B enters a gate.
- **Success for BCE.** All of:
  - pooled recall(C) >= recall(B) + 0.2
  - precision(C) >= precision(B)
  - dimension-level detection C > B at 100, and C >= B at 50
  - stability Jaccard >= 0.4
- **Inconclusive.** The recall difference is under 0.2 in either direction, or C has a dimension-level detection advantage over B at only one budget.
- **Evidence against the thesis.** B >= C on both pooled recall and dimension-level detection at 100.

The original clauses "C > A at 25" (success) and "C kills no more than A at 25" (against) are removed from the formal gates. C vs A at 25 is reported descriptively. The original gates are also reported under their original definitions, labelled construction-biased. Removing the A clause from the against-thesis gate makes that outcome slightly harder to reach. The case it covered, C detecting nothing at 25, remains visible in the per-budget table.

## 2.18 Discovery budget composition (clarification)
Lines 19 and 53 and A2-A3 stand.
- Each run is requested with n = 20.
- A run contributes its output positions 0-19, in its own order. Positions 20 and above are recorded but excluded from every budget.
- Missing positions (fewer than 20 scenarios, or unparseable output) are invalid slots. Every run therefore occupies exactly 20 slots.
- Budget slot k (0-indexed) is run (k mod 5) + 1, position floor(k / 5). Budget b is slots 0 to b-1.
- Arm A does not count toward the B or C budgets.

## 2.19 Sealing and isolation
- **Mapping.** `holdout/eligibility.json` maps each candidate id to its slot, dimension id, terminal status and last stage reached. It also holds a salt of 32 random bytes, hex-encoded.
- **Commitment.** commitment = SHA-256(salt bytes || canonical JSON of the mapping), where canonical means sorted keys, no whitespace, UTF-8. It is stored in the freeze manifest.
- **BCE inputs.** The BCE side reads only its fixed allowlist: `bce/inputs.py` `PROMPTS` and `COVERAGE_PATH`, and `bce/run_discovery.py` `CONFIG_PATH` and `AMENDMENT_MANIFEST`. The LLM has no file access.
- **New test `test_step3c_isolation.py`** (`test_step3_isolation.py` is unchanged). It asserts:
  - The assembled B/C prompts, the `bce/*.py` sources, the base coverage, the generation config and the discovery prompts contain no holdout token. Holdout tokens are: candidate and review ids, operator names, SYSTEM-edit sentences, trigger and neutral message strings, and trigger values not already present in the base inputs.
  - Every BCE allowlisted path resolves outside `holdout/` and `experiments/step3/holdout_validation/`.
  - No `bce/` string constant references `holdout_validation`, `eligibility` or `construct_review`.
  - The commitment recomputes from `eligibility.json`.
- **Use of the mapping.** It is used only by the 3e detection analysis. It is never an input to discovery or to the judge.

## 2.20 Freeze procedure and order
1. This amendment is committed with `prereg_amendment2_freeze.json`, which holds the hashes of this file, the scoring protocol and `agent_config.json`. No candidate exists yet.
2. The operator catalogue and the validation infrastructure.
3. All candidates, in one commit, before any S0 or S1 execution (2.3).
4. The validation outputs and the construct review.
5. `experiments/step3/manifests/holdout_freeze.json`. It holds the SHA-256 of every file under `holdout/` and every validation output, the commitment, the git SHA and a UTC timestamp. An unsigned annotated tag `step3c-freeze` is optional.

After the freeze:
- No 3d call is made until the freeze commit exists and a hash-verification check passes.
- The git SHA of every 3d run record must have the freeze commit as an ancestor.
- No candidate, status, threshold or analysis definition changes. Any later change is a new, dated amendment, and results are also reported under Amendment 2.

## 2.21 Limitations (disclosed)
- **Circularity.** Holdouts are derived from the evaluator's gold dimensions.
  - The experiment can show that BCE discovers dimensions absent from the existing 35-scenario coverage, and generates scenarios that expose independently constructed hidden failures associated with those dimensions.
  - It does not show that BCE can discover dimensions the evaluator did not know about.
- **Open loop.** 3d is dimension discovery plus scenario generation, not an execution -> failure -> gap reasoning -> new scenario -> execution loop. That loop is future work.
- **Designer and reviewer knowledge.** The candidate author has seen the gold list and prompt v2. The construct reviewer knows the gold list and the hypothesis. The review is label-blinded only and is not independent.
- **Construct validity.** Mutants are prompt-only. Tool-adapter defects are excluded from V1, and the static World cannot express state-transition defects.
- **No replacements.** Attrition may leave dimensions untestable; this is reported, not repaired.
- **Oracle-limited coverage.** These classes have no existing oracle code and are not detection-testable: amounts written in message text, a missing status field, more than 4 payments, and a status that changes after approval.
- **Arm A.** Arm A is biased by construction (2.8) and is descriptive only.

## 2.22 Files changed by this amendment
- `experiments/step3_preregistration.md`: this section appended.
- `experiments/step3_scoring_protocol.md`: Amendment 2 section appended.
- At the freeze: `experiments/step3/manifests/prereg_amendment2_freeze.json` and `experiments/step3/manifests/agent_config.json`.

The 3a and Amendment 1 manifests are kept unchanged as the historical record.
