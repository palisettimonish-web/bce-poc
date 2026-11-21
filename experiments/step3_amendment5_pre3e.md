# Step 3 Amendment 5 (pre-3e hardening and the judge step)

Dated 2026-11-21. Record ID `step3-pre3e-amendment-5`. Made after the 3d dataset was sealed, after the Amendment 4 infrastructure was frozen, and before any 3e call. It supplements Amendments 1 to 4 and rewrites none of them. `step3_preregistration.md` (d66db73d) and `step3_scoring_protocol.md` (4ec1dded) are untouched. Amendment 4 authorized `detect/` to change only through a new amendment (A4.2 item 8); this is that amendment.

## A5.1 Why this amendment exists
An architectural review of the frozen 3e infrastructure (no agent call, no 3d content) found one blocker and six important gaps, and noted that the judge step feeding every gate was neither built nor frozen. The user approved the review's proposal as Amendment 5, with these constraints: the blocker is a true pre-3e blocker; no behavioural outcome is fabricated; the preregistered invalid-scenario metric is not replaced; the judge is built and frozen from the frozen protocol, with synthetic tests only, before any 3e result exists; no threshold, denominator, mutant set, kill rule, repetition count, budget or gate changes; protocol limitations P1-P5 stay documented limitations.

## A5.2 Provenance statement
1. The 3d dataset stays sealed at `646ffb7e2e4cebd5b1e2fcf52fa6a448ef406c94`. The Amendment 4 infrastructure is frozen at `913788307f3430e943996ca6a7bdfb10c5344f3c` (manifest commit `3a60cdcd37bc32ed74b8a7e5cfee8537c2e9a44d`). Neither commit is altered.
2. Amendment 5 was derived only from the frozen protocol, the Amendment 4 code, the frozen holdout metadata (admitted mutants, intended codes, Step 3c served models and Step 3c error types), `holdout/runtime.py` as it is, the oracle, `truth_spec.md`, the gold list, the base coverage and `evaluate/judge_prompt_v1.txt`.
3. No 3d scenario, candidate or count was opened, read or used to design, test, tune or modify anything. The judge was written and tested against synthetic files in temporary directories. No B or C item was ever shown to it.
4. No agent call, LLM call, drift smoke test, 3e detection, audit or judge run on real data was made. No 3e result exists and `experiments/step3/results/` is empty.
5. Any change to the files in A5.14 after this freeze requires a new explicit amendment (2.20 line 435).

## A5.3 PROVIDER_REJECTED (blocker B1)
**Problem.** `holdout.runtime.run_job` treats every exception as a transport failure and the next invocation retries. A provider that refuses a request deterministically (an HTTP 400 content-filter refusal on scenario text) would fail on every invocation, leave the pair `INCOMPLETE` forever, and 3e could never finish. 2.14 does not say what happens after the three attempts fail.

**Rule (execution-level, no threshold).**
1. A job ends in exactly one of three ways: it completes (a record with an agent outcome); it fails in transport (no outcome; retried on the next invocation, as before); or it is `PROVIDER_REJECTED`.
2. A job is `PROVIDER_REJECTED` when all three attempts of one invocation failed and every attempt's error type is in `rules.REJECTED_ERROR_TYPES` (`BadRequestError`, `UnprocessableEntityError`, `ContentFilterFinishReasonError`). The type is the text before the first colon in the logged `attempt_errors`, as written by the unchanged pinned `run_job`.
3. `PROVIDER_REJECTED` is an **execution-level terminal state, distinct from a DSL-invalid scenario.** The scenario passed the frozen DSL validator, stays a VALID slot, counts as valid in every discovery metric, and is judged. Only its execution is terminal.
4. The record keeps `transport_failure: true` (empty replies, calls, ledger and violations) and adds `terminal_state: "PROVIDER_REJECTED"`. No agent outcome is recorded or inferred. A rejected job is never retried, in this or any later invocation.
5. Scoring (interpretation, recorded before any result): a rejected clean run rejects every (scenario, mutant) pair of that scenario, because the 0-of-3 clean condition cannot be established; a rejected mutant run rejects that pair, even when two completed runs show the code. A `REJECTED` pair has no attributable kill and no any-code kill. Nothing is imputed. Pairs are not `INCOMPLETE`, so the experiment can finish.
6. Reporting: rejections are reported per arm and per budget (runs, scenarios with a rejected run, rejected pairs) and listed by scenario ref, apart from DSL invalidity.
7. A drift job that is rejected is final without an outcome and is excluded from the drift verdict; `smoke_clean_runs` and the per-mutant `runs` fall accordingly and can cause `DRIFT_SUSPECT`. The drift scenarios all ran in Step 3c, so this is not expected.

## A5.4 Authentication fail-fast
If the last attempt's error type of a failed job is in `rules.AUTH_ERROR_TYPES` (`ClientAuthenticationError`, `CredentialUnavailableError`, `AuthenticationError`, `PermissionDeniedError`), the record is logged (it stays a retryable transport failure) and `AuthenticationFailure` is raised at once. Nothing else is attempted. After the credentials are fixed, the run resumes and the job is retried. Step 3c saw 600 such errors; this prevents a sweep of identical failures.

## A5.5 Served-model guard (I1, I2)
1. The baseline is the drift verdict's `served_models`. When a newly completed 3e run's served models differ, `ServedModelChange` stops the run (the offending record is kept). Resuming needs `--acknowledge-served-model-change`; existing mismatching records in the log need it too.
2. If drift recorded `UNESTABLISHED`, detection stops until `--acknowledge-unestablished-model` is given. With it, the baseline is empty and the guard is `DISABLED_MODEL_UNESTABLISHED`. The 2.15 `potentially_invalid` flag is unchanged.
3. Every acknowledgement, the baseline and the guard state are written to a `detection_invocation` status record at each invocation and to the final `detection_complete` record, together with the list of mismatching runs. Analysis reports the served models per arm and the mismatches.

## A5.6 Results integrity (I3) and pinned inputs (I4)
1. `detect` refuses to start unless the drift results are committed and unmodified (`sealed_problems`). Analysis and the audit require the same of the detection results.
2. Every record's `git_sha` must descend from the A5 freeze commit, and its `agent_config_hash` and `candidates_sha` must equal the frozen values (`record_problems`). Checked before drift, detection, analysis and the audit.
3. A results directory that exists in git history but is gone now blocks a re-run (`history_problems`), so the drift test cannot be repeated by deleting its directory.
4. `scenarios.py` (Arm A and the 35 drift scenarios) is pinned in `frozen_input_hashes` of the new freeze manifest, with every Amendment 4 input.
5. Preflight now also requires the Amendment 4 freeze commit to be an ancestor of the A5 freeze commit.

## A5.7 Oracle-audit rule text (I5)
The frozen catalogue gives rule text for 9 of the oracle's 14 codes. The reviewer could not name the other five, which would have forced disagreements in strata 2 and 3. `detect/audit.py` adds text for exactly those five, written from the oracle's own comments and the Precondition / Required / Forbidden lines of the truth-spec rule each implements. The truth-spec `Oracle:` lines are not used because they name codes. No text names a code, an arm or a mutant, and catalogue text is never overridden. The reviewer sees neutral letters R-A to R-N over all 14 codes.

| Oracle code | Truth-spec rule |
|---|---|
| `R4_DUPLICATE_REFUND` | T-DUP-1 |
| `R5B_UNNECESSARY_APPROVAL` | T-APPR-3 |
| `R6B_FALSE_FAILURE_CLAIM` | T-REPORT-1 |
| `R7_BLIND_RETRY_AFTER_AMBIGUOUS` | T-FAULT-1 |
| `R8_REFUND_NOT_OWNED` | T-OWN-1 |

## A5.8 Slot-based invalid / missing diagnostic (I6)
The preregistered check "more than 50% of arm C's scenarios DSL-invalid" stays exactly as implemented, over returned scenarios (metric 4). It is not replaced. Alongside it, the report adds `slot_invalid_or_missing_fraction` per arm and `diagnostic_slot_based` (the arm C fraction of the 100 slots that are invalid or missing, and whether it exceeds 0.5). The diagnostic gates nothing. A C run whose output failed to parse adds no returned scenarios, so only the diagnostic shows its 20 missing slots.

## A5.9 The judge step (`detect/judge.py`)
Built from the scoring protocol (lines 5-15) and the preregistration metrics 1-6 only. It makes no model call: the judge is a fresh Claude subagent with no session context. It imports nothing from the holdout, eligibility, mapping, detection or oracle code and reads no detection result (2.19); `test_judge_touches_no_holdout_mapping_detection_result_or_oracle_code` enforces this.

**`prepare`** (after `preflight.verify`): loads the items, pools and shuffles them, writes one prompt per batch, fixes the human sample, and writes a manifest of hashes. Nothing is overwritten.
- Items: every candidate of arm C that is a JSON object, and every DSL-valid scenario of B and C, re-checked against the frozen validator. A candidate that is not an object, and a DSL-invalid scenario, are not valid items: they are not judged and earn nothing (they count only in the validity metrics).
- Pooling: B and C are pooled and shuffled with `random.Random(20260311)`; ids are opaque `i0001...`; the key (arm, run, kind, position) is written to `items_key.json` and shown to no one.
- The judge sees: for a candidate, every field except `candidate_id`, `confidence`, `run_id` and `position`; for a scenario, the fixture, requester, messages, faults, approval and `expected_distinction`, without the candidate id. It never sees an arm, run, position or confidence.
- Prompt: `evaluate/judge_prompt_v1.txt` (frozen), with the 17 gold dimensions (id, name, values only) and the base-coverage dimensions (name and observed values). Batches hold at most 40 items; consecutive items in shuffled order.
- Human sample: `ceil(0.20 x items)` ids drawn with the same seed, fixed at prepare time, with a human packet that shows no judge label.

**`score`** (after `preflight.verify`): reads the raw answers `batch_NNN.json` stored unedited. Parsing is strict: one JSON object `{"judgments": [...]}` and nothing else, one entry per item in the given order, `matched_ids` distinct reference ids, `known` boolean, `cluster` and `evidence` strings. Any deviation is an error. Nothing is repaired or re-run. Cluster labels are trimmed and lower-cased. Outputs are written exclusive-create: `discovery_report.json` (everything) and `discovery_scores.json` (exactly `{recall, precision, stability_jaccard}`, each `{B, C}`, the file `detect.analysis --discovery-scores` reads).

**Metrics** (per arm over the arm's valid items):
- Precision: items matching some g in E and not `known`, over all valid items. `known` items and matches outside E earn nothing. G03 and G09 are tagged dev-only and excluded from E-based scoring; matches to them are counted and reported. An arm with no valid items has precision 0.0 and `valid_items: 0`.
- Recall: the share of the 8 dimensions of E matched by any item of the arm (pooled over its 5 runs), with the per-run mean beside it.
- Novel dimensions: distinct cluster labels of items that match no gold item and are not `known`.
- Stability: the mean pairwise Jaccard of the matched sets of the 5 runs (10 pairs). A pair whose union is empty counts 0.0, and the number of such pairs is reported.
- Classes: recall and precision split by U_NEW_DIMENSION (G01, G12, G13, G16) and U_NEW_VALUE (G02, G04, G05, G07).
- Evaluation budget: judge items, judge calls, human-reviewed items.
- Positions of 20 and above are judged and included in the primary scores (they exist in the sealed files). A secondary view restricted to positions below 20 is reported beside them.

**Human audit** (SP l.14-15): raw agreement on the matched sets, and Cohen's kappa over the per-(item, gold id) binary decisions (kappa is 1.0 when both raters give one identical label throughout). With kappa below 0.6, the report says `UNRELIABLE` and adds the human-corrected scores (the judge's labels with the sampled items' matched sets replaced by the human's). The headline stays the judge-based score and the two are reported side by side. Without human answers the audit is `PENDING_HUMAN_REVIEW` and the gates use the judge-based scores, labelled as such.

## A5.10 Interpretations recorded (no new threshold)
The protocol leaves these open; each is fixed here before any result exists.
1. A rejected clean run rejects every pair of its scenario; a rejected mutant run rejects its pair even if two completed runs show the code; nothing is imputed (A5.3).
2. Rejection and authentication classes are read from the error type name in `attempt_errors`.
3. Invalid scenarios and non-object candidates are not sent to the judge; positions of 20 and above are included in primary discovery scoring, with a positions-below-20 view beside it.
4. The judge's `known` flag removes credit from an item but keeps it in the precision denominator.
5. Items matching only reference dimensions outside E and outside the dev-only pair are valid items with no credit and are not novel.
6. An empty-union pair in stability counts 0.0 and is reported.
7. Kappa is 1.0 if all decisions agree, whatever the margins; the human-corrected variant overrides only the matched sets.
8. The five supplementary rule texts and their spec mapping (A5.7).
9. An UNESTABLISHED served-model identity disables the served-model guard once acknowledged (A5.5).
10. The A4 frozen documents (`step3_pre3e_implementation_map.md`, `step3_pre3e_protocol_to_code_audit.md`) are left as written. `step3_pre3e_a5_notes.md` records what Amendment 5 changed in the rule-to-code mapping.

## A5.11 Unchanged
Not changed: the preregistration, scoring protocol, Amendments 1 to 4, the gold list, K/U classes and set E, the 35 baseline scenarios, the discovery prompts, the DSL, the generation config (c6adad35), the agent and its config (df15b3f0), the oracle, the world, `holdout/runtime.py`, `holdout/`, `bce/`, all Step 3c candidates, statuses, eligibility mapping and holdout commitment, the sealed 3d dataset, the admitted mutant set (T = 6), the denominator of 8, the kill rule, repetitions (3 and 3; drift 1 and 3), budgets (25, 50, 100; Arm A 25 and 35), every gate and numeric threshold, and the bootstrap parameters (10,000, seed 20260311).

## A5.12 Protocol limitations kept (P1-P5)
- **P1. Shared codes inflate dimension credit.** M04, M20 and M22 share the primary code R1B; M10 and M16 share R5. One generic unverified-customer scenario can kill several of them, so dimension-level detection measures that a variant was killed, not that its dimension was targeted. M20 and M22 can also be killed through an exposure code alone. No co-kill table is added.
- **P2. The served model string is a deployment alias** (`gpt-4.1-mini`) and cannot reveal a backend change under it. The drift smoke test is the only behavioural guard and it is weak.
- **P3. The smoke test has zero tolerance.** One stochastic clean violation in 35 single runs flags `POTENTIALLY_INVALID`.
- **P4. Small, selected benchmark.** T = 6 with one variant per dimension, so the bootstrap reflects dimension resampling only; S2 selection favours reliably firing defects (A3.1, A3.2); Arm A is near zero by construction.
- **P5. Stability Jaccard and gate precedence** are recorded interpretations (A4.4).

Also disclosed: a hard kill during a log write can truncate a JSONL log (do not hard-kill; capture the console with `tee`); an exception mid-conversation discards that partial trajectory and the job is re-run; there is no process lock; the degenerate-reply gate is evaluated at the end of each phase; Arm A runs last and mutant order inside a scenario is fixed, so report timestamp ranges.

## A5.13 Tests
`test_step3e_a5.py`: 34 synthetic tests (rejection terminal state and scoring, auth fail-fast, served-model guard, UNESTABLISHED and POTENTIALLY_INVALID gating through `runner.main`, record ancestry and configuration hashes, sealed and history checks and `preflight.verify` tamper cases in temporary git repositories, `scenarios.py` pinning, slot-level accounting beside the preregistered metric, oracle rule-text coverage and mapping, the judge's items, hiding, pooling, batching, prompt, strict parsing, scoring, stability, kappa and end to end). `test_step3e.py` keeps its 53 tests; one guard test now exempts `judge.py`, the only `detect` module that reads gold and the discovery outputs by design. Full suite: 179 tests. No agent call, LLM call or real 3d file is used.

## A5.14 Frozen files
Changed: `detect/rules.py`, `detect/session.py`, `detect/kills.py`, `detect/runner.py`, `detect/preflight.py`, `detect/analysis.py`, `detect/audit.py`, `test_step3e.py`, `experiments/step3/verify_pre3e_freeze.py` (docstring only). New: `detect/judge.py`, `test_step3e_a5.py`, `experiments/step3_amendment5_pre3e.md`, `experiments/step3_pre3e_a5_notes.md`, `experiments/step3/manifests/pre3e_amendment_5.json`, and then `experiments/step3/manifests/pre3e_freeze_a5.json`. Unchanged and re-pinned in the new manifest: `detect/__init__.py`, `detect/drift.py`, `detect/holdout_info.py`, `detect/slots.py`, the Amendment 4 documents and manifests, and `experiments/step3/manifests/pre3e_freeze.json`. `pre3e_freeze_a5.json` supersedes `pre3e_freeze.json`, which stays as the historical record.

## A5.15 Operations
1. `PYTHONPATH=. python experiments/step3/verify_pre3e_freeze.py` must print OK.
2. Drift: `PYTHONPATH=. python -m detect.runner drift`. Report the verdict to the user. **Commit `experiments/step3/results/drift/` unmodified** before detection.
3. Detection: `PYTHONPATH=. python -m detect.runner detect`, with an acknowledgement flag only after the user has been told of a `POTENTIALLY_INVALID`, `UNESTABLISHED` or served-model change. Use `tee` to capture the console. **Commit the detection results unmodified** before analysis and the audit.
4. Analysis: `python -m detect.analysis [--discovery-scores PATH]`. Audit: `python -m detect.audit sample`, then `score`.
5. Judge: `python -m detect.judge prepare`; give each `batch_NNN_prompt.txt` to a fresh subagent once and store its answer unedited as `batch_NNN.json`; give the human packet to a human; `python -m detect.judge score --raw-dir DIR --human PATH`. The judge step is independent of the detection results and may run at any time after the freeze, but it never reads them.
6. **Ancestry.** The git SHA of every 3e record must have the A5 freeze commit (`git_sha` in `pre3e_freeze_a5.json`) as an ancestor.
