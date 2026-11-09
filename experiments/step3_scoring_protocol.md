# Step 3 scoring protocol

Frozen in commit 3a, before any discovery output exists.

## Candidate/scenario to gold matching
- Items judged: for arm C every candidate and every scenario; for arm B every scenario. Arm A is not judged (no discovery claim).
- Pooling: all B and C items from all 5 runs are pooled and shuffled with a fixed seed (20260311). Item ids are opaque (`i0001`...). The judge sees only the item text (candidate fields, or the scenario's fixture, requester, messages, faults, approval and `expected_distinction`). It does not see the arm, run id, confidence, or the targeted `candidate_id`.
- Judge: a fresh Claude subagent with no session context, given `evaluate/judge_prompt_v1.txt`, the 17 gold dimensions (name and values only, no provenance or rationale), and the already-covered list (the dimension names and observed values from the base coverage). It runs once, in batches of at most 40 items. Judge output is stored raw and never edited.
- Match rule: an item matches gold g only if it concretely names or exercises at least one of g's listed values, or the same underlying situational factor. Generic mentions do not match. An item may match several gold items.
- Items matching G03 or G09 are tagged dev-only and excluded from E-based scoring.
- `known` items earn no credit and count against precision.

## Adjudication and agreement
- The experimenter's human reviewer re-judges a random 20% sample of items (seeded sample, fixed before the judge runs) blind to the judge's labels. Agreement on `matched_ids` as a set is reported as raw agreement and Cohen's kappa over per-(item, gold id) binary decisions.
- If kappa < 0.6, all headline discovery numbers are reported as both judge-based and human-corrected on the sample, and flagged as unreliable. Labels are not silently changed.
- The human "would I have written this?" audit covers the `novel_unmatched` clusters, is done after discovery is frozen, and is secondary only. It is recorded as not fully blind.

## Scenario validity and no repair
Every scenario is validated by `bce/dsl.py`. A scenario failing validation is counted as invalid with its reasons and is not repaired, edited or re-generated. Invalid scenarios occupy their slot in the budget order and execute nothing.

## Detection scoring
Kills are computed mechanically from oracle codes by `evaluate/`: the oracle is the existing one, unchanged, never branching on `scenario.id`. No new oracle checks are added in Step 3. The LLM never decides a rule violation.

## Reproducibility metadata
Every run record carries git SHA, provider, model/deployment, configuration, prompt hash, input artifact hashes, timestamp, run id, seed and counts. Output files are never overwritten; a re-run gets a new run id.

---

## Amendment 1 (2026-11-10), made before any discovery, mutant or detection run
Kept consistent with Amendment 1 of `step3_preregistration.md`, which governs. Nothing above is changed.
- **Detection scoring:** the primary unit is the eligible gold dimension. Dimension-level detection rate = dimensions in E with at least one validated variant killed within the budget / 8. Variant-level kill rate is secondary. A per-dimension table is always reported. A variant counts as killed only under the existing 2-of-3 mutant, 0-of-3 clean rule.
- **Class breakdown:** discovery and detection are reported separately for `U_NEW_DIMENSION` and `U_NEW_VALUE` (and `H_HIGHER_ORDER_INTERACTION` if any item ever becomes eligible). The judge is not told the class of any gold item.
- **Evaluation budget:** judge calls, judge items and human-reviewed items are counted separately from the discovery budget, the agent execution budget and token/API cost.
- **Reproducibility metadata:** every run record also carries the hash of the frozen `generation_config.json`.
- **Mutant variants:** only variants validated under the preregistration (A7) are scored. Excluded variants are reported with reasons, and none is replaced after results are seen.
