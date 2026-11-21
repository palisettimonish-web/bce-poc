# Step 3 pre-3e Amendment 5: change-to-code-to-test map

Written 2026-11-21, before the Amendment 5 freeze commit, with the 3d dataset sealed at `646ffb7e2e4cebd5b1e2fcf52fa6a448ef406c94`. It extends `step3_pre3e_protocol_to_code_audit.md` (Amendment 4, left as written); rows 8, 25 and 26 of that audit are refined by the rows below, and every other row stands. Tests are in `test_step3e_a5.py` (34 synthetic tests) and `test_step3e.py` (53); full suite 179. "A5.n" = section of `step3_amendment5_pre3e.md`.

| # | Change | Implementation | Covering test(s) | Status |
|---|---|---|---|---|
| 1 | PROVIDER_REJECTED terminal state (A5.3) | `session.classify_failure`, `Session.ensure`, `Session.have`, `rules.REJECTED_ERROR_TYPES` | `test_classify_failure`, `test_rejected_clean_run_is_terminal_is_never_retried_and_invents_no_outcome` | New rule; interpretation 1 and 2 in A5.10 |
| 2 | Rejected pairs score as no kill | `kills.group_records`, `kills.build_table` (`REJECTED`, `rejected_executions`, `clean_rejected`) | `test_rejected_mutant_run_rejects_that_pair_only_and_the_kill_is_not_imputed`, `test_a_rejected_third_mutant_run_rejects_the_pair_even_when_two_completed_runs_show_the_code` | Interpretation |
| 3 | Rejection stops further runs, curtailment skips it | `runner.process_slot` | the two tests above | Exact to A5.3 |
| 4 | Transport failures stay retryable | `session.Session.ensure` | `test_a_transport_failure_stays_retryable_and_is_not_rejected` (and the A4 resume tests) | Unchanged behaviour |
| 5 | Rejections reported per arm and budget | `analysis.rejection_report` | `test_analysis_reports_rejections_per_arm_and_budget_apart_from_dsl_invalidity` | New report |
| 6 | Auth fail-fast (A5.4) | `session.AuthenticationFailure`, `Session.ensure` | `test_authentication_failure_stops_at_once_is_logged_and_resumes`, `test_main_authentication_failure_stops_with_a_clear_message` | New rule |
| 7 | Served-model guard (A5.5, I1) | `runner.served_guard`, `served_mismatches`, `ServedModelChange`, `run_detection` summary | `test_served_model_guard_stops_unless_acknowledged_or_without_a_baseline`, `test_run_detection_records_baseline_mismatches_and_acknowledgement`, `test_main_served_model_change_stops_and_resumes_only_when_acknowledged` | New rule |
| 8 | UNESTABLISHED model needs acknowledgement (I2) | `runner.main` | `test_main_unestablished_model_needs_acknowledgement_and_disables_the_guard` | New rule |
| 9 | POTENTIALLY_INVALID acknowledgement through `main` | `runner.main` | `test_main_potentially_invalid_drift_needs_acknowledgement` | A4 behaviour, now exercised |
| 10 | Drift once; detection after drift; entry points run end to end with a fake executor | `runner.main` | `test_main_refuses_without_the_freeze_and_without_a_drift_run`, `test_main_drift_then_detect_end_to_end_and_drift_is_never_rerun` | Coverage gap of A4 closed for `runner.main` |
| 11 | Results sealed and history (A5.6, I3) | `preflight.sealed_problems`, `history_problems`, `runner.main`, `analysis.main`, `audit.main` | `test_sealed_and_history_problems_with_a_real_git_repo`, `test_main_stops_on_integrity_problems` | New rule |
| 12 | Record ancestry and frozen hashes (A5.6, I3) | `preflight.record_problems`, `freeze_sha`, `frozen_config_hash` | `test_record_problems_ancestry_and_frozen_hashes` | Exact to A4.7 "must" |
| 13 | New freeze manifest, A4 ancestry, `scenarios.py` pinned (I4) | `preflight.verify`, `preflight.MANIFEST`, `TRACKED_INFRASTRUCTURE` | `test_verify_through_a_temporary_repo_catches_every_tamper_case`, `test_the_real_manifest_pins_scenarios_py_once_frozen` | New rule; the last test is skipped until the manifest exists |
| 14 | Slot-based diagnostic beside the preregistered metric (A5.8, I6) | `analysis.discovery_counts`, `analysis.analyze` | `test_slot_based_diagnostic_sits_beside_the_preregistered_returned_scenario_check` (and the A4 `test_invalid_experiment_check_for_arm_c`) | Additive |
| 15 | Rule text for all 14 oracle codes (A5.7, I5) | `audit.SUPPLEMENTARY_RULE_TEXT`, `SPEC_RULE_OF`, `full_rule_text` | `test_every_oracle_code_has_rule_text_and_no_text_names_a_code`, `test_supplementary_text_never_overrides_the_catalogue_and_maps_to_real_spec_rules` | Interpretation (wording) |
| 16 | Judge items, hiding, pooling, batching, sample (A5.9) | `judge.load_items`, `pool`, `batches`, `human_sample`, `render_items` | `test_judge_items_exclude_invalid_scenarios_and_non_object_candidates_and_flag_positions_over_19`, `test_judge_items_hide_ids_confidence_arm_and_position_from_the_judge`, `test_judge_pooling_batching_and_sample_are_fixed_by_the_seed` | Exact to SP l.6-8 and l.14; item scope is interpretation 3 |
| 17 | Frozen judge prompt filled with gold and coverage | `judge.build_prompt` | `test_judge_prompt_is_the_frozen_template_with_gold_and_covered_filled_in` | Exact |
| 18 | Strict parsing, nothing repaired | `judge.parse_batch` | `test_judge_parser_is_strict_and_repairs_nothing` | Exact to SP l.8 |
| 19 | Precision, recall, novelty, stability, classes, dev-only tags | `judge.arm_scores`, `discovery_scores` | `test_judge_scores_precision_recall_stability_novelty_and_known_handling`, `test_judge_position_sensitivity_and_dev_only_exclusion` | Exact to SP l.11-13; empty-union and `known` handling are interpretations |
| 20 | Human agreement, kappa, human-corrected variant | `judge.agreement`, `human_corrected`, `full_report` | `test_judge_human_agreement_kappa_and_the_human_corrected_variant` | Exact to SP l.14-15 |
| 21 | `prepare` and `score` end to end, exclusive-create outputs, gate input format | `judge.prepare`, `judge.score` | `test_judge_prepare_and_score_end_to_end_on_synthetic_files` | Synthetic only |
| 22 | Judge isolation (2.19) | imports of `detect/judge.py` | `test_judge_touches_no_holdout_mapping_detection_result_or_oracle_code` | Static check |
| 23 | No threshold, repetition, budget or denominator change | `rules` | `test_a5_constants_and_unchanged_preregistered_numbers`, A4 `test_frozen_constants` | Exact |

## Explicit checks
| Check | Result |
|---|---|
| Use of 3d content | None. The judge tests write synthetic scenario and candidate files in `tmp_path`. No file under `experiments/step3/scenarios/`, `normalized/` or `discovery/` was opened. |
| Use of 3e results | None exist. `experiments/step3/results/` is empty. |
| Fabricated outcomes | None. A rejected job has no outcome; its pairs are `REJECTED`, with no kill of either kind. |
| Changed kill rule, denominator, mutants, reps, budgets, gates, thresholds | None. |
| Replaced preregistered metric | None. The slot-based diagnostic is added beside it. |

## Coverage gaps (disclosed)
- `analysis.main`, `audit.main`, `judge.main`, `runner._executor` and the real `preflight.verify` against the real manifest run only after the freeze (the verifier is run on the frozen tree and on tampered clones). `runner.main` and `preflight.verify` are exercised in synthetic tests with injected dependencies and temporary git repositories.
- The judge has never been run on real items; its first real run is after the freeze.
- Client-level retries and real provider error types are known only from the Step 3c log (`ClientAuthenticationError`) and the OpenAI client's documented classes; `REJECTED_ERROR_TYPES` and `AUTH_ERROR_TYPES` are matched by name.
