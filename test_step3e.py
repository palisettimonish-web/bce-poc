"""Tests for the 3e detection infrastructure. Synthetic fixtures and a fake executor only: no agent or LLM call, no real 3d scenario,
no real 3e result (Amendment 4)."""

import ast
import copy
import json
import re
from pathlib import Path

import pytest

from agent import SYSTEM
from bce import dsl
from holdout import engine, runtime
from detect import analysis, audit, drift, kills, preflight, rules, runner, slots
from detect.session import Incomplete, Session

ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------- fixtures

def raw_scenario(tag):
    return {
        "candidate_id": None,
        "customers": [{"id": "C1", "valid": True}],
        "payments": [{"id": "P1", "customer_id": "C1", "amount": 1000, "status": "captured"}],
        "requester_id": "C1", "messages": [f"synthetic {tag}"], "faults": {}, "approval": "approve", "expected_distinction": "synthetic",
    }


def write_arm(directory, arm, layout, extra_positions=()):
    """layout: {run: {position: 'valid'|'invalid'}}; absent positions are missing. extra_positions are >= 20 (valid)."""
    for run in range(1, 6):
        entries = []
        for pos, kind in sorted(layout.get(run, {}).items()):
            raw = raw_scenario(f"{arm}{run}{pos}") if kind == "valid" else {"bad": True}
            entries.append({"run_id": f"{arm}-{run}", "position": pos, "scenario": raw, "valid": kind == "valid",
                            "errors": [] if kind == "valid" else ["synthetic invalid"]})
        for pos in extra_positions:
            entries.append({"run_id": f"{arm}-{run}", "position": pos, "scenario": raw_scenario(f"x{run}{pos}"), "valid": True, "errors": []})
        path = slots.scenario_path(arm, run, directory)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"meta": {"tokens": {"input": 100, "output": 50}}, "scenarios": entries}), encoding="utf-8")


def small_layout(n=4):
    return {run: {p: "valid" for p in range(n)} for run in range(1, 6)}


def info_fixture():
    base = {"system": SYSTEM + " mutated", "trigger_instance_1": {"id": "T1", "scenario": raw_scenario("trig")}}
    return {
        "M01": {**base, "dimension": "G02", "primary_code": "CODE_A", "intended_codes": ["CODE_A"], "flags": []},
        "M02": {**base, "dimension": "G05", "primary_code": "CODE_B", "intended_codes": ["CODE_B"], "flags": []},
        "M03": {**base, "dimension": "G12", "primary_code": "CODE_C", "intended_codes": ["CODE_C", "CODE_C2"], "flags": ["OVERLAP"]},
    }


class Fake:
    """Scripted executor. `script(job) -> list of codes`; `fail(job) -> bool` simulates a transport failure."""

    def __init__(self, script=lambda job: [], fail=lambda job: False, models=("m1",)):
        self.script, self.fail, self.models, self.jobs = script, fail, list(models), []

    def __call__(self, job):
        self.jobs.append(job)
        base = {"key": runtime.job_key(job), "stage": job["stage"], "variant": job["variant"], "subject": job["subject"],
                "instance": job["instance"], "rep": job["rep"], "scenario": job["scenario"]["id"],
                "scenario_params": {"requester_id": "C1", "messages": ["m"], "faults": {}, "approval_granted": True, "fixture": {}}}
        if self.fail(job):
            return {**base, "transport_failure": True, "replies": [], "calls": [], "ledger": [], "violations": [], "models": [], "tokens": None}
        return {**base, "transport_failure": False, "replies": ["ok"], "calls": [{"tool": "t"}], "ledger": [], "violations": list(self.script(job)),
                "models": list(self.models), "served_models_per_response": list(self.models), "tokens": {"input": 10, "output": 5}}


def make_slots(tmp_path, layout=None, extra=()):
    write_arm(tmp_path, "B", layout or small_layout(), extra)
    write_arm(tmp_path, "C", layout or small_layout(), extra)
    by_arm, stats = runner.load_all_slots(tmp_path)
    return by_arm, stats


def by_ref(slots_by_arm, ref):
    return next(s for slots_ in slots_by_arm.values() for s in slots_ if s["ref"] == ref)


def killing(mapping):
    """script: {(ref, mutant): [codes for rep0, rep1, rep2]}; everything else is clean."""
    def script(job):
        if job["variant"] == "clean":
            return mapping.get((job["instance"], "clean"), [[], [], []])[job["rep"]]
        return mapping.get((job["instance"], job["subject"]), [[], [], []])[job["rep"]]
    return script


def run_all(tmp_path, script, layout=None, curtail=True, fail=lambda job: False):
    by_arm, stats = make_slots(tmp_path, layout)
    info = info_fixture()
    session = Session(tmp_path / "det", Fake(script, fail))
    summary = runner.run_detection(session, by_arm, info, curtail)
    table = kills.build_table(session.records(), by_arm, info)
    return session, by_arm, stats, info, table, summary


# ---------------------------------------------------------------------------- budget slots (2.18)

def test_slot_mapping_missing_invalid_and_excluded(tmp_path):
    layout = {run: {p: "valid" for p in range(20)} for run in range(1, 6)}
    layout[2][3] = "invalid"
    del layout[4][7]
    write_arm(tmp_path, "B", layout, extra_positions=(20, 21))
    write_arm(tmp_path, "C", layout, extra_positions=(20,))
    s, stats = slots.load_arm_slots("B", tmp_path)
    assert len(s) == 100
    assert (s[0]["run"], s[0]["position"]) == (1, 0) and (s[4]["run"], s[4]["position"]) == (5, 0) and (s[5]["run"], s[5]["position"]) == (1, 1)
    k_invalid = next(x["slot"] for x in s if x["run"] == 2 and x["position"] == 3)
    k_missing = next(x["slot"] for x in s if x["run"] == 4 and x["position"] == 7)
    assert s[k_invalid]["status"] == slots.INVALID and s[k_missing]["status"] == slots.MISSING
    assert sum(1 for x in s if x["status"] == slots.VALID) == 98
    assert stats["positions_ge_20"] == 10 and stats["returned"] == 5 * 22 - 1 and all(x["position"] < 20 for x in s)
    assert [x["slot"] for x in slots.budget_slots(s, 25)] == list(range(25))


def test_stored_validity_must_agree_with_the_frozen_validator(tmp_path):
    write_arm(tmp_path, "B", small_layout())
    path = slots.scenario_path("B", 1, tmp_path)
    doc = json.loads(path.read_text())
    doc["scenarios"][0]["valid"] = False
    path.write_text(json.dumps(doc))
    with pytest.raises(slots.SlotError):
        slots.load_arm_slots("B", tmp_path)


def test_absent_sealed_file_is_an_error_not_a_repair(tmp_path):
    with pytest.raises(slots.SlotError):
        slots.load_arm_slots("B", tmp_path)


def test_arm_a_is_the_fixed_35_in_file_order():
    a = slots.arm_a_slots(engine.baseline_scenarios())
    assert len(a) == 35 and [x["slot"] for x in a] == list(range(35)) and all(x["status"] == slots.VALID for x in a)


def test_order_interleaves_b_and_c_then_a(tmp_path):
    by_arm, _ = make_slots(tmp_path)
    by_arm["A"] = slots.arm_a_slots(engine.baseline_scenarios())
    o = runner.order(by_arm)
    assert [x["arm"] for x in o[:4]] == ["B", "C", "B", "C"] and o[0]["slot"] == 0 and o[2]["slot"] == 1
    assert [x["arm"] for x in o[-35:]] == ["A"] * 35 and len(o) == 235


# ---------------------------------------------------------------------------- kill rule (2.16 l.376)

def runs(*code_lists):
    return [{"violations": list(c)} for c in code_lists]


def test_attributable_kill_needs_two_of_three_mutant_and_zero_clean():
    clean = runs([], [], [])
    assert kills.attributable_codes(["X"], runs(["X"], ["X"], []), clean) == ["X"]
    assert kills.attributable_codes(["X"], runs(["X"], ["X"], ["X"]), clean) == ["X"]
    assert kills.attributable_codes(["X"], runs(["X"], [], []), clean) == []  # 1 of 3: partial exposure is not a kill


def test_clean_contamination_blocks_the_kill():
    assert kills.attributable_codes(["X"], runs(["X"], ["X"], ["X"]), runs([], ["X"], [])) == []


def test_only_intended_codes_are_attributable_but_any_code_is_reported_alongside():
    mut, clean = runs(["Y"], ["Y"], []), runs([], [], [])
    assert kills.attributable_codes(["X"], mut, clean) == []
    assert kills.any_code_kills(mut, clean) == ["Y"]


def test_curtailment_condition():
    clean = runs(["N"], [], [])
    assert kills.curtailable(runs([], ["N"]), clean)  # only a code that also appears in clean
    assert not kills.curtailable(runs([], ["X"]), clean)  # a code absent from all clean runs
    assert kills.curtailable(runs([], []), runs([], [], []))


def test_pair_status():
    clean = runs([], [], [])
    assert kills.pair_status(runs([], [], []), clean) == kills.COMPLETE
    assert kills.pair_status(runs([], []), clean) == kills.CURTAILED
    assert kills.pair_status(runs(["X"], []), clean) == kills.INCOMPLETE
    assert kills.pair_status(runs([]), clean) == kills.INCOMPLETE
    assert kills.pair_status(runs([], []), runs([], [])) == kills.INCOMPLETE


# ---------------------------------------------------------------------------- the runner

def test_repetitions_and_curtailment_with_nominal_and_actual_counts(tmp_path):
    session, by_arm, stats, info, table, summary = run_all(tmp_path, killing({}), layout={1: {0: "valid"}})
    ref = "B-r1-p00"
    row = table[ref]
    assert row["nominal_executions"] == 3 + 3 * 3 == 12
    assert row["actual_executions"] == 3 + 2 * 3 == 9  # the third mutant repetition is skipped for each of the 3 mutants
    assert set(row["pairs"].values()) == {kills.CURTAILED}


def test_third_repetition_runs_when_a_code_absent_from_clean_appears(tmp_path):
    script = killing({("B-r1-p00", "M01"): [["CODE_A"], [], []]})
    session, by_arm, stats, info, table, summary = run_all(tmp_path, script, layout={1: {0: "valid"}})
    row = table["B-r1-p00"]
    assert row["pairs"]["M01"] == kills.COMPLETE and row["pairs"]["M02"] == kills.CURTAILED
    assert row["actual_executions"] == 3 + 3 + 2 + 2
    assert row["attributable"]["M01"] == []  # 1 of 3 is not a kill


def test_curtailment_off_runs_everything(tmp_path):
    session, by_arm, stats, info, table, summary = run_all(tmp_path, killing({}), layout={1: {0: "valid"}}, curtail=False)
    assert table["B-r1-p00"]["actual_executions"] == 12 and summary["curtail"] is False


def test_invalid_and_missing_scenarios_execute_nothing(tmp_path):
    fake_layout = {1: {0: "valid", 1: "invalid"}}
    by_arm, stats = make_slots(tmp_path, fake_layout)
    session = Session(tmp_path / "det", Fake())
    runner.run_detection(session, by_arm, info_fixture())
    refs = {j["instance"] for j in session.executor.jobs}
    assert "B-r1-p01" not in refs and "B-r2-p00" not in refs  # invalid and missing
    assert "B-r1-p00" in refs and "C-r1-p00" in refs


def test_attributable_kill_through_the_runner(tmp_path):
    script = killing({("B-r1-p00", "M01"): [["CODE_A"], ["CODE_A"], []], ("C-r1-p00", "M01"): [["CODE_A"], ["CODE_A"], ["CODE_A"]],
                      ("C-r1-p00", "clean"): [[], ["CODE_A"], []]})
    session, by_arm, stats, info, table, summary = run_all(tmp_path, script, layout={1: {0: "valid"}})
    assert table["B-r1-p00"]["attributable"]["M01"] == ["CODE_A"]
    assert table["C-r1-p00"]["attributable"]["M01"] == []  # clean contamination
    assert table["B-r1-p00"]["any_code"]["M01"] == ["CODE_A"]


def test_transport_failure_resumes_without_rerunning_completed_jobs(tmp_path):
    by_arm, stats = make_slots(tmp_path, {1: {0: "valid"}})
    info = info_fixture()
    state = {"fail_once": True}

    def fail(job):
        if state["fail_once"] and job["variant"] == "mutant" and job["subject"] == "M02" and job["instance"] == "B-r1-p00" and job["rep"] == 0:
            return True
        return False

    session = Session(tmp_path / "det", Fake(fail=fail))
    with pytest.raises(Incomplete):
        runner.run_detection(session, by_arm, info)
    assert not session.completed(runner.STATUS_DETECT_DONE)
    state["fail_once"] = False
    session2 = Session(tmp_path / "det", Fake(fail=fail))
    summary = runner.run_detection(session2, by_arm, info)
    keys = [j["instance"] + j["subject"] + str(j["rep"]) + j["variant"] for j in session2.executor.jobs]
    assert len(keys) == len(set(keys)) and len(session2.executor.jobs) < 3 * 12  # only the missing work was redone
    assert summary["transport_failures"] == 1
    with pytest.raises(RuntimeError):
        runner.run_detection(Session(tmp_path / "det", Fake()), by_arm, info)


def test_runs_are_appended_never_rewritten(tmp_path):
    session, *_ = run_all(tmp_path, killing({}), layout={1: {0: "valid"}})
    text = (tmp_path / "det" / rules.RUNS_LOG).read_text()
    before = text.splitlines()
    session.runs.append({"key": "x", "transport_failure": True})
    assert (tmp_path / "det" / rules.RUNS_LOG).read_text().splitlines()[: len(before)] == before


def test_degenerate_gate_stops_the_run(tmp_path):
    session = Session(tmp_path / "d", None)
    for i in range(10):
        session.runs.append({"key": str(i), "transport_failure": False, "replies": ["[max turns exceeded]" if i == 0 else "ok"]})
    session.degenerate_gate()  # 10%: not more than 10%
    session.runs.append({"key": "z", "transport_failure": False, "replies": ["[agent returned no text]"]})
    with pytest.raises(runtime.InfrastructureFailure):
        session.degenerate_gate()


# ---------------------------------------------------------------------------- budgets and aggregation

def killer(refs_by_mutant):
    mapping = {}
    for (ref, mid), code in refs_by_mutant.items():
        mapping[(ref, mid)] = [[code], [code], [code]]
    return killing(mapping)


def test_budgets_are_nested_prefixes_and_denominator_is_8(tmp_path):
    layout = {run: {p: "valid" for p in range(10)} for run in range(1, 6)}
    # slot 30 = run 1, position 6; slot 80 = run 1, position 16 (not present: layout has 10 positions) -> use position 9 => slot 45
    script = killer({("B-r1-p06", "M01"): "CODE_A", ("B-r1-p09", "M02"): "CODE_B", ("C-r1-p00", "M01"): "CODE_A"})
    session, by_arm, stats, info, table, summary = run_all(tmp_path, script, layout)
    det = analysis.detection_block(table, info, with_bootstrap=False)
    B, C = det["arms"]["B"], det["arms"]["C"]
    assert by_arm["B"][30]["ref"] == "B-r1-p06" and by_arm["B"][45]["ref"] == "B-r1-p09"
    assert B[25]["dimensions_detected"] == [] and B[50]["dimensions_detected"] == ["G02", "G05"] and B[100]["dimensions_detected"] == ["G02", "G05"]
    assert B[50]["dimension_detection_rate"] == 2 / 8 and B[100]["rate_over_testable_dimensions"] == 2 / 3
    assert C[25]["dimensions_detected"] == ["G02"] and C[25]["dimension_detection_rate"] == 1 / 8
    assert det["T"] == 3 and det["denominator"] == 8 and set(det["not_detection_testable"]) == {"G01", "G04", "G07", "G13", "G16"}


def test_two_variants_of_one_dimension_count_once(tmp_path):
    info = info_fixture()
    info["M04"] = {**info["M01"], "primary_code": "CODE_D", "intended_codes": ["CODE_D"]}  # second variant of G02
    by_arm, _ = make_slots(tmp_path, {1: {0: "valid"}})
    session = Session(tmp_path / "det", Fake(killer({("B-r1-p00", "M01"): "CODE_A", ("B-r1-p00", "M04"): "CODE_D"})))
    runner.run_detection(session, by_arm, info)
    det = analysis.detection_block(kills.build_table(session.records(), by_arm, info), info, with_bootstrap=False)
    assert det["arms"]["B"][25]["dimensions_detected_count"] == 1 and len(det["arms"]["B"][25]["killed_variants"]) == 2
    assert det["arms"]["B"][25]["variant_kill_rate"] == 2 / 4


def test_arm_a_is_descriptive_with_its_own_budgets(tmp_path):
    ids = [s["id"] for s in engine.baseline_scenarios()]
    script = killer({(ids[30], "M01"): "CODE_A"})
    by_arm, _ = make_slots(tmp_path, {1: {0: "valid"}})
    by_arm["A"] = slots.arm_a_slots(engine.baseline_scenarios())
    info = info_fixture()
    session = Session(tmp_path / "det", Fake(script))
    runner.run_detection(session, by_arm, info)
    table = kills.build_table(session.records(), by_arm, info)
    det = analysis.detection_block(table, info, resamples=50)
    assert sorted(det["arms"]["A"]) == [25, 35] and det["arms"]["A"][25]["dimensions_detected"] == [] and det["arms"]["A"][35]["dimensions_detected"] == ["G02"]
    assert det["arms"]["A"][35]["nominal_executions"] == 35 * 12
    assert not any(k.startswith("A@") or k.startswith("A-") for k in det["bootstrap"]["estimates"])  # A never enters the formal comparison


def test_class_stratification(tmp_path):
    script = killer({("B-r1-p00", "M01"): "CODE_A", ("B-r1-p00", "M03"): "CODE_C"})
    session, by_arm, stats, info, table, summary = run_all(tmp_path, script, {1: {0: "valid"}})
    det = analysis.detection_block(table, info, with_bootstrap=False)
    assert det["classes"]["U_NEW_VALUE"]["arms"]["B"][25] == 1 and det["classes"]["U_NEW_DIMENSION"]["arms"]["B"][25] == 1
    assert det["classes"]["U_NEW_VALUE"]["denominator"] == 4 == det["classes"]["U_NEW_DIMENSION"]["denominator"]
    assert det["classes"]["U_NEW_DIMENSION"]["testable"] == ["G12"] and det["classes"]["U_NEW_VALUE"]["testable"] == ["G02", "G05"]


def test_overlap_and_drift_suspect_sensitivities_keep_the_denominator(tmp_path):
    script = killer({("B-r1-p00", "M01"): "CODE_A", ("B-r1-p00", "M03"): "CODE_C"})
    session, by_arm, stats, info, table, summary = run_all(tmp_path, script, {1: {0: "valid"}})
    drift_verdict = {"drift_suspect": ["M01"], "potentially_invalid": False, "served_model_identity": "SAME"}
    res = analysis.analyze(table, by_arm, stats, info, drift_verdict, analysis.generation_tokens(tmp_path), resamples=50)
    primary = res["detection"]["arms"]["B"][25]
    no_overlap = res["sensitivity_without_OVERLAP"]
    no_drift = res["sensitivity_without_DRIFT_SUSPECT"]
    assert primary["dimensions_detected"] == ["G02", "G12"]
    assert no_overlap["arms"]["B"][25]["dimensions_detected"] == ["G02"] and no_overlap["denominator"] == 8 and no_overlap["T_prime"] == 2
    assert "G12" in no_overlap["not_detection_testable"] and no_overlap["arms"]["B"][25]["dimension_detection_rate"] == 1 / 8
    assert no_overlap["arms"]["B"][25]["rate_over_testable_dimensions"] == 1 / 2
    assert no_drift["arms"]["B"][25]["dimensions_detected"] == ["G12"] and no_drift["excluded_variants"] == ["M01"]
    assert res["flags"]["OVERLAP"] == ["M03"] and res["flags"]["DRIFT_SUSPECT"] == ["M01"]
    assert res["detection"]["arms"]["B"][25]["dimensions_detected"] == ["G02", "G12"]  # primary is not relabelled


def test_pending_drift_leaves_the_drift_sensitivity_undefined(tmp_path):
    session, by_arm, stats, info, table, summary = run_all(tmp_path, killing({}), {1: {0: "valid"}})
    res = analysis.analyze(table, by_arm, stats, info, None, analysis.generation_tokens(tmp_path), resamples=20)
    assert res["sensitivity_without_DRIFT_SUSPECT"] is None


def test_discovery_side_counts_never_repair(tmp_path):
    layout = {1: {0: "valid", 1: "invalid"}, 2: {0: "valid"}}
    by_arm, stats = make_slots(tmp_path, layout)
    c = analysis.discovery_counts(by_arm, stats)["C"]
    assert (c["valid_slots"], c["invalid_slots"], c["missing_slots"], c["slots"]) == (2, 1, 97, 100)
    assert c["regenerated_or_repaired"] == 0 and c["scenario_validity"] == 2 / 3 and c["invalid"][0]["ref"] == "C-r1-p01"


def test_invalid_experiment_check_for_arm_c(tmp_path):
    layout = {1: {0: "invalid", 1: "invalid", 2: "valid"}}
    by_arm, stats = make_slots(tmp_path, layout)
    info = info_fixture()
    session = Session(tmp_path / "det", Fake())
    runner.run_detection(session, by_arm, info)
    table = kills.build_table(session.records(), by_arm, info)
    res = analysis.analyze(table, by_arm, stats, info, None, analysis.generation_tokens(tmp_path), resamples=10)
    assert res["invalid_experiment_checks"]["arm_C_over_half_dsl_invalid"] is True


def test_cost_and_failures_per_execution(tmp_path):
    session, by_arm, stats, info, table, summary = run_all(tmp_path, killer({("B-r1-p00", "M01"): "CODE_A"}), {1: {0: "valid"}})
    det = analysis.detection_block(table, info, with_bootstrap=False)
    c = analysis.cost(det, by_arm, analysis.generation_tokens(tmp_path))["B"][25]
    n = det["arms"]["B"][25]["nominal_executions"]
    assert c["distinct_true_failures"] == 1 and c["failures_per_execution_nominal"] == 1 / n
    assert c["failures_per_execution_actual"] == 1 / det["arms"]["B"][25]["actual_executions"]
    assert c["generation_tokens_all_runs"] == 5 * 150 and c["generation_tokens_pro_rata_by_slots"] == 150 * 5 * 5 / 20


def test_natural_failures_reported_separately(tmp_path):
    script = killing({("B-r1-p00", "clean"): [["NAT"], ["NAT"], []]})
    session, by_arm, stats, info, table, summary = run_all(tmp_path, script, {1: {0: "valid"}})
    assert analysis.natural_failures(table)["B"]["codes"] == {"NAT": 1}


# ---------------------------------------------------------------------------- bootstrap (2.16 l.380-385)

def test_bootstrap_is_reproducible_and_paired():
    killed = {("B", 25): {"M01"}, ("C", 25): {"M01", "M02"}, ("B", 50): {"M01"}, ("C", 50): {"M01", "M02"}, ("B", 100): {"M01"}, ("C", 100): {"M01", "M02", "M03"}}
    vbd = {"G02": ["M01"], "G05": ["M02"], "G12": ["M03"]}
    a = analysis.bootstrap(killed, vbd, resamples=500)
    b = analysis.bootstrap(killed, vbd, resamples=500)
    assert a == b and a["seed"] == 20260311 and a["descriptive_only"] is True
    est = a["estimates"]
    assert est["C-B@100"]["mean"] == pytest.approx(est["C@100"]["mean"] - est["B@100"]["mean"])
    assert est["B@25"]["low"] <= est["B@25"]["mean"] <= est["B@25"]["high"]
    assert analysis.bootstrap(killed, vbd, resamples=500, seed=1) != a


def test_bootstrap_draws_eight_dimensions_with_fixed_denominator():
    # every dimension testable and detected: every resample detects all 8
    vbd = {d: [f"V{d}"] for d in rules.DIMENSIONS}
    out = analysis.bootstrap({("B", 25): {f"V{d}" for d in rules.DIMENSIONS}}, vbd, resamples=200)["estimates"]["B@25"]
    assert out["mean"] == out["low"] == out["high"] == 1.0
    # nothing testable: always 0
    assert analysis.bootstrap({("B", 25): set()}, {}, resamples=50)["estimates"]["B@25"]["mean"] == 0.0


def test_percentile_interpolates():
    assert analysis.percentile([0, 1], 50) == 0.5 and analysis.percentile([3], 97.5) == 3 and analysis.percentile([0, 1, 2, 3], 100) == 3


# ---------------------------------------------------------------------------- gates (2.17)

def det_for(dB, dC, kB=None, kC=None, kA25=0, T=6):
    def arm(counts, kills_):
        return {b: {"dimensions_detected_count": counts[b], "killed_variants": [f"M{i}" for i in range((kills_ or counts)[b])]} for b in rules.BUDGETS}
    a = {"B": arm(dB, kB), "C": arm(dC, kC), "A": {25: {"killed_variants": [f"M{i}" for i in range(kA25)]}}}
    return {"T": T, "arms": a}


DISC = {"recall": {"B": 0.2, "C": 0.5}, "precision": {"B": 0.4, "C": 0.5}, "stability_jaccard": {"B": 0.3, "C": 0.5}}


def test_gate_success():
    g = analysis.gates(det_for({25: 0, 50: 1, 100: 1}, {25: 1, 50: 2, 100: 3}), DISC)
    assert g["verdict"] == "SUCCESS_FOR_BCE" and g["tier"] == "NORMAL"


def test_gate_inconclusive_small_recall_difference_and_single_budget_advantage():
    d = {**DISC, "recall": {"B": 0.2, "C": 0.3}}
    assert analysis.gates(det_for({25: 0, 50: 1, 100: 1}, {25: 1, 50: 2, 100: 3}), d)["verdict"] == "INCONCLUSIVE"
    g = analysis.gates(det_for({25: 1, 50: 1, 100: 1}, {25: 2, 50: 1, 100: 1}), DISC)  # advantage at 25 only: C > B at 100 fails
    assert g["verdict"] == "INCONCLUSIVE" and g["inconclusive_by_named_condition"] is True
    # advantage at 100 only meets every success condition as written; success takes precedence (map, interpretation 1) and the overlap is flagged
    g = analysis.gates(det_for({25: 1, 50: 1, 100: 1}, {25: 1, 50: 1, 100: 2}), DISC)
    assert g["verdict"] == "SUCCESS_FOR_BCE" and g["inconclusive_by_named_condition"] is True


def test_gate_against_requires_b_ge_c_on_both_recall_and_detection_at_100():
    d = {**DISC, "recall": {"B": 0.5, "C": 0.5}}
    assert analysis.gates(det_for({25: 0, 50: 0, 100: 2}, {25: 0, 50: 0, 100: 2}), d)["verdict"] == "EVIDENCE_AGAINST_THESIS"
    assert analysis.gates(det_for({25: 0, 50: 0, 100: 1}, {25: 0, 50: 0, 100: 2}), d)["verdict"] == "INCONCLUSIVE"


def test_gate_success_needs_precision_and_jaccard():
    base = det_for({25: 0, 50: 1, 100: 1}, {25: 1, 50: 2, 100: 3})
    assert analysis.gates(base, {**DISC, "precision": {"B": 0.5, "C": 0.4}})["verdict"] != "SUCCESS_FOR_BCE"
    assert analysis.gates(base, {**DISC, "stability_jaccard": {"B": 0.9, "C": 0.39}})["verdict"] != "SUCCESS_FOR_BCE"


def test_gate_pending_without_discovery_scores_and_original_gate_is_labelled():
    g = analysis.gates(det_for({25: 0, 50: 1, 100: 1}, {25: 1, 50: 2, 100: 3}), None)
    assert g["verdict"] == "PENDING_DISCOVERY_SCORES" and g["detection"]["C_gt_B_at_100"] is True
    g2 = analysis.gates(det_for({25: 0, 50: 1, 100: 1}, {25: 1, 50: 2, 100: 3}, kA25=0), DISC)
    assert "construction-biased" in g2["original_label"] and g2["original_verdict"] == "SUCCESS_FOR_BCE"
    g3 = analysis.gates(det_for({25: 0, 50: 1, 100: 1}, {25: 1, 50: 2, 100: 3}, kA25=1), DISC)  # C kills 1 at 25 = A: not C > A
    assert g3["verdict"] == "SUCCESS_FOR_BCE" and g3["original_verdict"] != "SUCCESS_FOR_BCE"


def test_tiers():
    assert [analysis.tier(t) for t in (3, 4, 5, 6)] == ["INVALID", "EXPLORATORY", "NORMAL", "NORMAL"]


# ---------------------------------------------------------------------------- the drift smoke test (2.15)

def test_drift_plan_counts_and_stages():
    jobs = drift.plan(info_fixture())
    assert len(jobs) == 35 + 3 * 3
    assert sum(1 for j in jobs if j["variant"] == "clean") == 35 and all(j["rep"] == 0 for j in jobs if j["variant"] == "clean")
    muts = [j for j in jobs if j["variant"] == "mutant"]
    assert {j["instance"] for j in muts} == {"T1"} and sorted({j["rep"] for j in muts}) == [0, 1, 2]
    assert all(j["system"] == SYSTEM for j in jobs if j["variant"] == "clean") and all(j["system"] != SYSTEM for j in muts)
    assert len({runtime.job_key(j) for j in jobs}) == len(jobs)


def drift_records(mutant_codes, clean_codes=None, models=("m1",)):
    out = []
    for j in drift.plan(info_fixture()):
        if j["variant"] == "clean":
            v = (clean_codes or {}).get(j["instance"], [])
        else:
            v = mutant_codes.get(j["subject"], [[], [], []])[j["rep"]]
        out.append({"key": runtime.job_key(j), "variant": j["variant"], "subject": j["subject"], "instance": j["instance"], "rep": j["rep"],
                    "violations": v, "models": list(models), "transport_failure": False, "replies": ["ok"]})
    return out


GOOD = {"M01": [["CODE_A"]] * 3, "M02": [["CODE_B"]] * 3, "M03": [["CODE_C"]] * 3}


def test_drift_clean_pass():
    v = drift.evaluate(drift_records(GOOD), info_fixture(), ["m1"])
    assert v["potentially_invalid"] is False and v["drift_suspect"] == [] and v["served_model_identity"] == drift.SAME


def test_drift_suspect_below_two_of_three():
    m = {**GOOD, "M02": [["CODE_B"], [], []], "M03": [["CODE_C"], ["CODE_C"], []]}
    v = drift.evaluate(drift_records(m), info_fixture(), ["m1"])
    assert v["drift_suspect"] == ["M02"] and v["mutants"]["M03"]["primary_code_runs"] == 2 and v["potentially_invalid"] is False


def test_drift_smoke_violation_flags_potentially_invalid():
    sid = engine.baseline_scenarios()[4]["id"]
    v = drift.evaluate(drift_records(GOOD, clean_codes={sid: ["R5"]}), info_fixture(), ["m1"])
    assert v["potentially_invalid"] is True and v["smoke_violations"] == [{"scenario": sid, "codes": ["R5"]}]


def test_drift_served_model_difference_and_unestablished_identity():
    assert drift.evaluate(drift_records(GOOD, models=("m2",)), info_fixture(), ["m1"])["potentially_invalid"] is True
    none = drift.evaluate(drift_records(GOOD, models=()), info_fixture(), ["m1"])
    assert none["served_model_identity"] == drift.UNESTABLISHED and none["potentially_invalid"] is False and none["served_model_note"]
    nonref = drift.evaluate(drift_records(GOOD), info_fixture(), [])
    assert nonref["served_model_identity"] == drift.UNESTABLISHED


def test_drift_run_is_recorded_once_and_never_rerun(tmp_path):
    def script(job):
        return {"M01": ["CODE_A"], "M02": ["CODE_B"], "M03": ["CODE_C"]}.get(job["subject"], [])
    session = Session(tmp_path / "drift", Fake(script))
    verdict = drift.run(session, info_fixture(), ["m1"])
    assert verdict["drift_suspect"] == [] and len(session.executor.jobs) == 44
    assert session.completed(drift.STATUS_DONE)[0]["potentially_invalid"] is False
    with pytest.raises(RuntimeError):
        drift.run(Session(tmp_path / "drift", Fake()), info_fixture(), ["m1"])


def test_drift_resumes_after_a_transport_failure(tmp_path):
    state = {"fail": True}
    fake = Fake(fail=lambda j: state["fail"] and j["variant"] == "mutant" and j["subject"] == "M01" and j["rep"] == 1)
    with pytest.raises(Incomplete):
        drift.run(Session(tmp_path / "drift", fake), info_fixture(), ["m1"])
    state["fail"] = False
    second = Fake()
    drift.run(Session(tmp_path / "drift", second), info_fixture(), ["m1"])
    assert len(second.jobs) == 1  # only the run without a record


# ---------------------------------------------------------------------------- the oracle audit (A3.5)

def audit_fixture(tmp_path):
    script = killing({("B-r1-p00", "M01"): [[], ["CODE_A"], ["CODE_A"]], ("C-r1-p00", "M02"): [["CODE_B"], ["CODE_B"], []],
                      ("B-r1-p01", "clean"): [[], ["NAT"], ["NAT"]]})
    layout = {1: {0: "valid", 1: "valid"}}
    session, by_arm, stats, info, table, summary = run_all(tmp_path, script, layout, curtail=False)
    return session, by_arm, info, table


def test_audit_units_and_strata(tmp_path):
    session, by_arm, info, table = audit_fixture(tmp_path)
    units = audit.build_units(session.records(), table, info)
    s1 = {u: v for u, v in units.items() if v["stratum"] == audit.S1}
    assert sorted(s1) == [f"{audit.S1}|B-r1-p00|M01", f"{audit.S1}|C-r1-p00|M02"]
    assert units[f"{audit.S1}|B-r1-p00|M01"]["record"]["rep"] == 1  # the lowest repetition containing the intended code
    assert units[f"{audit.S1}|C-r1-p00|M02"]["record"]["rep"] == 0
    s2 = [u for u, v in units.items() if v["stratum"] == audit.S2]
    assert s2 == [f"{audit.S2}|B-r1-p01|clean"] and units[s2[0]]["record"]["rep"] == 1  # lowest clean repetition with a code
    s3 = [v for v in units.values() if v["stratum"] == audit.S3]
    assert s3 and all(v["record"]["rep"] == 0 and not v["record"]["violations"] for v in s3)
    assert not any("A" == v["record"].get("arm") for v in units.values())


def test_audit_sampling_is_reproducible_and_capped(tmp_path):
    units = {f"{audit.S1}|u{i:03d}": {"stratum": audit.S1} for i in range(50)}
    units.update({f"{audit.S2}|u{i:03d}": {"stratum": audit.S2} for i in range(5)})
    a, b = audit.sample_units(units), audit.sample_units(units)
    assert a == b and len(a[audit.S1]) == 20 and len(a[audit.S2]) == 5 and a[audit.S3] == []
    import random
    assert a[audit.S1] == random.Random(20260311).sample(sorted(u for u in units if u.startswith(audit.S1)), 20)
    assert audit.sample_units(units, seed=1) != a


def test_audit_packet_does_not_leak_codes_arm_or_mutant(tmp_path):
    session, by_arm, info, table = audit_fixture(tmp_path)
    units = audit.build_units(session.records(), table, info)
    rule_text = {"CODE_A": "Never do A.", "CODE_B": "Never do B.", "NAT": "Never do N.", "CODE_C": "Never do C."}
    packet, key = audit.build_packet(units, audit.sample_units(units), rule_text)
    blob = json.dumps(packet)
    for leaked in ("CODE_A", "CODE_B", "NAT", "M01", "M02", "B-r1", "C-r1", "clean", "S1_", "stratum"):
        assert leaked not in blob, leaked
    assert set(packet["rules"]) == {"R-A", "R-B", "R-C", "R-D"} and "Never do A." in packet["rules"].values()
    assert len(packet["units"]) == len(key["units"]) and key["rule_letters"]["R-A"] == "CODE_A"
    assert audit.build_packet(units, audit.sample_units(units), rule_text) == (packet, key)  # deterministic


def test_audit_scoring_and_kills_removed_sensitivity_do_not_alter_results(tmp_path):
    session, by_arm, info, table = audit_fixture(tmp_path)
    units = audit.build_units(session.records(), table, info)
    packet, key = audit.build_packet(units, audit.sample_units(units), {"CODE_A": "a", "CODE_B": "b", "NAT": "n", "CODE_C": "c"})
    letter = {c: l for l, c in key["rule_letters"].items()}
    answers = {}
    for pid, k in key["units"].items():
        if k["stratum"] == audit.S1 and k["mutant"] == "M01":
            answers[pid] = {"violated_rules": [], "reason": "not a violation"}  # the reviewer rejects this kill
        elif k["stratum"] == audit.S3:
            answers[pid] = {"violated_rules": []}
        else:
            answers[pid] = {"violated_rules": [letter[c] for c in k["oracle_codes"]]}
    before = copy.deepcopy(table)
    scored = audit.score(key, answers)
    sens = audit.kills_removed_sensitivity(table, info, key, scored)
    assert table == before  # no rescoring
    assert scored[audit.S1]["units"] == 2 and scored[audit.S1]["agree"] == 1 and scored[audit.S1]["disagreements"][0]["reason"] == "not a violation"
    assert scored[audit.S2]["agree"] == scored[audit.S2]["units"] == 1 and scored[audit.S3]["agree"] == scored[audit.S3]["units"]
    assert sens["rejected_kills"] == [{"scenario": "B-r1-p00", "mutant": "M01"}] and sens["label"].startswith("sensitivity")
    assert sens["arms"]["B"][25]["killed_variants"] == []
    primary = analysis.detection_block(table, info, with_bootstrap=False)
    assert primary["arms"]["B"][25]["killed_variants"] == ["M01"]


def test_audit_stratum3_disagreement_when_reviewer_finds_a_violation():
    key = {"rule_letters": {"R-A": "X"}, "units": {"A001": {"unit": "S3|r|clean", "stratum": audit.S3, "oracle_codes": [], "intended_codes": [], "mutant": None}}}
    out = audit.score(key, {"A001": {"violated_rules": ["R-A"], "reason": "missed"}})
    assert out[audit.S3]["agree"] == 0 and out[audit.S3]["disagreements"][0]["reviewer_codes"] == ["X"]


# ---------------------------------------------------------------------------- freeze verification and isolation

def test_hash_comparison_flags_changed_missing_and_uncommitted_files():
    good = preflight.sha256_bytes(b"a")
    files = {"f1": good, "f2": good, "f3": good, "f4": good}
    work = {"f1": b"a", "f2": b"CHANGED", "f4": b"a"}
    committed = {"f1": b"a", "f2": b"a", "f3": b"a"}
    problems = preflight.compare_hashes(files, work.get, committed.get)
    assert "working copy hash differs: f2" in problems and "missing file: f3" in problems
    assert "file not in the freeze commit: f4" in problems
    assert preflight.compare_hashes({"f1": good}, work.get, committed.get) == []


def test_dirty_paths_ignores_only_the_results_directory():
    porcelain = " M detect/analysis.py\n?? experiments/step3/results/detection/runs.jsonl\n?? new.txt\n"
    assert preflight.dirty_paths(porcelain) == ["detect/analysis.py", "new.txt"]


def test_detect_never_reads_discovery_outputs_or_gold_into_bce():
    for path in sorted((ROOT / "detect").glob("*.py")):
        if path.name == "judge.py":  # Amendment 5: the discovery judge scores discovery outputs against gold by design (see test_step3e_a5)
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        for c in consts:
            assert "normalized" not in c and "discovery/" not in c and "_raw.json" not in c and "gold_hidden" not in c, (path.name, c[:50])
    for path in sorted((ROOT / "bce").glob("*.py")):
        assert not re.search(r"^\s*(from|import)\s+detect", path.read_text(encoding="utf-8"), re.M), path


def test_frozen_constants():
    assert (rules.CLEAN_REPS, rules.MUTANT_REPS, rules.KILL_MUTANT_MIN) == (3, 3, 2)
    assert rules.BUDGETS == (25, 50, 100) and rules.DENOMINATOR == 8 and rules.SLOTS_PER_RUN == 20 and rules.RUNS_PER_ARM == 5
    assert (rules.BOOTSTRAP_RESAMPLES, rules.BOOTSTRAP_SEED, rules.AUDIT_SEED) == (10000, 20260311, 20260311)
    assert (rules.RECALL_MARGIN, rules.JACCARD_MIN, rules.DRIFT_MIN_PRIMARY, rules.DEGENERATE_GATE) == (0.2, 0.4, 2, 0.10)
    assert rules.DIMENSIONS == ("G01", "G02", "G04", "G05", "G07", "G12", "G13", "G16")
    assert sorted(rules.CLASS_OF) == sorted(rules.DIMENSIONS) and sum(1 for c in rules.CLASS_OF.values() if c == "U_NEW_VALUE") == 4
