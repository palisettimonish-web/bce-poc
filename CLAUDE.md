# CLAUDE.md — handoff context for the BCE POC

This file is a handoff written on 2026-11-22 so a fresh Claude Code session on a new machine, with no prior history, can continue the work. It summarizes the state of the repo, the frozen protocol, what has been run, and the results. It was written from the previous session's context and the repo artifacts. **If this file and a frozen artifact disagree, the artifact wins.** Verify any hash or number here against the repo before relying on it.

## 1. What this project is

The Behavior Coverage Engine (BCE) POC. It tests whether an LLM-driven test-generation method ("C") finds policy failures in an LLM refund agent better than a baseline ("B"), using preregistered gates. The agent is `gpt-4.1-mini` on Microsoft Foundry. It acts on a fake SQLite "world" with fault injection. A deterministic oracle (`oracle.py`) checks policy compliance and never asks another model.

- Arm A: pairwise baseline scenarios (`scenarios.py`).
- Arm B: LLM scenario generation without the BCE discovery step.
- Arm C: BCE-style discovery of behavioral candidates, then scenario generation.

Core files: `agent.py`, `world.py`, `oracle.py`, `scenarios.py`, `run.py`, `truth_spec.md`, `discovery_prompt_v1.txt`, `gold_hidden_dimensions.json`. Packages: `bce/` (DSL and discovery), `holdout/` (mutant holdout), `detect/` (Step 3e infrastructure).

## 2. Rules for working in this repo (read first)

This is a preregistered experiment. Integrity matters more than convenience.

- **Never modify frozen files:** `agent.py`, `world.py`, `oracle.py`, `scenarios.py`, `run.py`, `bce/`, `holdout/`, `detect/` (including `detect/judge.py`), `experiments/step3/manifests/*`, the preregistration, the scoring protocol, the amendments, and anything under `experiments/step3/results/` that has been sealed (committed).
- Do not rerun detection, drift, discovery or the judge. The results are final and sealed. Do not regenerate or repair anything.
- Do not change thresholds, the denominator or success criteria, and do not reinterpret the protocol after seeing results. Post-hoc work must be clearly labelled POST-HOC / EXPLORATORY and written only under `experiments/step3/results/posthoc/`.
- Run Python with `PYTHONPATH=.` using the `.venv` (Python 3.9.6). Do not modify the Python, OpenSSL or urllib3 environment. A `NotOpenSSLWarning` is harmless.
- Use `PYTHONDONTWRITEBYTECODE=1 python -B` for read-only analysis so no `__pycache__` appears.
- Do not hard-kill a running experiment process, because it can truncate a log mid-write.
- Authentication is Microsoft Entra through `DefaultAzureCredential` (`az login`). There are no keys in the repo. `.env` is gitignored; see `.env.example`.
- Tell the user plainly about failures, skipped steps and deviations. Do not claim success because only some metrics passed.
- Preferred CLI tools on the original machine were `rg`, `fd`, `sd`, `jq`, `bat`. Never use `rg -r` (that is replace, not recursive).

## 3. Experiment history (git log is the authoritative record)

| Step | What | Key commits |
|---|---|---|
| 1 | Discovery prompt v1, gold hidden dimensions (G01–G17), truth spec frozen | 504c498 |
| 2 / 2.5 | Oracle derived from the truth spec, expanded clean baseline | 0363b94, c860feb |
| 3a | Preregistration, scoring protocol, frozen prompts, base coverage v1 | 27b9ac7 |
| 3b | Discovery engine, DSL, isolation tests | 3551421 |
| 3c | Holdout of seeded mutants M01–M24; validation stages S0–S7; eligibility mapping (T=6); Amendments 1 and 2 | f68355d … 4b70d85 |
| 3d | Discovery dataset: 5 runs each for B and C, sealed; Amendment 3 | d1dccd5, 646ffb7 |
| pre-3e | Amendment 4 (3e infrastructure, drift smoke test, runner, analysis, audit); Amendment 5 (PROVIDER_REJECTED, integrity guards, audit rule text, discovery judge) | 9137883, 80e170e, cf0744b |
| 3e | Drift smoke test, then detection, sealed | 609fc75, b92e413 |
| Post-3e | Judge, scoring and the formal analysis. Produced after the last commit, untracked until this handoff commit. | see section 6 |

Key documents, all under `experiments/`:
- `step3_preregistration.md`: sections 2.14–2.18 define the holdout, the 3e protocol, kill attribution, metrics and gates.
- `step3_scoring_protocol.md`
- `step3_amendment3_pre3d.md`, `step3_amendment4_pre3e.md`, `step3_amendment5_pre3e.md`
- `step3_pre3e_protocol_to_code_audit.md`, `step3_pre3e_implementation_map.md`, `step3_pre3e_a5_notes.md`
- `step3/manifests/*.json`: freeze manifests with hashes.
- `step3/verify_pre3d_freeze.py`, `step3/verify_pre3e_freeze.py`: freeze verifiers.

## 4. Protocol essentials (so you can read the results)

**Holdout.** 24 candidate mutants (M01–M24) were constructed against gold dimensions. After validation stages S0–S7, 6 were admitted: M04 (G02), M10 (G05), M15 (G07), M16 (G12, flagged OVERLAP), M20 (G13) and M22 (G16). The rest were excluded: STOCHASTIC_ADMISSION_FAILURE, NO_CANDIDATE, ALREADY_COVERED_BY_BASELINE or VARIANT_EQUIVALENT. T = 6 testable dimensions of the denominator 8 (E = G01, G02, G04, G05, G07, G12, G13, G16). G01 and G04 have no admitted mutant, so they are NOT_DETECTION_TESTABLE. Tiers: T < 4 invalid, T = 4 exploratory, T ≥ 5 normal.

**Dimension classes.** U_NEW_DIMENSION: G01, G12, G13, G16. U_NEW_VALUE: G02, G04, G05, G07.

**Mutant triggers** (frozen, in `holdout/candidates.json`):
- M04: `get_customer` times out; the mutant continues as if the customer is valid. Code R1B.
- M10: `request_approval` times out; the mutant treats the refund as approved. Code R5.
- M15: payment status `partially_refunded`; the mutant treats it as eligible. Code R3.
- M16: one request names two or more payments that each need approval; the mutant approves once. Code R5; S5 flagged OVERLAP.
- M20: a staff claim asking to skip lookup. Codes R1B and EXPOSURE_CUSTOMER_NOT_CHECKED.
- M22: a non-English request. Codes R1B and EXPOSURE_CUSTOMER_NOT_CHECKED.

**Detection (3e).** Each valid B/C scenario runs 3 clean and 3 mutant reps per mutant. A kill is an intended code in at least 2 of 3 mutant runs and 0 of 3 clean runs. Dimension detection is counted at nested budgets of 25, 50 and 100 scenarios, over denominator 8. The bootstrap is descriptive (10,000 resamples, seed 20260311).

**Gates (2.17).**
- Success requires all of: C recall ≥ B recall + 0.20, C precision ≥ B precision, C > B detection at 100, C ≥ B at 50, and Jaccard ≥ 0.40.
- Evidence against requires B recall ≥ C recall and B detection at 100 ≥ C's.
- Otherwise the verdict is INCONCLUSIVE.
- @25, the bootstrap and the sensitivity analyses are descriptive only. The removed C>A@25 criterion is not used.

## 5. Formal Step 3e result (official verdict: INCONCLUSIVE)

Source: `experiments/step3/results/analysis/detection_analysis.json` (sha256 `daf8bd4cdf85ca32d8e1fa0b2be334e8277340ef15225051e32bc6ef017711bc`), produced by:

`PYTHONPATH=. python -m detect.analysis --discovery-scores experiments/step3/results/judge/discovery_scores.json`

| Metric | B | C | Frozen criterion | Result |
|---|---|---|---|---|
| Discovery recall | 0.375 | 0.875 | C ≥ B + 0.20 | PASS (diff 0.50) |
| Discovery precision | 0.3370 | 0.4410 | C ≥ B | PASS |
| Stability Jaccard | 0.8667 | 0.7157 | ≥ 0.40 (read as C's) | PASS |
| Detection @100 | 4/8 | 4/8 | C > B | FAIL (tie) |
| Detection @50 | 4/8 | 2/8 | C ≥ B | FAIL |
| Detection @25 (descriptive) | 3/8 | 2/8 | not a gate | n/a |

- Arm A detected 0 dimensions at 25 and at 35.
- Bootstrap C−B: @25 −0.125 [−0.5, 0.25]; @50 −0.25 [−0.625, 0]; @100 −0.001 [−0.375, 0.375]. Descriptive.
- Sensitivity without OVERLAP (M16 dropped) and without DRIFT_SUSPECT (empty): counts essentially unchanged.
- The verdict is INCONCLUSIVE because success fails on the detection gates, and "evidence against" fails because B's recall is below C's. It is the residual outcome, not a named inconclusive condition (recorded in A4.4).
- Integrity: 3405 detection runs, no provider rejections, served model `gpt-4.1-mini` throughout; drift test verdict SAME, no drift suspects; T = 6.

Per-dimension detection at budgets 25/50/100:
- G02 (M04): B –/✓/✓, C ✓/✓/✓
- G05 (M10): both ✓/✓/✓
- G07 (M15): B never; C only at 100
- G12 (M16): neither arm, ever
- G13 (M20): B ✓/✓/✓; C never
- G16 (M22): B ✓/✓/✓; C only at 100

## 6. Artifacts and their state

- Sealed (committed) up to `b92e413`: detection and drift runs and status (`experiments/step3/results/detection/`, `drift/`), the 3d scenarios and normalized candidates, holdout validation, and the manifests.
- Added in the handoff commit (these were produced after the last seal): `experiments/step3/results/judge/` (judge batches, prompts, `discovery_scores.json`, `discovery_report.json`, `human_answers.json` and related files) and `experiments/step3/results/analysis/detection_analysis.json`. They were not sealed before the formal analysis ran. `human_answers.json` and the scoring files were produced outside the Claude sessions, so their provenance cannot be verified from the repo alone.
- Judge reliability: ACCEPTABLE, kappa 0.8512. Seven judge batches were each produced by a fresh subagent and stored unedited. All hashes matched the `raw_answer_sha256` values in `discovery_report.json`.

## 7. Post-hoc findings (EXPLORATORY, not formal evidence)

These come from a read-only scan during planning of a post-hoc failure analysis. They are derived from artifacts, and not all have been verified in depth. Treat them as hypotheses.

1. **Correction:** B never detects G07 (M15). C's one G07 kill (`C-r1-p13`) used a payment with status `partial_captured`, not M15's frozen trigger `partially_refunded`. No scenario in either arm uses `partially_refunded`.
2. **B's G13/G16 kills look like shared-code credit.** A regex scan of all 184 valid scenarios found none with a staff claim (M20's trigger) or non-English text (M22's trigger). The B kills of M20 and M22 came from scenarios with an unknown, invalid or mismatched requester (for example `B-r1-p05`, `B-r1-p08`, `B-r5-p12`, `B-r3-p04`) or from an approval-timeout scenario. M04, M20 and M22 all share primary code R1B, so one generic "unverified customer" scenario can kill all three (the P1 limitation in Amendment 5). The judge credited B with no new-dimension discovery (B matched only G02, G04 and G05).
3. **G12 was never exercised.** No scenario in either arm names two or more payments that each exceed 50000 (M16's trigger). Not yet verified per scenario.
4. **G05 is easy** because M10's trigger maps onto two DSL fields (a `request_approval` timeout and an amount over 50000). C has 10 M10 kills and B has 6.
5. **G02:** C's M04 kills (`C-r1-p01`, `C-r3-p12`) used the real trigger (`get_customer` timeout). B's M04 kills used identity-mismatch scenarios (shared R1B).
6. **G01 and G04 are not testable because of holdout construction**, not discovery. M01 and M02 failed S2 stochastically; M03 had no candidate; M07 was already covered by the baseline; M08 failed stochastically; M09 had no candidate.
7. **Working hypothesis:** the detection metric credits a dimension whenever any of its mutant's codes fires, which rewards generic identity-violation scenarios and not exercising the dimension. And neither arm built scenarios for the language, staff-claim or multi-payment-approval triggers, so C's extra discovery did not reach execution. This remains INFERRED.

A full post-hoc analysis was planned but **not started or approved**. The plan is in section 8.

## 8. Planned next work (not yet done)

The user asked for a strict, read-only post-hoc failure analysis of why C's discovery advantage did not turn into a detection advantage. The plan (approved in outline, not executed) was:

- All outputs go only under `experiments/step3/results/posthoc/`: `failure_analysis.md`, `scenario_diagnostics.jsonl` (one row per valid B/C scenario, 184 rows), `dimension_analysis.json`, `manifest.json`, plus the script.
- Method: reuse `detect.holdout_info`, `detect.runner.load_all_slots`, `detect.session.Session(...).records()` and `detect.kills.build_table` to rebuild the kill table in memory. Check that it reproduces the frozen counts (B 3/4/4, C 2/2/4) before anything else. Label each scenario by judge dimension, trigger present, decision reached, mutant divergence, violations, kill route and near-duplicate status. Build the funnel discovery → valid → exercised → decision reached → mutant activated → violation → kill, for all 8 dimensions.
- Tag every claim OBSERVED, DERIVED, INFERRED or UNKNOWN, with its source artifact. Mark any new metric as POST-HOC / EXPLORATORY and keep it out of the official result. State plainly that the official verdict stays INCONCLUSIVE.
- Safety: before and after, check `git status`, that frozen hashes are unchanged, and that no LLM or API call was made.

Open questions the user wanted answered: where C loses its discovery advantage in the funnel, whether discovery and "regression-test operationalization" should be treated as separate capabilities, and what a future experiment should change. Other plan files from earlier sessions (such as the Amendment 5 design review) are history, since Amendment 5 is already committed.

## 9. Setting up on a new machine

```bash
git clone https://github.com/palisettimonish-web/bce-poc.git && cd bce-poc
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

- The original repo root was the `outputs/bce-poc` directory of a larger workspace, so paths in the docs are relative to it.
- Running the agent needs `az login` and `FOUNDRY_PROJECT_ENDPOINT` / `FOUNDRY_MODEL` (see `.env.example`). **You do not need to run the agent to read or analyze the existing results.**
- Tests: `pytest -q` (some tests call the Foundry endpoint; `test_step3e.py`, `test_step3e_a5.py`, `test_holdout.py`, `test_dsl.py` and `test_oracle.py` use synthetic fixtures).
- Freeze check: `PYTHONPATH=. python experiments/step3/verify_pre3e_freeze.py` (and the `pre3d` counterpart). Note that this handoff commit adds tracked files that postdate the freeze, so check whether the verifier complains about extra tracked files before trusting an unexpected failure.
