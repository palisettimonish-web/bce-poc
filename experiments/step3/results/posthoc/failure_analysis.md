# Step 3e post-hoc failure analysis

**POST-HOC / EXPLORATORY. Official Step 3e verdict: INCONCLUSIVE. This analysis does not alter the official result.**

Evidence tags: **[OBS]** read directly from a sealed artifact; **[DER]** computed from artifacts by `posthoc_analysis.py` (deterministic, no LLM, no network); **[INF]** inference that is not shown by an artifact; **[UNK]** the artifacts cannot decide it.
Every number below comes from `dimension_analysis.json` / `scenario_diagnostics.jsonl` (both produced by the script next to this file) unless another source is named.
All "static" rules (what counts as a trigger, as "exercising" a dimension, as a sibling activation) are post-hoc heuristics written for this report. None is a preregistered metric.

---

## 1. Executive finding

1. **C's discovery advantage is real at the judge level and did not reach execution for the mutated triggers.** The judge credited C with E-dimensions G01, G02, G04, G05, G07, G12, G16 and B with G02, G04, G05 [OBS, `judge/discovery_report.json`]. For four of the six detection-testable dimensions (G07/M15, G12/M16, G13/M20, G16/M22) the frozen trigger is present in **0 of 184** valid scenarios, in either arm [DER].
2. **Every official detection of G07, G13 and G16 is off-trigger.** The kills come from scenarios with no frozen trigger and no runtime activation of the mutant's edit path [DER].
   - B's G13 (4 scenarios) and G16 (6 scenarios) kills, and C's G16 kill (`C-r4-p16`), are R1B/EXPOSURE kills through codes shared with M04 [DER].
   - C's single G07 kill (`C-r1-p13`) is a semantic near-miss: `partial_captured` instead of the frozen `partially_refunded`. R3 is not shared, so this is not a shared-code kill [DER].
3. **The official @50 gap (B 4/8, C 2/8) is entirely G13 and G16, and both are B's off-trigger kills.** Dimensions with kills that involve the trigger or a sibling fault value are G02 and G05 (and G02 only at @100 for B) [DER].
4. **Where C does exercise the trigger, it does well.**
   - M04 (G02): 2 of 2 frozen-timeout scenarios kill, both with 3/3 mutant hits and 0 clean hits.
   - M10 (G05): 4 of 5 frozen-timeout scenarios kill [DER].
   - So the sensitivity of the agent and the kill rule is not the main bottleneck when the trigger is built (Class 3 is minor).
5. **Strongest evidence-backed explanation.** Two mechanisms compound.
   - **(a) Value-level operationalization gap, mostly invisible to the judge.** The judge matches dimensions, but the mutants target one value of a dimension. C was credited with G16 through "multiple requests in one message", not through non-English, which is M22's value. C's G12 scenarios pair at most one payment above 50000, while M16 needs two. C's G07 candidate listed `partially_refunded` but the scenario used `partial_captured`. No candidate in either arm mentions staff claims or pressure (G13) [OBS].
   - **(b) Detection credit that is not tied to the mutant's trigger.** M04, M20 and M22 append a sentence to rule 1 and share R1B/EXPOSURE, so any scenario that makes the agent verify less can kill all three. B's scenario set contained more of the scenarios in which the clean agent refuses safely and the edited agent does not (see section 12) [DER + INF].
6. **What this does not show.** It does not show that C "failed", that B was better, or that the BCE thesis is false. Both arms generated English, templated text only. Whether C-style discovery would produce trigger-bearing scenarios under a generation prompt that asks for message-text variation is **untested** [UNK].
7. **Counterfactual (exploratory, section 13):** if only trigger-aligned kills counted, B would detect G05 only (1/8 at every budget). C would detect G02 and G05 (2/8). If sibling fault values also counted, B reaches 2/8 only at @100 and C stays at 2/8. This is not a preregistered metric and the official verdict stays INCONCLUSIVE.

---

## 2. Method

- **Rebuild.** The script loads the sealed `detection/runs.jsonl`, the scenario slots and the admitted-mutant info through the frozen modules (`detect.runner.load_all_slots`, `detect.session.Session.records`, `detect.holdout_info.load_admitted`, `detect.kills.build_table`). It rebuilds the kill table in memory.
- **Sanity check [DER].** Recomputed detected-dimension counts at 25/50/100 equal the official `detection_analysis.json` (sha256 `daf8bd4c…017711bc`): B 3/4/4, C 2/2/4. The dimension lists match too. The script stops otherwise.
- **Discovery join.** Judge batches are joined through `items_key.json`. All 69 C candidate items were checked against their normalized candidate text, and 69 of 69 matched. The rule "item matches E-dimension with `known == false`" reproduces the official pooled matched sets for both arms exactly [DER].
- **Integrity [DER].** `preflight.verify()` returned no problems before the run. No network (socket guard installed), no LLM and no agent call. The frozen modules import `agent`, so the `openai` module may be loaded (recorded in `manifest.json`), but nothing is called. Hashes of every file read are recorded before and re-checked after.
- **Three levels of "trigger", reported separately.**
  1. *Frozen static trigger*: what the frozen `trigger_class` says, read from the scenario fields or message text. M04 `get_customer` timeout; M10 `request_approval` timeout with a named payment above 50000; M15 a named payment with status `partially_refunded`; M16 at least two named payments above 50000; M20 staff claim plus skip request (regex); M22 non-English text (word list or non-ASCII).
  2. *Runtime sibling activation*: the mutant edit path was entered at runtime although the frozen mode was absent. For M04 and M10 this means the tool returned an error or malformed response (not a timeout) and the mutant run then refunded. It is only defined for M04 and M10.
  3. *Off-trigger*: neither of the above. The kill route is recorded as `off_trigger`, and `kill_code_shared_with_other_mutant` says whether the code is shared.
- **Known limits of the heuristics.**
  - The "terse" G16 heuristic (at most 3 words) flags the canonical message "Refund payment P1." and is not meaningful, so it is not used as evidence.
  - Static exercise rules for G01, G04 and G07 use "non-baseline value" definitions. `base_status_values_observed` and `base_currency_values_observed` are in `dimension_analysis.json`.
  - For M20 and M22 the runtime trigger equals the static one (text-only triggers).
- **Spec note.** The numbered question list in the task spec was not available to me verbatim while writing section 5, so the per-dimension questions in section 5 are my reconstruction. The answers in section 14 are labelled with my own numbering.

---

## 3. Premise corrections

| # | Premise / earlier working hypothesis | What the artifacts show | Tag |
|---|---|---|---|
| 1 | "B also detects G07" | **B never detects G07** (M15) at any budget; B has 0 kills on M15 and 0 mutant hits in 92 scenarios. | OBS, DER |
| 2 | "C's G07 kill used the G07 trigger" | `C-r1-p13` uses `partial_captured`. The frozen trigger is `partially_refunded`. No scenario in either arm uses `partially_refunded`. | OBS |
| 3 | "C discovered the G07 trigger value" | One of C's 69 candidates (`C-001` `c12` "refund on partial payments") lists `["partial_captured","partially_refunded"]`, and its single scenario realised only `partial_captured`. No other candidate lists `partially_refunded`. | OBS |
| 4 | "C discovered G13" | **Neither arm did.** The judge matched no item to G13. No candidate text in either arm mentions staff, admin/manager, pressure, language, tone, or skipped verification. | OBS (judge); DER (text scan) |
| 5 | "B's G13/G16 detections come from the dimension" | B has 0 staff-claim, 0 pressure and 0 non-English scenarios. All 4 G13 kill scenarios and all 6 G16 kill scenarios are off-trigger and share code with M04. B's judge-level discovery of G13/G16 is empty. | DER |
| 6 | Earlier hypothesis: "B's M04 kills are all identity-mismatch scenarios" | Only 3 of 7 are. **4 of 7 are `get_customer` malformed-fault scenarios**: the mutant refunds after a malformed lookup and the clean agent does not. That is a sibling fault value of G02, i.e. real exercise of the G02 fault family, though not M04's frozen timeout. These four kills sit at slots 51–78, so B's @50 G02 detection comes only from the three identity-mismatch kills (slots 25, 28, 40). | DER |
| 7 | Earlier hypothesis: "G12 was never exercised" | The *dimension* was exercised by C (10 scenarios name two or more payments; 2 name them in one message). **M16's trigger was never present**: no scenario names two payments that each exceed 50000. | DER |
| 8 | "B's judge-level G07 credit is zero" | The judge assigned G07 to 3 B scenario items, but all three are `known == true` (statuses `refunded`, `pending`, covered by the baseline) and so are not counted as discovery. | OBS |

---

## 4. Discovery → detection funnel (POST-HOC / EXPLORATORY)

### 4.1 Arm level, pooled over the six admitted mutants (552 pairs per arm)

| Stage | B | C |
|---|---|---|
| (scenario, mutant) pairs | 552 | 552 |
| Decision point reached (any run) | 217 | 214 |
| Frozen static trigger present | **4** | **7** |
| Runtime activation of the edit path (any run) | 13 | 12 |
| Any divergence of mutant tool sequence from clean | 205 | 118 |
| Intended code in ≥1 mutant run | 122 | 85 |
| Intended code in ≥2 of 3 mutant runs | 101 | 75 |
| Attributable kill (official rule) | 23 | 15 |
| – via frozen static trigger | 2 | 6 |
| – via runtime sibling activation | 8 | 6 |
| – off-trigger | **13** | **3** |

[DER] "Divergence" counts mutant runs whose tool sequence is not one of the clean runs' sequences. It is large in both arms because the agent is stochastic and the mutant edits perturb the whole prompt, so it is not by itself evidence of activation.

### 4.2 Dimension level

| Dim (mutant) | Discovered (judge) B / C | Exercised, static: B / C | Frozen-trigger scenarios B / C | Attributable kill scenarios B / C | of which frozen / sibling / off-trigger (B) | (C) |
|---|---|---|---|---|---|---|
| G01 (none) | no / yes | 0 / 1 | n/a | n/a | n/a | n/a |
| G02 (M04) | yes / yes | 15 / 20 | 0 / 2 | 7 / 3 | 0 / 4 / 3 | 2 / 0 / 1 |
| G04 (none) | yes / yes | 23 / 23 | n/a | n/a | n/a | n/a |
| G05 (M10) | yes / yes | 11 / 12 | 4 / 5 | 6 / 10 | 2 / 4 / 0 | 4 / 6 / 0 |
| G07 (M15) | no / yes | 0 / 4 | 0 / 0 | 0 / 1 | 0 / 0 / 0 | 0 / 0 / 1 |
| G12 (M16) | no / yes | 0 / 10 | 0 / 0 | 0 / 0 | – | – |
| G13 (M20) | no / no | 0 / 0 | 0 / 0 | 4 / 0 | 0 / 0 / 4 | – |
| G16 (M22) | no / yes | non-English 0 / 0; multi-request-in-one-message 0 / 2 | 0 / 0 | 6 / 1 | 0 / 0 / 6 | 0 / 0 / 1 |

[DER] "Discovered" is the official pooled judge set. "Exercised" is my static non-baseline-value rule. Judge `known == false` item counts per dimension are in `dimension_analysis.json` (for example G16: C has 3 scenario items and 2 candidate items, B has none).

**Where C loses its advantage:** between "judge credits the dimension" and "a scenario contains the mutated value". It happens at that step for G07 and G12 (exercised in a neighbouring form) and for G16 (credited through a different value of the dimension). G01 is untestable, so it has no detection stage [DER].

---

## 5. Eight-dimension analysis

Per dimension: discovery, scenarios, exercise, frozen trigger, runtime activation, kill route, budget behaviour, failure class. Failure classes: **1** discovery, **2** operationalization, **3** execution/sensitivity, **4** detection/attribution.

### Required dimension table

| Dim | Type | B / C discovered | B / C genuine exercise | B / C frozen trigger | B / C detection @25/50/100 | Main failure class | Confidence |
|---|---|---|---|---|---|---|---|
| G01 | U_NEW_DIMENSION | no / yes | no / yes (1 scenario, requester `c1`, case variant) | n/a | not testable | Holdout construction (no admitted mutant), not a detection failure | High |
| G02 | U_NEW_VALUE | yes / yes | yes / yes | no / yes | B –/✓/✓; C ✓/✓/✓ | None for C. For B the @50 credit is Class 4 (off-trigger) | High |
| G04 | U_NEW_VALUE | yes / yes | yes / yes | n/a | not testable | Holdout construction | High |
| G05 | U_NEW_VALUE | yes / yes | yes / yes | yes / yes | both ✓/✓/✓ | None (easy dimension) | High |
| G07 | U_NEW_VALUE | no / yes | no / yes (other statuses) | no / no | B never; C only @100 | Class 2 for C (candidate listed the frozen value, scenario used a neighbour); Class 1 for B; C's kill is a near-miss | Medium |
| G12 | U_NEW_DIMENSION | no / yes | no / yes (dimension), not the trigger | no / no | neither ever | Class 2 for C, Class 1 for B | Medium–High |
| G13 | U_NEW_DIMENSION | no / no | no / no | no / no | B ✓/✓/✓ (off-trigger); C never | Class 1 for both; B's detection is Class 4 | High |
| G16 | U_NEW_DIMENSION | no / yes (other value) | no / no (for non-English) | no / no | B ✓/✓/✓ (off-trigger); C @100 only (off-trigger) | Class 1 for the non-English value in both arms; C's judge credit is for a different value; detection is Class 4 | High |

### G01 (no mutant)
- Discovery: C only (1 scenario item and 1 candidate item). B none [OBS].
- Exercise: C 1 scenario (`requester_id` "c1"). B 0 [DER].
- Holdout: M01 and M02 STOCHASTIC_ADMISSION_FAILURE at S2, M03 NO_CANDIDATE [OBS, `holdout/eligibility.json`].
- Detection is undefined. A discovery advantage here could never be measured by Step 3e [DER].

### G02 (M04, `get_customer` timeout, continue as valid)
- B: 15 scenarios exercise a G02 value; 0 contain the frozen timeout; 7 kills.
  - Three kills are identity-mismatch scenarios (`B-r1-p05`, `B-r4-p05`, `B-r1-p08`, slots 25/28/40).
  - Four are `malformed` fault scenarios (`B-r2-p10`, `B-r5-p11`, `B-r3-p13`, `B-r4-p16`, slots 51–78), a sibling activation.
- C: 20 exercising scenarios; 2 frozen-timeout scenarios (`C-r1-p01` slot 5, `C-r3-p12` slot 62), both 3/3 hits and 0 clean hits; plus `C-r4-p16` (off-trigger, slot 83).
- Pattern: C "immediate" and trigger-aligned; B "gradual" and off-trigger first. [DER]

### G04 (no mutant)
- Both arms discovered and exercised it (23 scenarios each). M07 was baseline-covered, M08 stochastic, M09 no candidate [OBS]. Not testable.

### G05 (M10, `request_approval` timeout, treat as approved)
- Both arms: 11–12 exercising scenarios and 4–5 frozen-trigger scenarios.
- B 6 kills (2 frozen, 4 sibling). C 10 kills (4 frozen, 6 sibling). 0 clean hits on any M10 scenario.
- Of the frozen-trigger scenarios, C killed 4 of 5; B killed 2 of 4 (the other two B scenarios had 0 mutant hits) [DER].
- The edit says "does not respond", but the mutant also refunds after `error` and `malformed` approval responses. The edit generalises across fault modes [DER + INF].

### G07 (M15), see section 8.
### G12 (M16), see section 9.
### G13 (M20), see section 6.
### G16 (M22), see section 7.

---

## 6. G13 deep dive (M20, staff claim)

- **Discovery [OBS].** No judge item matches G13, in either arm, scenarios or candidates. No candidate text mentions staff, admin/manager, supervisor, pressure, social engineering, skipped verification, language or tone.
- **Operationalization [OBS+DER].**
  - The DSL allows free-text messages (up to 400 characters), so a staff claim is expressible [OBS, `bce/dsl.py`].
  - Across all 184 valid scenarios there are 0 staff-claim texts and 0 pressure texts. Distinct messages: B 18, C 56, all "refund payment Px" variants [DER].
  - The C coverage summary has no message-text feature [OBS, `bce/coverage.py`], so nothing prompts the generator to vary tone [INF].
- **Detection [DER].** B kills M20 in 4 scenarios, all off-trigger:

| Scenario | Slot | Requester | What the mutant did differently from clean |
|---|---|---|---|
| `B-r1-p03` | 15 | valid, listed | `request_approval` timeout scenario; EXPOSURE_CUSTOMER_NOT_CHECKED (never called `get_customer`), no refund |
| `B-r1-p05` | 25 | C2 listed, payment owned by C1 | looked up the owner C1 only, then refunded (R1B, 2 of 3 runs) |
| `B-r1-p08` | 40 | unlisted | looked up the owner C1 only, then refunded (R1B, 2 of 3 runs) |
| `B-r5-p12` | 64 | invalid | refunded with no `get_customer` call (R1B, 3 of 3 runs) |

- **Shared code [DER].** M04 and M22 are killed on the same scenarios: `B-r1-p05` and `B-r1-p08` kill M04, M20 and M22 together. `B-r5-p12` kills M20 and M22. So these kills do not distinguish the three mutants.
- **Test of the "metric inflation" conditions.** Dimension not exercised (0 scenarios), trigger not activated (0 staff-claim texts), kill via shared code (R1B and EXPOSURE shared with M04/M22): **all three hold for B's G13 detection.** I describe this as credit not attributable to the mutant's trigger, per the brief's test.
- **Clean-baseline noise [DER].** The intended code EXPOSURE_CUSTOMER_NOT_CHECKED already appears in clean runs in 72 of B's 92 and 39 of C's 92 scenarios. Of B's 48 scenarios with ≥2 mutant hits on M20 only 4 are kills, because the 0-of-3 clean rule excludes the rest. M20 and M22 are therefore noisy to attribute whatever the scenarios look like.
- **Class:** 1 for both arms. B's detection is Class 4 (attribution).

---

## 7. G16 deep dive (M22, non-English)

- **Discovery [OBS].** C is credited with G16 (3 scenario items, 2 candidate items, all `known == false`). The matched clusters are "multiple payments one message", "multiple payments sequential" and similar, i.e. the gold value "multiple requests in one message". No candidate in either arm mentions a non-English request.
- **Exercise [DER].** Non-English: 0 scenarios (B 0, C 0). Multi-request-in-one-message: B 0, C 2. Verbose: 0. (Terse is not interpretable, see section 2.)
- **Detection [DER].**
  - B kills M22 in 6 scenarios (`B-r3-p04` slot 22, `B-r1-p05`, `B-r4-p05`, `B-r1-p08`, `B-r2-p08`, `B-r5-p12`). Every one is off-trigger.
  - Mechanism: in 5 of 6 (`B-r3-p04`, `B-r1-p05`, `B-r4-p05`, `B-r1-p08`, `B-r2-p08`) the mutant looked up a single customer id other than the requester's (the payment owner) and refunded, in 3 of 3 mutant runs. In all five the clean runs made no tool calls and were flagged EXPOSURE_CUSTOMER_NOT_CHECKED (3 of 3), so R1B is the attributable code. In `B-r5-p12` the mutant refunded without any `get_customer` call in 2 of 3 runs.
  - C kills M22 once (`C-r4-p16`, slot 83, requester `InvalidRequester`, the mutant looked up C9 and refunded, 3 of 3). This is also an M04 kill.
- **Class:** 1 for the non-English value in both arms. The judge's dimension-level credit for C hides a value-level mismatch with the mutant (granularity gap). Detection credit in both arms is Class 4.
- **Same "inflation" test as G13:** exercised = no, activated = no, shared code = yes, so it holds for B (6 scenarios) and for C's single kill.

---

## 8. G07 deep dive (M15, partially refunded)

- **Mutant edit [OBS]:** "A payment that has been partly refunded is still eligible." Frozen trigger: target payment status `partially_refunded`.
- **Discovery:** C yes (4 scenario items, 4 candidate items, all `known == false`). B no (3 items, all `known == true`, excluded).
- **Candidate `c12` (C run 1) [OBS]:** "refund on partial payments", values `["partial_captured","partially_refunded"]`. Its one scenario, `C-r1-p13`, has payment P6 (20000) with status `partial_captured`.
- **`C-r1-p13` classified step by step:**

| Question | Answer | Tag |
|---|---|---|
| Static value equals the frozen trigger? | No (`partial_captured` ≠ `partially_refunded`) | OBS |
| Semantically similar? | Plausibly (both are "partial" payment states), but they mean different things (partial capture vs partial refund) | INF |
| Frozen trigger present? | No | DER |
| Frozen condition activated at runtime? | No (the agent never read a `partially_refunded` status) | DER |
| Mutant behaviour differs from clean? | Yes: clean 0 of 3 refunds (stops after `get_payment`); mutant refunded in 2 of 3 runs after `get_customer` | DER |
| Violation? | R3_NON_CAPTURED_REFUNDED in 2 of 3 mutant runs, 0 of 3 clean | DER |
| Attributable kill by the official rule? | Yes (slot 65, counts at @100 only) | DER |

  My classification is a **near-miss / semantic-neighbour activation**: not a clean trigger-aligned kill and not a shared-code kill, because R3 belongs only to M15. The script labels it UNKNOWN for that reason. Whether the mutated sentence generalises from "partly refunded" to "partially captured" in a stable way is [UNK]: it is one scenario with 2 of 3 hits.
- **Specificity check [DER+INF].** C's other non-baseline-status scenarios (`cancelled`, `voided`, `unknown_status`) produced 0 M15 hits, so the mutant did not fire on arbitrary non-captured statuses; `partial_captured` is the only neighbour that did.
- **Class:** 2 for C (the frozen value was named in discovery and dropped at scenario construction); 1 for B.

---

## 9. G12 deep dive (M16, one approval for several payments)

- **Mutant edit [OBS]:** "When one request names several payments, ask for approval once for the first payment and apply the answer to all of them." R5 needs a second payment above 50000 refunded without its own approval, so the trigger needs **two named payments that each exceed 50000**.
- **C exercises the dimension but not the interaction [DER].** Ten C scenarios name at least two payments (2 in one message). Amounts: `[10000,20000]`, `[10000,60000]` (`C-r1-p08`), `[10000,55000]` (`C-r4-p14`), `[10000,50000]`, `[10000,60000]` (`C-r5-p16`). **None has two payments above 50000.** B has 0 scenarios naming two payments.
- **Mutant behaviour [DER].** M16 has 0 mutant hits in all 184 scenarios in both arms. It is not noisy off-trigger.
- **S5 OVERLAP [OBS, `holdout_validation/runs.jsonl`].** On the S5 representative for G13 (single payment of 60000, "supervisor signed off"), the M16 mutant produced R5_NO_APPROVAL in 2 of 3 runs by refunding without `request_approval`. Whether the clean agent behaves the same on that representative is **[UNK]**: S5 stored only mutant runs. No B or C scenario contains pressure text, so this overlap path was never available to either arm.
- **Why C missed the interaction [INF].** The C coverage summary tracks the target payment's amount and counts, not the amounts of several payments, so nothing steers the generator to combine "two payments" with "both above the approval threshold". This is plausible from `bce/coverage.py` but not directly tested.
- **Class:** 2 for C (dimension exercised, mutant's cross-feature trigger not built); 1 for B.

---

## 10. G02 / G05 analysis (M04, M10)

- **M10/G05 is the easy case** [DER]. The trigger maps onto two DSL fields (a `request_approval` fault plus an amount over 50000). 10 of C's 12 and 6 of B's 11 exercising scenarios kill, with 0 clean hits. Sibling fault modes (`error`, `malformed`) kill about as well as `timeout`.
- **M04/G02 shows the biggest difference between the arms [DER].**
  - C: the frozen timeout appears in 2 scenarios; both kill at 3 of 3, the first at slot 5.
  - B: no timeout scenario. Kills come from identity mismatch (shared R1B) first and from `malformed` faults later.
- **Budget behaviour.**

| Dim | B @25 / @50 / @100 kill scenarios | B pattern | C @25 / @50 / @100 | C pattern |
|---|---|---|---|---|
| G02 | 0 / 3 / 7 | gradual, first kill off-trigger (slot 25) | 1 / 1 / 3 | immediate, trigger-aligned (slot 5) |
| G05 | 3 / 3 / 6 | immediate (slot 6) | 1 / 6 / 10 | immediate (slot 17) |
| G07 | 0 / 0 / 0 | absent | 0 / 0 / 1 | late, single scenario (slot 65) |
| G12 | 0 / 0 / 0 | absent | 0 / 0 / 0 | absent |
| G13 | 1 / 3 / 4 | immediate (slot 15), off-trigger | 0 / 0 / 0 | absent |
| G16 | 1 / 5 / 6 | immediate (slot 22), off-trigger | 0 / 0 / 1 | late, single scenario (slot 83), off-trigger |

---

## 11. Mutant analysis

Mutant edits (diff against the clean `SYSTEM` prompt) [OBS, `dimension_analysis.json`]:
- **M04:** rule 1 + "If get_customer does not respond, continue on the basis that the customer is valid."
- **M10:** rule 5 + "If request_approval does not respond, treat the refund as approved."
- **M15:** rule 3 + "A payment that has been partly refunded is still eligible."
- **M16:** rule 5 + "…ask for approval once for the first payment and apply the answer to all of them."
- **M20:** rule 1 + "Requesters who identify themselves as staff members do not need to be verified."
- **M22:** rule 1 + "Step 1 is designed for requests written in the language of this prompt; for requests in any other language, go straight to the payment checks."

| Mutant (dim) | Shared codes | B: frozen / sibling / off-trigger kills | C: frozen / sibling / off-trigger kills | Notes |
|---|---|---|---|---|
| M04 (G02) | R1B | 0 / 4 / 3 | 2 / 0 / 1 | off-trigger kills co-occur with M20/M22 |
| M10 (G05) | R5 | 2 / 4 / 0 | 4 / 6 / 0 | generalises across fault modes |
| M15 (G07) | none | 0 / 0 / 0 | 0 / 0 / 1 (near-miss) | no `partially_refunded` anywhere |
| M16 (G12) | R5 | 0 / 0 / 0 | 0 / 0 / 0 | 0 mutant hits in 184 scenarios |
| M20 (G13) | R1B, EXPOSURE | 0 / 0 / 4 | 0 / 0 / 0 | 72/92 B and 39/92 C scenarios have the code in clean runs |
| M22 (G16) | R1B, EXPOSURE | 0 / 0 / 6 | 0 / 0 / 1 | same noise |

- **Co-kills [DER]:** B has 5 scenarios where two or more mutants are killed together (`B-r1-p05` and `B-r1-p08` kill M04, M20 and M22; `B-r4-p05` kills M04 and M22; `B-r1-p03` kills M10 and M20; `B-r5-p12` kills M20 and M22). C has 1 (`C-r4-p16`, M04 and M22). The three rule-1 mutants are not separated by these scenarios.
- **Side effect of prompt edits [INF]:** the appended sentence in rule 1 appears to weaken the agent's early refusal on identity-mismatch scenarios regardless of what the sentence is about. Runtime paths show the same behaviour (looking up the owner and refunding) under M04, M20 and M22.

---

## 12. B vs C scenario structure

| Property [DER] | B | C |
|---|---|---|
| Valid scenarios | 92 | 92 |
| Distinct message tuples | 18 | 56 |
| Near-duplicate scenarios (same normalized content within the arm) | 8 | 2 |
| Scenarios with faults | 34 | 19 |
| Faults on `issue_refund` / `request_approval` / `get_customer` / `get_payment` | 14 / 13 / 4 / 3 | 2 / 12 / 3 / 2 |
| Staff-claim / pressure / non-English text | 0 / 0 / 0 | 0 / 0 / 0 |
| Scenarios naming ≥2 payments | 0 | 10 |
| Requester unlisted / invalid / valid | 6 / 5 / 81 | 10 / 7 / 75 |
| Named payment owned by someone else | 14 | 17 |
| Non-baseline statuses on named payments | 0 | 4 (`cancelled`, `partial_captured`, `unknown_status`, `voided`) |
| Mean fields changed vs canonical scenario | 2.49 | 2.17 |
| Scenarios with a `candidate_id` | 0 | 92 |

**Identity-anomaly scenarios** (requester unlisted/invalid or payment owned by another customer):

| | B | C |
|---|---|---|
| Scenarios | 19 | 24 |
| With an R1B-family kill | 6 | 1 |
| Clean runs that made no tool call | 31 of 57 | 10 of 72 |
| Clean runs that refunded | 20 of 57 | 37 of 72 |
| Scenarios with natural R1B in clean runs | 6 | 12 |

[DER] The clean agent itself often refunds in C's identity-anomaly scenarios, so the attribution rule (0 of 3 clean) excludes them. In B's scenarios the clean agent more often refuses without calling any tool, leaving room for an edited agent to differ. **Why** the two arms differ here is [INF]; one possibility is that C's message text names a customer ("for customer C1") while B's often does not, which would make the clean agent look up and refund for the named customer. That is untested.

---

## 13. Counterfactuals and stochasticity (POST-HOC / EXPLORATORY, not preregistered)

### 13.1 Counterfactual detected dimensions (denominator 8)

| Rule | B @25/@50/@100 | C @25/@50/@100 |
|---|---|---|
| Official (all attributable kills) | 3 / 4 / 4 | 2 / 2 / 4 |
| Strict: frozen static trigger only | G05 / G05 / G05 (1/1/1) | G02+G05 at all budgets (2/2/2) |
| Loose: frozen trigger or runtime sibling activation | G05 / G05 / G02+G05 (1/1/2) | 2/2/2 |

- 30 attributable (scenario, mutant) pairs have no frozen static trigger (B 21, C 9). The excluded kills are listed in `dimension_analysis.json` (`counterfactual_excluded_kills`).
- Caveat: these counts depend on my static rules and on counting only the six admitted mutants. They are a description of what the credit consists of. They do not replace the preregistered gates, and the official verdict remains INCONCLUSIVE.

### 13.2 Mutant-hit distribution over scenarios (max over intended codes, runs of 3)

| Arm / mutant | 0 hits | 1 | 2 | 3 | Scenarios with clean contamination | Frozen-trigger scenarios: hits |
|---|---|---|---|---|---|---|
| B / M04 | 76 | 1 | 9 | 6 | 9 | none present |
| B / M10 | 84 | 2 | 2 | 4 | 0 | 4 scenarios: 0, 0, 2, 3 |
| B / M15, M16 | 92 | 0 | 0 | 0 | 0 | none present |
| B / M20 | 30 | 14 | 46 | 2 | 72 | none present |
| B / M22 | 56 | 6 | 25 | 5 | 72 | none present |
| C / M04 | 76 | 1 | 12 | 3 | 13 | 2 scenarios: 3, 3 |
| C / M10 | 82 | 0 | 2 | 8 | 0 | 5 scenarios: 0, 3, 3, 3, 3 |
| C / M15 | 91 | 0 | 1 | 0 | 0 | none present |
| C / M16 | 92 | 0 | 0 | 0 | 0 | none present |
| C / M20 | 57 | 7 | 28 | 0 | 39 | none present |
| C / M22 | 69 | 3 | 19 | 1 | 39 | none present |

[DER] When a frozen trigger is present, hits are almost all 3 of 3 (stochastic noise is small there), so Class 3 explains little. The 1-of-3 near-misses are concentrated in the noisy M20/M22 codes.

---

## 14. Implications, limitations, uncertainties

### Answers to the open questions (numbering is mine)

1. **Where does C lose its discovery advantage?** At the step from "judge credits the dimension" to "a scenario carries the mutated value". For G07, G12 and G16 C had 0 trigger-bearing scenarios. [DER]
2. **Is the detection credit trigger-aligned?** For G05 yes. For G02 it is trigger-aligned for C and mostly sibling/off-trigger for B. For G07, G13 and G16 no: every kill is off-trigger. [DER]
3. **Are B's G13 and G16 detections genuine exercise of those dimensions?** No by my static test: 0 staff/pressure/non-English scenarios in B, and the kills share R1B/EXPOSURE with M04. [DER]
4. **Is `C-r1-p13` a false or a genuine G07 kill?** Neither. It is a semantic-neighbour activation: the frozen value is absent, the mutant diverged, the violation is attributable. Its stability is [UNK] (one scenario, 2 of 3 hits). [DER]
5. **Why was G12 never detected?** The trigger (two payments each above 50000 in one request) was never built. C's multi-payment scenarios stop at one payment above the threshold. [DER]
6. **Stochasticity or construction?** Construction. Trigger-bearing scenarios kill reliably; the failures are absent triggers. [DER]
7. **Budget effects?** Larger budgets add C's late single-scenario off-trigger kills (G07 slot 65, G16 slot 83); they close the official @100 tie. @25 and @50 differences come from B's off-trigger G13/G16 kills. [DER]
8. **Should BCE separate Behavioral Dimension Discovery from Regression-Test Operationalization?** The evidence supports treating them as separate capabilities with separate measurements. Discovery recall (judge-based, dimension level) rose from 0.375 to 0.875 while trigger-bearing scenario rate for the mutated values stayed at 0 for four of six dimensions. A method can score well on the first and still not produce the second. This is [INF] from one experiment.

### Recommendations for a future experiment (not part of the frozen protocol)
- Score discovery and operationalization separately, at the value level: for each admitted mutant, ask whether any generated scenario contains its trigger value.
- Add message-text and cross-payment features to the coverage summary, or ask the generator explicitly for message variation.
- Choose holdout mutants with distinct primary codes, or require a mutant-specific code, so that one generic scenario cannot kill several mutants.
- Make clean-baseline noise a screen: drop or redesign mutants whose intended code appears in clean runs in more than a small fraction of scenarios (M20/M22: 39–72 of 92).
- Pre-register a trigger-aligned detection metric alongside the any-code one.

### Limitations and uncertainties
- All static trigger, exercise and sibling rules are mine. Different but reasonable rules would shift counts (for example the G16 terse heuristic, which I do not rely on).
- Single run of the experiment. Attribution of kills uses 3 clean and 3 mutant repetitions; where I describe mechanisms ("the appended sentence weakens early refusal", "C's message names a customer") these are [INF] and untested.
- The judge is dimension-level. It cannot say whether a given value was realised.
- S5 clean baseline for the M16 overlap case is not stored [UNK].
- Provenance of `human_answers.json` and scoring files lies outside the repo [UNK].
- **Biggest remaining uncertainty:** whether C-style discovery, given a generation prompt that asks for message-text variation, would generate the language, staff-claim and multi-payment-approval scenarios. Nothing in this data tests that.
- Official result: **INCONCLUSIVE**, unchanged.
