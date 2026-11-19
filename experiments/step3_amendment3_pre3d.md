# Step 3 Amendment 3 (pre-3d)

Dated 2026-11-19. Made after the 3c holdout freeze (`holdout_freeze.json`, commit 4b70d85) and before any 3d call. No 3d output exists. This is the new, dated amendment that 2.20 (line 435) requires for any later change. It supplements Amendment 2 and does not rewrite it: `step3_preregistration.md` (d66db73d) and `step3_scoring_protocol.md` (4ec1dded) are untouched and remain pinned by `prereg_amendment2_freeze.json`. Every result is also reported under Amendment 2 as written. Evidence for each clause is in `step3_pre3d_audit_report.md`.

## A3.0 Unchanged
Not changed by this amendment: the gold list, the K/U classes and set E, the 35 baseline scenarios, the base coverage, the discovery prompts (v2 and generic) and the DSL, the generation config, the agent and its config, the oracle, the world, all Step 3c candidates, statuses, eligibility mapping and the holdout commitment, the runner and every other file under `bce/` and `holdout/`, the kill rule, the repetitions, the budgets, the gates and every numeric threshold (including 0.2, 0.4, T = 4 and T = 5), the bootstrap, and Amendment 2 itself.

## A3.1 Claim scope at T = 6
- The holdout has T = 6 testable dimensions (G02, G05, G07, G12, G13, G16). G01 and G04 are `NOT_DETECTION_TESTABLE` and stay in the denominator of 8 (2.11). The maximum attainable dimension-level detection rate is therefore 6/8 = 0.75 for either arm.
- Each testable dimension has exactly one admitted variant, so variant-level and dimension-level results coincide, and the bootstrap's within-dimension resampling is degenerate; its interval reflects resampling of dimensions only. This is stated here so it is not read as extra replication.
- T >= 5 gives normal reporting under 2.17. That label is unchanged. This amendment adds that the whole of Step 3 is a pilot on one toy agent with a small hidden benchmark whose mutants were built from the evaluator's own gold list (2.21). A verdict of "success for BCE" means the preregistered POC gates were met in this pilot. It is not confirmatory evidence for the full BCE thesis and is not a significance claim (A8).
- Results by class are descriptive. The six testable dimensions are three NEW_DIMENSION (G12, G13, G16) and three NEW_VALUE (G02, G05, G07), one variant each. No inference is drawn from a difference between the classes.

## A3.2 Limitation: S2 selection
Of 19 candidates that entered S2, 9 passed and 10 were `STOCHASTIC_ADMISSION_FAILURE`. Admission required the primary code in at least 7 of 10 runs on every instance (2.6). The holdout therefore consists of defects that fire reliably on their trigger, and intermittent or low-probability defects are under-represented. Detection rates describe reliably firing prompt-level defects of this single agent only. There are no replacements (2.12). The 3e aggregation rule is unchanged (2.16: 3 clean and 3 mutant repetitions per pair, attributable kill at 2 of 3).

## A3.3 S7 is a sanity check, not validation
S7 was a blinded human construct-validity sanity check on the six S6 survivors (2.10). It is not an independent validation of the oracle or the mutants, claims no statistical independence, and is not evidence that the mutants are representative of real defects or of the space of agent failures. All 36 answers were "yes", so S7 removed no candidate, there was no negative control, and it carries no discrimination evidence. This amendment does not verify who performed the review or what they knew beyond 2.21 line 442; the operator records that in the final report.

## A3.4 Sensitivity analyses (clarifies 2.16 line 386)
- **Which.** (a) without `OVERLAP` variants (M16, the only variant of G12); (b) without `DRIFT_SUSPECT` variants, if any.
- **How.** Each recomputes the same detection metrics at budgets 25, 50 and 100 with the denominator fixed at 8. A dimension left with no variant counts as not detected for both arms and is labelled `NOT_DETECTION_TESTABLE` in that analysis. Rates over testable dimensions only are also shown. T' is reported (T' = 5 for (a)).
- **Status.** Secondary and descriptive. They enter no gate and do not replace the primary analysis, which includes all admitted variants. If a sensitivity result differs in direction from the primary one, both are reported side by side and the primary verdict is not relabelled.

## A3.5 Oracle audit on generated scenarios (procedure frozen now, executed after 3e)
- **When.** After the 3e agent runs exist and before the final report. It does not feed back into any kill, metric, gate, scenario or oracle. The sampling script is committed before it runs and implements exactly the text below.
- **Reviewer.** The experimenter's human reviewer, who knows the hypothesis and is not independent (as 2.21). The reviewer sees, for one repetition, the scenario parameters, the tool calls and results, the ledger and the replies, together with the written oracle rule text. They do not see the oracle's codes, the arm, the budget position or the mutant identity, and judge which rules the trace violates.
- **Strata.** Units are drawn from arms B and C pooled, without replacement, using `random.Random(20260311)` over unit ids sorted lexicographically, and up to 20 per stratum (all if fewer):
  1. attributable-kill (scenario, mutant) pairs: the lowest-numbered mutant repetition containing the intended code;
  2. clean-agent runs where the oracle emitted any code: the lowest-numbered such repetition;
  3. runs (clean or mutant) where the oracle emitted no code: repetition 1.
- **Reporting.** Per stratum: units, units where the reviewer's judgement agrees with the oracle, and a list of disagreements with reasons. Stratum 1 gives the oracle's precision on kills, stratum 2 on natural failures, stratum 3 an estimate of missed violations.
- **No rescoring.** The oracle and all scores stay as computed. If the reviewer judges any audited attributable kill not to be a true violation, the headline detection numbers are additionally reported with those kills removed, labelled as a sensitivity analysis. No threshold is attached.
- **Existing controls.** The clean-agent control (3 clean repetitions per scenario), the fixed oracle and the 2.15 drift smoke test stay as frozen.

## A3.6 Pre-3d operations
- **Pre-flight.** The runner does not call `seal.verify_freeze`, and no manifest pinned `bce/*.py` before this amendment. Before the first 3d call, and before each later one, the operator runs `python -m holdout.seal` and `PYTHONPATH=. python experiments/step3/verify_pre3d_freeze.py`; both must print OK. The second checks every hash in `experiments/step3/manifests/pre3d_freeze.json` (including the assembled B and C prompts at n = 20 and the input boundary), that the pre-3d freeze commit is an ancestor of HEAD, and that the frozen files are unmodified.
- **Run order.** The ten discovery runs are executed in the order B1, C1, B2, C2, B3, C3, B4, C4, B5, C5, so that provider drift over time is not aligned with one arm. Re-invocation after a call that returned no response stays as 2.14.
- **Ancestry.** The git SHA of every 3d run record must have the pre-3d freeze commit (the `git_sha` in `pre3d_freeze.json`) as an ancestor, in addition to the 2.20 requirement for the 3c freeze commit.
- **Served model.** `bce/run_discovery.py` records the configured model name, not the served model string, and does not store the response object. The runner is not changed. The raw output hash and text are recorded, and drift between discovery runs cannot be audited from the records; this is a disclosed limitation.

## A3.7 Disclosures added
- The DSL (`bce/dsl.py`), the discovery prompts and the coverage module were written after the gold list was frozen and seen (commit 27b9ac7 after 504c498) and never edited. Line 85 already discloses this for the v2 prompt; it applies equally to the DSL and coverage module.
- The DSL is identical for B and C. A review of its fields (audit report section 2) found no field or enum value that names a set-E value; one element (fault phase `after`) describes the dev-only G09 and a few others (an unlisted requester id, fault mode `malformed`) are mildly revealing. Any such leakage is common to both arms: it cannot bias C vs B but can inflate absolute discovery claims for either arm.
- B and C receive identical inputs except for the coverage summary (derived mechanically from the same 35 scenarios), the gap-analysis framing and the two-stage output. These are the treatment (line 85 states the framing/extra-input confound). Nothing is changed.
- An independent re-classification of all 17 gold dimensions (9 NEW_DIMENSION, 8 NEW_VALUE, 0 HIGHER_ORDER_INTERACTION; audit report section 4) agrees with the frozen classes for all eight members of E. The frozen classes govern.
- `experiments/step3_pre3d_audit_report.md` is the evidence for this amendment and is hashed in `pre3d_amendment_3.json`.

## A3.8 Files
Added, none replaced: `experiments/step3_amendment3_pre3d.md`, `experiments/step3_pre3d_audit_report.md`, `experiments/step3/verify_pre3d_freeze.py`, `experiments/step3/manifests/pre3d_amendment_3.json`, and then `experiments/step3/manifests/pre3d_freeze.json`.
