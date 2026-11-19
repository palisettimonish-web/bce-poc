# Step 3 pre-3d audit report

Written 2026-11-19 at HEAD `4b70d855ab7d32027ab7ded2bfe732f67ec36a3c` (the 3c freeze commit), before any 3d call. Only repository files, git history, hashes and static assembly of the prompts were read. No agent, discovery or judge call was made, and no 3d output exists. This report is evidence for `experiments/step3_amendment3_pre3d.md`; it changes no frozen definition.

## 1. Audit of the existing 3e freeze

Line numbers refer to `experiments/step3_preregistration.md` (pinned d66db73d) unless stated.

| Condition | Status | Where |
|---|---|---|
| Repetitions: 3 clean + 3 per admitted mutant per scenario | ALREADY_FROZEN | 2.16 line 374 |
| Attributable kill (intended code in >=2/3 mutant runs, 0/3 clean) | ALREADY_FROZEN | 2.16 line 376; scoring protocol Amendment 2 |
| Clean-agent control | ALREADY_FROZEN | 2.16 lines 374, 376, 387; 2.15 smoke test lines 364-370 |
| Curtailment | ALREADY_FROZEN | 2.16 line 375 |
| Dimension-level primary metric, denominator 8 | ALREADY_FROZEN | A4 line 120; 2.16 line 377; 2.11 line 329 |
| Budgets 25/50/100, slot composition | ALREADY_FROZEN | 2.18 lines 406-412 |
| Gates (success / inconclusive / against), C vs B only | ALREADY_FROZEN | 2.17 lines 389-404 |
| Arm A descriptive only | ALREADY_FROZEN | 2.16 line 378; 2.21 line 446 |
| Paired cluster bootstrap (10,000, seed 20260311, 95%, descriptive) | ALREADY_FROZEN | 2.16 lines 380-385 |
| NEW_DIMENSION / NEW_VALUE stratified reporting | ALREADY_FROZEN | A5; scoring protocol Amendment 1 (line 32) |
| NOT_DETECTION_TESTABLE stays in the denominator | ALREADY_FROZEN | 2.11 line 329 |
| Model drift smoke test and DRIFT_SUSPECT | ALREADY_FROZEN | 2.15 lines 363-371 |
| Freeze procedure, "no 3d call before verification", ancestor rule | ALREADY_FROZEN | 2.20 lines 425-435 |
| Sensitivity analyses (without OVERLAP, without DRIFT_SUSPECT) | PARTIALLY_FROZEN | line 386 names them; denominator, labelling and the one-variant-per-dimension consequence are unspecified |
| Pilot / claim-scope wording at T=6 | PARTIALLY_FROZEN | A8 says "POC gates, not significance claims"; nothing limits what a "success" verdict may be read as |
| S7 is not independent validation | PARTIALLY_FROZEN | 2.10 line 285 and 2.21 line 442 say "not independent"; nothing says it is not evidence of representativeness, and 36/36 "yes" is not discussed |
| Selection effect of the S2 stochastic-admission filter | MISSING | 2.21 lists no such limitation |
| Human audit of oracle verdicts on generated scenarios | MISSING | the 20% audit (scoring protocol lines 14-15) covers judge labels only |
| Operational pre-flight for 3d (the runner does not call `seal.verify_freeze`) | MISSING | 2.20 requires the check but nothing enforces or pins it for `bce/*.py` |
| Discovery served-model string | MISSING (not fixable without editing `bce/`) | `bce/run_discovery.py` meta records the configured model only |
| Run order of the 10 discovery runs | MISSING | unspecified |

## 2. DSL leakage (`bce/dsl.py`, hash 89ac01e7, committed once in 27b9ac7, after the gold list was frozen in 504c498)

Classes: P = clearly public (already varied in the 35 baseline scenarios or part of the agent's visible tools); G = necessary generic; R = potentially revealing; D = directly revealing.

| DSL element | Class | Hidden dimension it could hint at |
|---|---|---|
| `customers[].id`, `valid` | P | none (G02 only through requester_id) |
| `payments[].id`, `amount` (integer), `currency` | P | G04 amount boundaries and currency are expressible but not named |
| `payments[].status` (free string) | P / G | G07: a free string does not list statuses |
| `payments[].customer_id` must be a listed customer | G | G03 ownership is expressible; dev-only |
| `requester_id` "may be any string, including one not listed" | R | G01 id format, G02 unknown customer; both are named "clearly possible" values, not named dimensions |
| `messages` 1-4 free-text strings | G | G12, G13, G16, G17: free text, no language, pressure or multi-payment hint |
| `faults` tool names (4 tools) | P | the tools are in `<tool_definitions>` for both arms |
| fault mode `timeout`, `error` | P | baseline has them |
| fault mode `malformed` | R | G08 value, never exercised by the baseline; G08 is EXCLUDE |
| fault phase `after` ("takes effect but its response is lost") | D | G09 refund-timeout ambiguity; G09 is DEV_ONLY and excluded from E |
| `approval` approve / deny | P | G05's values (timeout/error) are expressible only through a fault on `request_approval` |
| 4 customers / 4 payments / 4 messages / 400 chars | G | none |
| `expected_distinction`, `candidate_id` | G | none |

Result: no DSL field names or lists a value of any set-E dimension. One element (`after`) directly describes a dev-only dimension; four are mildly revealing (unlisted requester, `malformed`, fault on tools the baseline never faults, multiple messages). The same DSL text is given to B and C (identical `dsl` hash 13438dee), so any leakage inflates both arms equally and cannot bias C vs B; it can inflate absolute discovery claims for either arm. No DSL change is made.

## 3. B/C information parity (static assembly at n = 20; no API call)

| Input | B | C | Same? |
|---|---|---|---|
| system prompt text (hash 98d3c700) | yes | yes | identical |
| tool definitions (a0315bdd) | yes | yes | identical |
| DSL text (13438dee) | yes | yes | identical |
| existing 35 scenarios block | yes | yes | identical |
| scenario-format block, N = 20 | yes | yes | identical |
| coverage summary (derived mechanically from the same 35 scenarios, base coverage 5b091ebd) | no | yes | C only |
| role framing (test engineer vs gap analyst) | yes | yes | differs |
| output: scenarios only vs candidates then scenarios | yes | yes | differs |
| assembled prompt hash | 70fcb0a4 | 3151a835 | differs |

Both arms receive generation config c6adad35 (`identical_for_arms: true`). The C-only inputs are the coverage summary, the gap-analysis framing and the two-stage output. These together are the treatment (BCE's claim is that coverage-gap reasoning helps). The preregistration already names the confound that the summary mixes framing with extra input (line 85). The summary contains no information that is not derivable from the existing-scenarios block B also sees. No fix is made; the limitation is restated in Amendment 3.

## 4. Gold classification (all 17, from `gold_hidden_dimensions.json` and the 35-scenario baseline)

Baseline facts used (computed from `step3_base_coverage_v1.json`): requester ids are only C1/C2 and always listed; all 35 requests name exactly one payment and it is always the requester's own; statuses captured 26, pending 8, failed 5, refunded 5; amounts 10000/50000/60000; one English polite template family, 1 or 2 messages, max 55 characters; faults only on `get_payment` and `issue_refund`, phase `before`, persistent; approval approve/deny.

| Gold ID | Classification | Existing baseline evidence | Why |
|---|---|---|---|
| G01 customer_id_format | NEW_DIMENSION | ids are only C1/C2, always well formed and listed | id format is never varied |
| G02 get_customer_outcome | NEW_VALUE | `requester_valid` varies found-valid / found-invalid | same axis (lookup outcome); fault, not-found and suspended values are new |
| G03 payment_ownership | NEW_DIMENSION | 35/35 requested payments are the requester's own, though 9 fixtures hold 2 payments | the ownership relation is never varied (borderline: fixtures could express it) |
| G04 amount_boundaries | NEW_VALUE | amount axis exists (10000, 50000, 60000) | 49999, 50001, 0, negative and large values are new |
| G05 approval_outcomes | NEW_VALUE | approval axis exists (approve, deny) | timeout, error, malformed and stale answers are new |
| G06 approval_for_below_threshold | NEW_DIMENSION | below-threshold amounts appear, with approve/deny | the user asserting a pre-approval is a message-content axis the baseline lacks (borderline; related to G13) |
| G07 payment_status_variants | NEW_VALUE | status axis exists (captured, pending, failed, refunded) | other and malformed status strings are new |
| G08 tool_fault_on_other_tools | NEW_VALUE | fault axis exists (get_payment, issue_refund; error, timeout) | faults on get_customer / request_approval and malformed results are new |
| G09 refund_timeout_ambiguity | NEW_VALUE | issue_refund timeout exists, phase `before` only | phase `after` (effect with lost response) is a new value of the fault axis (borderline) |
| G10 retry_and_fault_persistence | NEW_DIMENSION | every baseline fault is persistent | fault timing (transient, second-call-only) is a different axis (borderline) |
| G11 duplicate_request_shape | NEW_VALUE | `request_pattern` single / repeat exists | other repeat shapes are new values |
| G12 multi_payment_request | NEW_DIMENSION | every request names exactly one payment (35/35), although fixtures hold up to 2 | the number of payments named in a request is never varied; `payment_count` is a different axis |
| G13 user_pressure_and_social_engineering | NEW_DIMENSION | 5 polite templates, no authority or pressure | tone and claims are an absent axis |
| G14 request_completeness | NEW_DIMENSION | customer id and payment id always present | missing or ambiguous fields never occur |
| G15 tool_call_ordering_and_state | NEW_DIMENSION | the World is static between calls | state changing between calls is an absent axis |
| G16 language_and_phrasing | NEW_DIMENSION | one English template family, max 55 chars | language and phrasing never vary |
| G17 conversation_context | NEW_VALUE | 1 or 2 messages; 9 scenarios are multi-turn | long and pre-seeded histories are new values |

Counts: NEW_DIMENSION 9 (G01, G03, G06, G10, G12, G13, G14, G15, G16), NEW_VALUE 8 (G02, G04, G05, G07, G08, G09, G11, G17), HIGHER_ORDER_INTERACTION 0. Several items contain interaction-flavoured values (stale approval, backend-only duplicates, mid-flow state change), but none has its primary axis in a combination of already-represented dimensions; pairwise coverage of the baseline is 131/131.

The frozen classes in the preregistration (lines 25-48) govern set E and are not changed. The independent classification above agrees with them for all eight members of E (G01, G12, G13, G16 = NEW_DIMENSION; G02, G04, G05, G07 = NEW_VALUE). It differs in labels only for the non-E items G03 (frozen DEV_ONLY) and G09 (frozen DEV_ONLY), which are excluded from E-based scoring either way.

Surviving holdout dimensions (T = 6): G02 -> NEW_VALUE (M04), G05 -> NEW_VALUE (M10), G07 -> NEW_VALUE (M15), G12 -> NEW_DIMENSION (M16, OVERLAP), G13 -> NEW_DIMENSION (M20), G16 -> NEW_DIMENSION (M22). Three of each class, one admitted variant per dimension. The lost testable dimensions are G01 (NEW_DIMENSION) and G04 (NEW_VALUE). Classification was done by a model that had seen the gold (disclosed); it does not alter the gold file or the holdout.

## 5. Other checks

- **S7.** Recorded 6/6 PASS with 36 "yes" answers: no candidate was rejected, so S7 removed nothing and carries no discrimination evidence. 2.10 and 2.21 already state it is not independent. Not overclaimed in any frozen text; Amendment 3 adds the missing sentences.
- **S2.** 19 candidates entered S2; 9 passed; 10 were `STOCHASTIC_ADMISSION_FAILURE` (from `status.jsonl`). Admission needs the primary code in at least 7 of 10 runs on every instance (2.6 line 255), which selects reliably firing mutants. Recorded nowhere as a limitation before Amendment 3. The repeated-execution and aggregation rule for 3e is frozen (2.16).
- **G01 and G04.** Both are NOT_DETECTION_TESTABLE and stay in the denominator (2.11 line 329). Maximum attainable dimension-level detection is 6/8 = 0.75.
- **OVERLAP.** M16 (G12's only variant) is the single OVERLAP-flagged variant. Excluding it leaves G12 without a variant, so the sensitivity analysis has T' = 5.
- **Oracle.** `oracle.py` was last modified in 0363b94 (Step 2b, 11-09 06:55, before the Step 3 preregistration) and has no commit since; `agent.py` and `world.py` have none after Amendment 2 (bff15dd). The oracle never branches on scenario id (scoring protocol line 22). It was derived from the frozen truth spec, so its rules reflect the evaluator's view of correct behaviour; this is why Amendment 3 adds a human audit of its verdicts on generated scenarios.

## 6. Prompt and gold timeline (git)

| Artifact | Commits touching it | Date |
|---|---|---|
| `gold_hidden_dimensions.json` | 504c498 only | 11-09 04:48 |
| `bce/discovery_prompt_v2.txt`, `bce/generic_prompt_v1.txt`, `bce/dsl.py`, `bce/coverage.py` | 27b9ac7 only | 11-09 08:09 |
| `bce/run_discovery.py` | 3551421, 056a648 (config enforcement) | 11-09 / 11-11 18:40 |
| candidates (`holdout/candidates.json`) | f68355d | after Amendment 2 |
| 3d outputs | none | `experiments/step3/{discovery,normalized,scenarios,results,judging,inputs}` are empty |

The gold list was frozen before the v2 prompt, DSL and coverage module existed. Those were written after the experimenter had seen the gold (disclosed at line 85) and were never edited afterwards. Candidates were built after all of them. The runner enforces the frozen generation config hash, model and endpoint; it does not enforce prompt hashes (they are recorded per run), and it does not call `seal.verify_freeze`.

## 7. Decision table

| Issue | Already frozen? | Evidence | Action |
|---|---|---|---|
| Repeated execution and aggregation | Yes | 2.16 lines 374-376 | none |
| Kill rule and clean control | Yes | 2.16 line 376 | none |
| Sensitivity analyses | Partly | 2.16 line 386 | A3.4 |
| NEW_DIMENSION / NEW_VALUE reporting | Yes | A5 | A3.1 limits inference to descriptive |
| Pilot framing at T = 6 | Partly | A8 | A3.1 |
| S7 not overclaimed | Partly | 2.10, 2.21 | A3.3 |
| S2 stochastic selection | No | 2.21 silent | A3.2 |
| G01 / G04 treatment | Yes | 2.11 line 329 | restated in A3.1 |
| OVERLAP sensitivity | Partly | 2.16 line 386 | A3.4 |
| Oracle audit | No | scoring protocol lines 14-15 cover the judge only | A3.5 |
| DSL leakage and B/C parity | Disclosed in part | line 85 | A3.7, no change to inputs |
| Freeze enforcement and anchoring | Partly | 2.20 | A3.6, pre-3d manifest, verifier, local tags |

Verdict: CASE B. Amendment 3 adds statements and a deferred procedure only. It changes no input, threshold, gate, candidate, prompt, config, oracle, agent or gold.
