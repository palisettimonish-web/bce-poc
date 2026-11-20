# Step 3 Amendment 4 (pre-3e infrastructure)

Dated 2026-11-21. Record ID `step3-pre3e-amendment-4`. Made after the 3d dataset was sealed and before any 3e call. It supplements Amendments 1 to 3 and rewrites none of them. `step3_preregistration.md` (d66db73d) and `step3_scoring_protocol.md` (4ec1dded) are untouched. Evidence for the rule-by-rule mapping is in `step3_pre3e_protocol_to_code_audit.md`; the design is in `step3_pre3e_implementation_map.md`.

## A4.1 Why this amendment exists
The pre-3e preflight found that no frozen 3e runner or command existed and that the 2.15 drift smoke test had no code. The user confirmed the finding and authorized building and freezing that infrastructure as a methodological implementation step, not an analysis step. This amendment is the dated record that 2.20 (line 435) requires.

## A4.2 Provenance statement
1. The 3d dataset was sealed at commit `646ffb7e2e4cebd5b1e2fcf52fa6a448ef406c94` (`step3d: seal discovery dataset`). That commit is unchanged by this work.
2. The 3e implementation was authored AFTER the 3d dataset existed.
3. The implementation was derived only from the frozen protocol: the preregistration, the scoring protocol, Amendments 1 to 3, the frozen holdout definitions, candidates and mutants, the oracle, the agent configuration and the frozen 3e rules.
4. No 3d content, quality, counts, B/C differences or results were used. No generated scenario was opened or read to design any rule, no B/C candidate count, missing-slot pattern or invalid-scenario pattern was inspected, and no B-versus-C outcome was assumed. The code reads sealed scenario files only structurally: the stored `valid` flag (re-checked with the frozen `dsl.validate`), the DSL-to-world conversion, and the per-run token totals for the cost metric.
5. All tests use synthetic fixtures and a scripted fake executor. No agent call, LLM call or real 3d scenario was used. No drift smoke test, 3e detection or oracle audit has been run, and no 3e result exists.
6. The drift smoke test (2.15) must run, and be recorded, before any 3e detection run. The detection runner refuses to start otherwise.
7. The runner, analysis code, audit sampler, tests, verifier and manifests listed in A4.6 are frozen by this amendment.
8. Any change to those files after the freeze requires a new explicit amendment (2.20 line 435).

## A4.3 Unchanged
Not changed: the preregistration, the scoring protocol, Amendments 1 to 3, the gold list, K/U classes and set E, the 35 baseline scenarios, the discovery prompts, the DSL, the generation config (c6adad35), the agent and its config (df15b3f0), the oracle, the world, all Step 3c candidates, statuses, eligibility mapping and the holdout commitment, `bce/`, `holdout/`, the sealed 3d dataset, the kill rule, repetitions, budgets, gates, every numeric threshold and the bootstrap parameters.

## A4.4 Interpretations recorded (no new threshold)
The protocol leaves these points open. Each is fixed here before any 3e result exists. They add no threshold and change no preregistered number.
1. **Gate precedence.** Success if every success condition holds; otherwise evidence against if its condition holds; otherwise inconclusive. A C advantage at budget 100 only, with ties at 25 and 50, meets every success condition and also matches the inconclusive clause "advantage at only one budget". Success takes precedence, and the output carries `inconclusive_by_named_condition = true` so the overlap is visible. Against must precede the small-recall-difference clause, since otherwise against could almost never be reached.
2. **Stability Jaccard.** "Stability Jaccard >= 0.4" is read as arm C's value. B's is reported alongside.
3. **Discovery scores.** Recall, precision and stability Jaccard come from the judge step. It is not part of this build. The gate code takes them from an optional input file and reports `PENDING_DISCOVERY_SCORES` without it. The detection side is always computed. No gate verdict is final until that input exists.
4. **Percentile.** Linear interpolation between order statistics (the numpy default), on 10,000 resamples, seed 20260311. The bootstrap covers B, C and C minus B only; Arm A is descriptive.
5. **Oracle audit.** A fresh `random.Random(20260311)` per stratum over lexicographically sorted unit ids; packet presentation order shuffled with the same seed; rule codes shown to the reviewer as neutral labels. Agreement means: stratum 1, the reviewer confirms an intended code; stratum 2, the reviewer's set equals the oracle's set; stratum 3, the reviewer's set is empty. Arm A is not audited.
6. **Cost per true failure.** Generation tokens pro rata by slots used, with the all-runs total also reported, plus agent tokens of the scenarios in the budget.
7. **Resumption.** Runs are append-only and keyed by stage, variant, subject, instance and repetition. A rerun skips completed keys. Curtailment is recomputed from the log, so it is deterministic. Output files are written with exclusive-create and never overwritten.
8. **Degenerate-reply gate.** The more-than-10% empty or max-turn check is evaluated at the end of each phase (drift, detection), as in the 3c engine.
9. **Drift handling.** A `POTENTIALLY_INVALID` drift verdict stops the detection runner unless `--acknowledge-potentially-invalid` is passed (2.15 requires the user to be told before 3e). A served model that cannot be established is recorded as `UNESTABLISHED`, never as the same model. The configured model name is not treated as proof of served-model identity.
10. **Run order.** B and C are interleaved slot by slot, then Arm A. Curtailment needs the three clean runs first within each scenario.

## A4.5 Limitations
- The judge step (recall, precision, stability Jaccard) is not implemented here (A4.4 item 3).
- The command-line entry points and the git-dependent verifier are not run by the synthetic suite (see the audit report, coverage gaps). The verifier is checked by running it after the freeze, and on a tampered copy.
- Served-model identity can be established only if the provider returns a model string per response. If it does not, the drift record says `UNESTABLISHED` and the limitation stands.
- The T = 6 pilot limitation of A3.1 is unchanged and applies to every 3e result.

## A4.6 Frozen files
New, none replaced: `detect/__init__.py`, `detect/rules.py`, `detect/slots.py`, `detect/holdout_info.py`, `detect/kills.py`, `detect/session.py`, `detect/drift.py`, `detect/runner.py`, `detect/preflight.py`, `detect/analysis.py`, `detect/audit.py`, `test_step3e.py`, `experiments/step3/verify_pre3e_freeze.py`, `experiments/step3_pre3e_implementation_map.md`, `experiments/step3_pre3e_protocol_to_code_audit.md`, `experiments/step3_amendment4_pre3e.md`, `experiments/step3/manifests/pre3e_amendment_4.json`, and then `experiments/step3/manifests/pre3e_freeze.json`.

## A4.7 Operations
- **Pre-flight.** Every `detect` command first runs `detect.preflight.verify`, which runs the pre-3d verifier, checks that the freeze commit and the sealed 3d commit are ancestors of HEAD, checks every infrastructure hash in the working copy and at the freeze commit, checks the 30 sealed 3d artifacts against `git show <sealed commit>`, checks that no tracked file under `detect/` is missing from the manifest, and requires a clean working tree outside `experiments/step3/results/`.
- **Order.** (1) `PYTHONPATH=. python -m detect.runner drift`; (2) the user is told the drift verdict; (3) `PYTHONPATH=. python -m detect.runner detect`; (4) `python -m detect.analysis`; (5) `python -m detect.audit sample`, then `score`. The drift test is never re-run once recorded.
- **Ancestry.** The git SHA of every 3e run record must have the pre-3e freeze commit (`git_sha` in `pre3e_freeze.json`) as an ancestor, in addition to the 3c and pre-3d freeze commits.
