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
