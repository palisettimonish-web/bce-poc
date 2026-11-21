"""Tests for Amendment 5 (pre-3e). Synthetic fixtures, a scripted fake executor and temporary git repositories only: no agent or
LLM call, no real 3d scenario or candidate, no 3e result. Fixtures come from the Amendment 4 suite."""

import ast
import json
import math
import re
import subprocess
from pathlib import Path

import pytest

from bce import dsl
from detect import analysis, audit, drift, judge, kills, preflight, rules, runner, slots
from detect.session import AuthenticationFailure, Session, classify_failure, is_rejected
from test_step3e import Fake, info_fixture, killing, make_slots, raw_scenario, run_all, small_layout, write_arm

ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------- failing executors

def attempts(kind):
    types = {"reject": ["BadRequestError"] * 3, "auth": ["ClientAuthenticationError"] * 3, "transport": ["APIConnectionError"] * 3,
             "mixed": ["BadRequestError", "BadRequestError", "APITimeoutError"], "short": ["BadRequestError"] * 2}[kind]
    return [{"attempt": n + 1, "error": f"{t}: synthetic"} for n, t in enumerate(types)]


class Failing(Fake):
    """`behave(job)` is None (the job completes) or one of the kinds above (every attempt of the invocation fails that way)."""

    def __init__(self, behave, script=lambda job: [], models=("m1",)):
        super().__init__(script, lambda job: behave(job) is not None, models)
        self.behave = behave

    def __call__(self, job):
        rec = super().__call__(job)
        kind = self.behave(job)
        if kind:
            rec["attempt_errors"] = attempts(kind)
        return rec


def one_scenario_layout():
    return {1: {0: "valid"}}


def run_failing(tmp_path, behave, script=lambda job: [], layout=None):
    by_arm, stats = make_slots(tmp_path, layout or one_scenario_layout())
    info = info_fixture()
    session = Session(tmp_path / "det", Failing(behave, script))
    summary = runner.run_detection(session, by_arm, info)
    return session, by_arm, stats, info, summary


# ---------------------------------------------------------------------------- A5.1 PROVIDER_REJECTED (B1)

def test_classify_failure():
    ok = {"transport_failure": False}
    assert classify_failure(ok) is None
    assert classify_failure({"transport_failure": True, "attempt_errors": attempts("reject")}) == rules.TERMINAL_REJECTED
    assert classify_failure({"transport_failure": True, "attempt_errors": attempts("short")}) == "TRANSPORT"  # not every attempt was made
    assert classify_failure({"transport_failure": True, "attempt_errors": attempts("mixed")}) == "TRANSPORT"
    assert classify_failure({"transport_failure": True, "attempt_errors": attempts("transport")}) == "TRANSPORT"
    assert classify_failure({"transport_failure": True, "attempt_errors": attempts("auth")}) == "AUTH"
    assert classify_failure({"transport_failure": True}) == "TRANSPORT"
    assert not set(rules.REJECTED_ERROR_TYPES) & set(rules.AUTH_ERROR_TYPES)


def test_rejected_clean_run_is_terminal_is_never_retried_and_invents_no_outcome(tmp_path):
    behave = lambda job: "reject" if (job["instance"], job["variant"], job["rep"]) == ("B-r1-p00", "clean", 1) else None
    session, by_arm, stats, info, summary = run_failing(tmp_path, behave)
    rec = next(r for r in session.records() if r.get("terminal_state"))
    assert rec["terminal_state"] == rules.TERMINAL_REJECTED and rec["transport_failure"] is True and is_rejected(rec)
    assert rec["violations"] == [] and rec["replies"] == [] and rec["calls"] == [] and rec["ledger"] == []  # no outcome fabricated
    assert not any(j["instance"] == "B-r1-p00" and j["variant"] == "mutant" for j in session.executor.jobs)  # nothing more runs for it
    assert summary["provider_rejected_runs"] == 1 and summary["transport_failures"] == 0
    table = kills.build_table(session.records(), by_arm, info)  # the experiment completes: a rejected pair is not INCOMPLETE
    row = table["B-r1-p00"]
    assert set(row["pairs"].values()) == {kills.REJECTED} and row["clean_rejected"] is True
    assert all(v == [] for v in row["attributable"].values()) and all(v == [] for v in row["any_code"].values())
    # a later invocation does not retry it
    again = Failing(lambda job: None)
    Session(tmp_path / "det", again).ensure(session.executor.jobs[0])
    assert again.jobs == []
    session2 = Session(tmp_path / "det", again)
    session2.runs.read()
    assert session2.have()[rec["key"]]["terminal_state"] == rules.TERMINAL_REJECTED


def test_rejected_mutant_run_rejects_that_pair_only_and_the_kill_is_not_imputed(tmp_path):
    behave = lambda job: "reject" if (job["instance"], job["subject"], job["rep"]) == ("B-r1-p00", "M01", 0) else None
    script = killing({("B-r1-p00", "M01"): [["CODE_A"]] * 3, ("B-r1-p00", "M02"): [["CODE_B"]] * 3})
    session, by_arm, stats, info, summary = run_failing(tmp_path, behave, script)
    row = kills.build_table(session.records(), by_arm, info)["B-r1-p00"]
    assert row["pairs"]["M01"] == kills.REJECTED and row["attributable"]["M01"] == [] and row["any_code"]["M01"] == []
    assert row["pairs"]["M02"] == kills.COMPLETE and row["attributable"]["M02"] == ["CODE_B"]  # the other mutants are untouched
    assert row["clean_rejected"] is False and row["rejected_executions"] == 1
    assert not any(j["subject"] == "M01" and j["instance"] == "B-r1-p00" and j["rep"] > 0 for j in session.executor.jobs)


def test_a_rejected_third_mutant_run_rejects_the_pair_even_when_two_completed_runs_show_the_code(tmp_path):
    behave = lambda job: "reject" if (job["instance"], job["subject"], job["rep"]) == ("B-r1-p00", "M01", 2) else None
    session, by_arm, stats, info, summary = run_failing(tmp_path, behave, killing({("B-r1-p00", "M01"): [["CODE_A"]] * 3}))
    row = kills.build_table(session.records(), by_arm, info)["B-r1-p00"]
    assert row["pairs"]["M01"] == kills.REJECTED and row["attributable"]["M01"] == []  # conservative: not a kill (A5.1 interpretation)


def test_a_transport_failure_stays_retryable_and_is_not_rejected(tmp_path):
    flaky = {"on": True}
    behave = lambda job: "transport" if flaky["on"] and (job["instance"], job["variant"], job["rep"]) == ("B-r1-p00", "clean", 0) else None
    by_arm, stats = make_slots(tmp_path, one_scenario_layout())
    info = info_fixture()
    session = Session(tmp_path / "det", Failing(behave))
    with pytest.raises(runner.Incomplete):
        runner.run_detection(session, by_arm, info)
    flaky["on"] = False
    runner.run_detection(Session(tmp_path / "det", Failing(behave)), by_arm, info)
    assert not any(is_rejected(r) for r in Session(tmp_path / "det", None).records())


def test_analysis_reports_rejections_per_arm_and_budget_apart_from_dsl_invalidity(tmp_path):
    behave = lambda job: "reject" if (job["instance"], job["variant"], job["rep"]) == ("B-r1-p00", "clean", 0) else None
    session, by_arm, stats, info, summary = run_failing(tmp_path, behave)
    table = kills.build_table(session.records(), by_arm, info)
    res = analysis.analyze(table, by_arm, stats, info, None, analysis.generation_tokens(tmp_path), resamples=10,
                           records=session.records(), baseline=["m1"])
    rej = res["provider_rejections"]
    assert rej["final_rejected_runs"] == 1 and rej["scenarios"] == ["B-r1-p00"]
    assert rej["by_arm"]["B"][25] == {"rejected_runs": 1, "scenarios_with_a_rejected_run": 1, "rejected_pairs": 3}
    assert rej["by_arm"]["C"][25]["rejected_pairs"] == 0
    assert res["discovery_side_inputs"]["B"]["invalid_slots"] == 0  # a rejection is not a DSL-invalid scenario
    assert res["detection"]["arms"]["B"][25]["killed_variants"] == []


# ---------------------------------------------------------------------------- A5.2 auth fail-fast

def test_authentication_failure_stops_at_once_is_logged_and_resumes(tmp_path):
    by_arm, stats = make_slots(tmp_path, one_scenario_layout())
    info = info_fixture()
    bad = Failing(lambda job: "auth")
    with pytest.raises(AuthenticationFailure):
        runner.run_detection(Session(tmp_path / "det", bad), by_arm, info)
    assert len(bad.jobs) == 1  # nothing else was attempted
    logged = Session(tmp_path / "det", None).records()
    assert len(logged) == 1 and logged[0]["transport_failure"] is True and "terminal_state" not in logged[0]
    good = Fake()
    runner.run_detection(Session(tmp_path / "det", good), by_arm, info)  # fixed credentials: the failed job is retried and completes
    assert any(j["instance"] == logged[0]["instance"] and j["rep"] == logged[0]["rep"] for j in good.jobs)


# ---------------------------------------------------------------------------- A5.4 served-model guard

def test_served_model_guard_stops_unless_acknowledged_or_without_a_baseline(tmp_path):
    job = {"stage": "3E", "variant": "clean", "subject": "clean", "instance": "X", "rep": 0, "scenario": {"id": "X"}, "system": "s"}
    with pytest.raises(runner.ServedModelChange):
        Session(tmp_path / "a", Fake(models=("m2",)), guard=runner.served_guard(["m1"], False)).ensure(job)
    Session(tmp_path / "b", Fake(models=("m2",)), guard=runner.served_guard(["m1"], True)).ensure(job)  # acknowledged
    Session(tmp_path / "c", Fake(models=("m1",)), guard=runner.served_guard(["m1"], False)).ensure(job)  # same model
    assert runner.served_guard([], False) is None  # UNESTABLISHED identity: no baseline, no guard
    logged = Session(tmp_path / "a", None).records()
    assert len(logged) == 1 and runner.served_mismatches(logged, ["m1"]) == [logged[0]["key"]]  # the offending record is kept
    assert runner.served_mismatches(logged, []) == []


def test_run_detection_records_baseline_mismatches_and_acknowledgement(tmp_path):
    by_arm, stats = make_slots(tmp_path, one_scenario_layout())
    session = Session(tmp_path / "det", Fake(models=("m2",)), guard=runner.served_guard(["m1"], True))
    summary = runner.run_detection(session, by_arm, info_fixture(), baseline=["m1"], acknowledged={"served_model_change": True})
    assert summary["served_model_baseline"] == ["m1"] and summary["served_models"] == ["m2"]
    assert summary["served_model_mismatches"] and summary["acknowledged"] == {"served_model_change": True}
    table = kills.build_table(session.records(), by_arm, info_fixture())
    res = analysis.analyze(table, by_arm, {"B": stats["B"], "C": stats["C"]}, info_fixture(), None, analysis.generation_tokens(tmp_path),
                           resamples=10, records=session.records(), baseline=["m1"])
    assert res["served_models_report"]["mismatching_runs"] == summary["served_model_mismatches"]
    assert res["served_models_report"]["by_arm"]["B"] == ["m2"]


# ---------------------------------------------------------------------------- A5.5 results integrity

def good_record(**over):
    return {"key": "k", "git_sha": "good", "agent_config_hash": "cfg", "candidates_sha": "cand", **over}


def test_record_problems_ancestry_and_frozen_hashes():
    ancestor = lambda commit, sha: sha == "good"
    assert preflight.record_problems([good_record()], "freeze", "cfg", "cand", ancestor) == []
    assert any("does not descend" in p for p in preflight.record_problems([good_record(git_sha="bad")], "freeze", "cfg", "cand", ancestor))
    assert any("does not descend" in p for p in preflight.record_problems([good_record(git_sha=None)], "freeze", "cfg", "cand", ancestor))
    assert any("agent_config_hash" in p for p in preflight.record_problems([good_record(agent_config_hash="other")], "freeze", "cfg", "cand", ancestor))
    assert any("candidates_sha" in p for p in preflight.record_problems([good_record(candidates_sha="other")], "freeze", "cfg", "cand", ancestor))
    asked = []
    preflight.record_problems([good_record(), good_record(key="k2")], "freeze", "cfg", "cand", lambda c, s: asked.append(s) or True)
    assert asked == ["good"]  # one ancestry query per distinct SHA


def make_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()

    def g(*args, check=True):
        r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", *args], cwd=repo, capture_output=True)
        assert r.returncode == 0 or not check, r.stderr
        return r

    g("init", "-q")
    monkeypatch.setattr(preflight, "ROOT", repo)
    monkeypatch.setattr(preflight, "git", lambda *a: subprocess.run(["git", *a], cwd=repo, capture_output=True))
    monkeypatch.setattr(preflight, "_pre3d_problems", lambda: [])
    return repo, g


def commit_file(repo, g, rel, text, message="c"):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    g("add", rel)
    g("commit", "-q", "-m", message)
    return g("rev-parse", "HEAD").stdout.decode().strip()


def test_sealed_and_history_problems_with_a_real_git_repo(tmp_path, monkeypatch):
    repo, g = make_repo(tmp_path, monkeypatch)
    commit_file(repo, g, "README", "x")
    results = repo / "experiments/step3/results/drift"
    assert preflight.history_problems(results, "drift") == []
    assert "no results found" in preflight.sealed_problems(results, "drift")[0]
    results.mkdir(parents=True)
    (results / "runs.jsonl").write_text('{"a": 1}\n', encoding="utf-8")
    assert "not committed" in preflight.sealed_problems(results, "drift")[0]  # untracked results are not sealed
    g("add", "-f", str(results / "runs.jsonl"))
    g("commit", "-q", "-m", "seal drift")
    assert preflight.sealed_problems(results, "drift") == []
    (results / "runs.jsonl").write_text('{"a": 2}\n', encoding="utf-8")
    assert "not committed and unmodified" in preflight.sealed_problems(results, "drift")[0]  # a modified log is not sealed
    g("checkout", "--", str(results / "runs.jsonl"))
    (results / "runs.jsonl").unlink()
    results.rmdir()
    assert "never re-run" in preflight.history_problems(results, "drift")[0]  # a deleted committed directory blocks a re-run


def test_verify_through_a_temporary_repo_catches_every_tamper_case(tmp_path, monkeypatch):
    repo, g = make_repo(tmp_path, monkeypatch)
    files = {"detect/x.py": "x = 1\n", "test_step3e.py": "t = 1\n"}
    inputs = {"scenarios.py": "S = 1\n"}
    sealed = {"experiments/step3/scenarios/B.json": "{}\n"}
    for rel, text in {**files, **inputs, **sealed}.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    g("add", ".")
    g("commit", "-q", "-m", "freeze")
    c1 = g("rev-parse", "HEAD").stdout.decode().strip()
    h = lambda d: {k: preflight.sha256_bytes(v.encode()) for k, v in d.items()}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"git_sha": c1, "sealed_3d_commit": c1, "amendment4_freeze_commit": c1, "files": h(files),
                                    "frozen_input_hashes": h(inputs), "sealed_3d_files": h(sealed)}), encoding="utf-8")

    def reset():
        g("reset", "-q", "--hard", c1)
        g("clean", "-fdq")

    assert preflight.verify(manifest) == []
    (repo / "scenarios.py").write_text("S = 2\n", encoding="utf-8")
    problems = preflight.verify(manifest)
    assert any("working copy hash differs: scenarios.py" in p for p in problems) and any("working tree not clean" in p for p in problems)
    g("commit", "-qam", "edit the pinned scenarios file")  # committed edits are caught too: Arm A and the drift scenarios are pinned (I4)
    assert any("working copy hash differs: scenarios.py" in p for p in preflight.verify(manifest))
    reset()
    (repo / "detect/x.py").write_text("x = 2\n", encoding="utf-8")
    g("commit", "-qam", "edit detect")
    assert any("working copy hash differs: detect/x.py" in p for p in preflight.verify(manifest))
    reset()
    commit_file(repo, g, "detect/new.py", "n = 1\n")
    assert "tracked but not in the freeze manifest: detect/new.py" in preflight.verify(manifest)
    reset()
    commit_file(repo, g, "experiments/step3/scenarios/B.json", "{ }\n")
    assert any("sealed 3d artifact" in p or "working copy hash differs: experiments/step3/scenarios/B.json" in p for p in preflight.verify(manifest))
    reset()
    c2 = commit_file(repo, g, "README", "later")
    later = json.loads(manifest.read_text(encoding="utf-8"))
    later["amendment4_freeze_commit"] = c2  # Amendment 4 cannot come after the Amendment 5 freeze
    manifest.write_text(json.dumps(later), encoding="utf-8")
    assert any("Amendment 4 freeze commit is not an ancestor" in p for p in preflight.verify(manifest))


def test_the_real_manifest_pins_scenarios_py_once_frozen():
    if not preflight.MANIFEST.exists():
        pytest.skip("the Amendment 5 freeze manifest does not exist yet")
    doc = json.loads(preflight.MANIFEST.read_text(encoding="utf-8"))
    assert "scenarios.py" in doc["frozen_input_hashes"] and "amendment4_freeze_commit" in doc and doc["no_3e_results_at_freeze"] is True
    assert "detect/judge.py" in doc["files"] and "test_step3e_a5.py" in doc["files"]


# ---------------------------------------------------------------------------- A5.3 slot-level accounting

def test_slot_based_diagnostic_sits_beside_the_preregistered_returned_scenario_check(tmp_path):
    by_arm, stats = make_slots(tmp_path, {1: {0: "valid", 1: "valid", 2: "valid"}})  # four runs returned nothing
    c = analysis.discovery_counts(by_arm, stats)["C"]
    assert c["scenario_validity"] == 1.0  # preregistered metric 4 is unchanged: every returned scenario is valid
    assert c["slot_invalid_or_missing_fraction"] == 97 / 100 and c["valid_slots"] == 3
    session = Session(tmp_path / "det", Fake())
    runner.run_detection(session, by_arm, info_fixture())
    table = kills.build_table(session.records(), by_arm, info_fixture())
    checks = analysis.analyze(table, by_arm, stats, info_fixture(), None, analysis.generation_tokens(tmp_path), resamples=10)["invalid_experiment_checks"]
    assert checks["arm_C_over_half_dsl_invalid"] is False  # the preregistered check is not replaced
    assert checks["diagnostic_slot_based"]["arm_C_over_half_invalid_or_missing_slots"] is True
    assert checks["diagnostic_slot_based"]["arm_C_invalid_or_missing_slot_fraction"] == 0.97


# ---------------------------------------------------------------------------- A5.5 / I5 oracle rule text

def oracle_codes():
    return set(re.findall(r'violations\.append\("([A-Z0-9_]+)"\)', (ROOT / "oracle.py").read_text(encoding="utf-8")))


def test_every_oracle_code_has_rule_text_and_no_text_names_a_code():
    codes, text = oracle_codes(), audit.full_rule_text()
    assert len(codes) == 14 and codes <= set(text)
    for code, sentence in text.items():
        assert not re.search(r"\bR\d+[A-Z]?_|EXPOSURE_", sentence) and code not in sentence, code
        assert not re.search(r"\b(arm|mutant|oracle|M\d\d)\b", sentence, re.I), code
    assert set(audit.SUPPLEMENTARY_RULE_TEXT) == set(audit.SPEC_RULE_OF) and len(audit.SUPPLEMENTARY_RULE_TEXT) == 5
    assert len(audit.rule_letters(text)) == len(text)


def test_supplementary_text_never_overrides_the_catalogue_and_maps_to_real_spec_rules():
    assert audit.full_rule_text({"R4_DUPLICATE_REFUND": "custom"})["R4_DUPLICATE_REFUND"] == "custom"
    spec = (ROOT / "truth_spec.md").read_text(encoding="utf-8")
    for code, rule in audit.SPEC_RULE_OF.items():
        assert f"**{rule}:" in spec and code in oracle_codes()


# ---------------------------------------------------------------------------- runner.main integration (monkeypatched)

@pytest.fixture
def env(tmp_path, monkeypatch):
    by_arm, stats = make_slots(tmp_path / "sc")
    info = info_fixture()
    holder = {"models": ("m1",), "executors": []}

    def script(job):
        return [info[job["subject"]]["primary_code"]] if job["variant"] == "mutant" else []

    def executor():
        holder["executors"].append(Fake(script, models=holder["models"]))
        return holder["executors"][-1]

    monkeypatch.setattr(runner.preflight, "verify", lambda: [])
    monkeypatch.setattr(runner.preflight, "sealed_problems", lambda d, label: [])
    monkeypatch.setattr(runner.preflight, "history_problems", lambda d, label: [])
    monkeypatch.setattr(runner, "_record_problems", lambda session: [])
    monkeypatch.setattr(runner.holdout_info, "load_admitted", lambda: info)
    monkeypatch.setattr(runner, "load_all_slots", lambda scenario_dir=None: (by_arm, stats))
    monkeypatch.setattr(drift, "reference_models", lambda runs_path=None: ["m1"])
    monkeypatch.setattr(rules, "DRIFT_DIR", tmp_path / "drift")
    monkeypatch.setattr(rules, "DETECTION_DIR", tmp_path / "detection")
    monkeypatch.setattr(runner, "_executor", executor)
    holder["tmp"] = tmp_path
    return holder


def statuses(directory, kind):
    return [r for r in Session(directory, None).status.read() if r.get("type") == kind]


def test_main_refuses_without_the_freeze_and_without_a_drift_run(env, monkeypatch, capsys):
    monkeypatch.setattr(runner.preflight, "verify", lambda: ["working tree not clean: x"])
    assert runner.main(["detect"]) == 1 and "pre-3e freeze verification failed" in capsys.readouterr().out
    monkeypatch.setattr(runner.preflight, "verify", lambda: [])
    assert runner.main(["detect"]) == 1 and "drift smoke test has not been completed" in capsys.readouterr().out
    assert not (env["tmp"] / "detection").exists()


def test_main_drift_then_detect_end_to_end_and_drift_is_never_rerun(env, capsys):
    assert runner.main(["drift"]) == 0
    assert statuses(rules.DRIFT_DIR, drift.STATUS_DONE)[0]["served_model_identity"] == drift.SAME
    assert runner.main(["drift"]) == 1 and "never re-run" in capsys.readouterr().out
    assert runner.main(["detect"]) == 0
    start = statuses(rules.DETECTION_DIR, runner.STATUS_DETECT_START)[0]
    assert start["served_model_guard"] == "ACTIVE" and start["served_model_baseline"] == ["m1"]
    done = statuses(rules.DETECTION_DIR, runner.STATUS_DETECT_DONE)[0]
    assert done["served_model_mismatches"] == [] and done["provider_rejected_runs"] == 0
    assert runner.main(["detect"]) == 1 and "already complete" in capsys.readouterr().out


def test_main_unestablished_model_needs_acknowledgement_and_disables_the_guard(env):
    env["models"] = ()
    assert runner.main(["drift"]) == 0
    assert statuses(rules.DRIFT_DIR, drift.STATUS_DONE)[0]["served_model_identity"] == drift.UNESTABLISHED
    assert runner.main(["detect"]) == 1 and not rules.DETECTION_DIR.exists()
    assert runner.main(["detect", "--acknowledge-unestablished-model"]) == 0
    start = statuses(rules.DETECTION_DIR, runner.STATUS_DETECT_START)[0]
    assert start["served_model_guard"] == "DISABLED_MODEL_UNESTABLISHED" and start["acknowledged"]["unestablished_model"] is True


def test_main_potentially_invalid_drift_needs_acknowledgement(env):
    env["models"] = ("m2",)  # a different served model than 3c: POTENTIALLY_INVALID
    assert runner.main(["drift"]) == 0
    assert statuses(rules.DRIFT_DIR, drift.STATUS_DONE)[0]["potentially_invalid"] is True
    assert runner.main(["detect"]) == 1
    assert runner.main(["detect", "--acknowledge-potentially-invalid"]) == 0
    assert statuses(rules.DETECTION_DIR, runner.STATUS_DETECT_START)[0]["acknowledged"]["potentially_invalid"] is True


def test_main_served_model_change_stops_and_resumes_only_when_acknowledged(env, capsys):
    assert runner.main(["drift"]) == 0
    env["models"] = ("m2",)  # the provider changes after the drift run
    assert runner.main(["detect"]) == 1 and "ServedModelChange" in capsys.readouterr().out
    assert runner.main(["detect"]) == 1 and "acknowledge-served-model-change" in capsys.readouterr().out
    assert runner.main(["detect", "--acknowledge-served-model-change"]) == 0
    done = statuses(rules.DETECTION_DIR, runner.STATUS_DETECT_DONE)[0]
    assert done["acknowledged"]["served_model_change"] is True and done["served_model_mismatches"]


def test_main_stops_on_integrity_problems(env, monkeypatch, capsys):
    assert runner.main(["drift"]) == 0
    monkeypatch.setattr(runner.preflight, "sealed_problems", lambda d, label: [f"{label}: results are not committed and unmodified: x"])
    assert runner.main(["detect"]) == 1 and "commit the drift results" in capsys.readouterr().out
    monkeypatch.setattr(runner.preflight, "sealed_problems", lambda d, label: [])
    monkeypatch.setattr(runner, "_record_problems", lambda session: ["k: git_sha 'x' does not descend from the freeze commit f"])
    assert runner.main(["detect"]) == 1 and "does not descend" in capsys.readouterr().out
    monkeypatch.setattr(runner, "_record_problems", lambda session: [])
    monkeypatch.setattr(runner.preflight, "history_problems", lambda d, label: [f"{label}: deleted"])
    assert runner.main(["drift"]) == 1  # a deleted drift directory blocks a second drift test


def test_main_authentication_failure_stops_with_a_clear_message(env, monkeypatch, capsys):
    assert runner.main(["drift"]) == 0
    monkeypatch.setattr(runner, "_executor", lambda: Failing(lambda job: "auth"))
    assert runner.main(["detect"]) == 1 and "AuthenticationFailure" in capsys.readouterr().out


# ---------------------------------------------------------------------------- judge (A5.6): synthetic data only

def candidate(run, position, **over):
    return {"candidate_id": f"C-r{run}-c{position}", "confidence": 0.8731, "behavior_dimension": f"dim {run}{position}",
            "description": "d", "why_not_covered": "w", "values_or_states": ["v"], "trigger_condition": "t", "interaction_dependencies": [],
            "risk_reason": "r", "scenario_template": "s", "novelty_claim": "n", "run_id": f"C-{run}", "position": position, **over}


def write_candidates(directory, extra_non_object=True):
    directory.mkdir(parents=True, exist_ok=True)
    for run in range(1, 6):
        cands = [candidate(run, p) for p in range(3)]
        if run == 1 and extra_non_object:
            cands.append({"raw": "not an object", "run_id": "C-1", "position": 3})
        (directory / f"C_run_{run:03d}_candidates.json").write_text(json.dumps({"meta": {}, "candidates": cands}), encoding="utf-8")


def judge_inputs(tmp_path):
    layout = small_layout(4)
    layout[1][4] = "invalid"
    for arm in ("B", "C"):
        write_arm(tmp_path / "sc", arm, layout, extra_positions=(20,))
    write_candidates(tmp_path / "norm")
    return tmp_path / "sc", tmp_path / "norm"


def test_judge_items_exclude_invalid_scenarios_and_non_object_candidates_and_flag_positions_over_19(tmp_path):
    sc, norm = judge_inputs(tmp_path)
    items, stats = judge.load_items(sc, norm)
    count = lambda arm, kind: sum(1 for i in items if i["arm"] == arm and i["kind"] == kind)
    assert (count("B", "scenario"), count("C", "scenario"), count("B", "candidate"), count("C", "candidate")) == (25, 25, 0, 15)
    assert stats["B"]["scenarios_invalid"] == 1 and stats["C"]["candidates_not_objects"] == 1 and stats["C"]["candidates"] == 15
    assert sum(1 for i in items if not i["in_budget"]) == 10 and all(i["position"] == 20 for i in items if not i["in_budget"])


def test_judge_items_hide_ids_confidence_arm_and_position_from_the_judge(tmp_path):
    sc, norm = judge_inputs(tmp_path)
    items, _ = judge.load_items(sc, norm)
    for item in items:
        assert not set(item["text"]) & {"candidate_id", "confidence", "run_id", "position"}
    pooled = judge.pool(items)
    shown = json.dumps(judge.render_items(pooled, list(pooled)))
    for leak in ("0.8731", "C-r1-c", "C-1", "run_id", '"arm"', "confidence", "candidate_id"):
        assert leak not in shown, leak
    assert any("behavior_dimension" in i["text"] for i in items) and any("messages" in i["text"] for i in items)


def test_judge_pooling_batching_and_sample_are_fixed_by_the_seed(tmp_path):
    sc, norm = judge_inputs(tmp_path)
    items, _ = judge.load_items(sc, norm)
    a = judge.pool(items)
    assert list(a) == [f"i{n:04d}" for n in range(1, 66)]
    assert judge.pool(items) == a  # deterministic
    assert [(it["arm"], it["kind"]) for it in a.values()] != sorted((it["arm"], it["kind"]) for it in a.values())  # shuffled, arms mixed
    batches = judge.batches(list(a))
    assert [len(x) for x in batches] == [40, 25] and max(len(x) for x in batches) <= rules.JUDGE_BATCH_MAX
    sample = judge.human_sample(list(a))
    assert len(sample) == math.ceil(0.2 * 65) == 13 and sample == judge.human_sample(list(reversed(list(a)))) and set(sample) <= set(a)


def test_judge_prompt_is_the_frozen_template_with_gold_and_covered_filled_in(tmp_path):
    sc, norm = judge_inputs(tmp_path)
    pooled = judge.pool(judge.load_items(sc, norm)[0])
    template = judge.PROMPT_PATH.read_text(encoding="utf-8")
    gold, covered = judge.load_gold(), judge.load_covered()
    prompt = judge.build_prompt(template, gold, covered, pooled, list(pooled)[:40])
    assert "{{" not in prompt and len(gold) == 17 and all(g["id"] in prompt for g in gold)
    assert set(gold[0]) == {"id", "name", "values"} and all(set(c) == {"name", "observed_values"} for c in covered)
    assert all(i in prompt for i in list(pooled)[:40]) and list(pooled)[40] not in prompt


GOLD = [g["id"] for g in judge.load_gold()]


def answer(ids, **per_item):
    rows = [{"item_id": i, "matched_ids": [], "known": False, "cluster": "x", "evidence": "e", **per_item.get(i, {})} for i in ids]
    return json.dumps({"judgments": rows})


def test_judge_parser_is_strict_and_repairs_nothing():
    ids = ["i0001", "i0002"]
    ok = judge.parse_batch(answer(ids, i0001={"matched_ids": ["G01"], "cluster": "  Stale Hold "}), ids, GOLD)
    assert ok["i0001"]["matched"] == {"G01"} and ok["i0001"]["cluster"] == "stale hold"
    bad = ["not json", "```json\n" + answer(ids) + "\n```", json.dumps({"judgments": [], "extra": 1}), json.dumps([1]),
           answer(ids[:1]), answer(list(reversed(ids))), answer(ids, i0001={"matched_ids": ["G99"]}), answer(ids, i0001={"matched_ids": ["G01", "G01"]}),
           answer(ids, i0001={"matched_ids": "G01"}), answer(ids, i0001={"known": "no"}), answer(ids, i0001={"cluster": 3}), answer(ids + ["i0003"])]
    for text in bad:
        with pytest.raises(judge.JudgeError):
            judge.parse_batch(text, ids, GOLD)


def item(arm, run, **kw):
    return {"arm": arm, "run": run, "kind": "scenario", "position": 0, "in_budget": True, "text": None, **kw}


def label(matched=(), known=False, cluster="c"):
    return {"matched": set(matched), "known": known, "cluster": cluster, "evidence": ""}


def test_judge_scores_precision_recall_stability_novelty_and_known_handling():
    E = list(rules.DIMENSIONS)
    non_e = next(g for g in GOLD if g not in E and g not in rules.DEV_ONLY_GOLD)
    pooled = {f"i{n}": item("C", run) for n, run in enumerate([1, 1, 1, 1, 1, 1, 1, 2], 1)}
    labels = {"i1": label([E[0]]), "i2": label([E[1]]), "i3": label([E[2]], known=True), "i4": label([], cluster="foo"),
              "i5": label(["G03"], cluster="dev"), "i6": label([non_e], cluster="out"), "i7": label([], known=True, cluster="old"), "i8": label([E[0]])}
    s = judge.arm_scores(pooled, labels, "C")
    assert s["valid_items"] == 8 and s["items_matching_E"] == 3 and s["precision"] == 3 / 8  # known and dev-only / non-E matches earn nothing
    assert s["recall_pooled"] == 2 / 8 and s["matched_gold_pooled"] == sorted(E[:2])
    assert s["recall_per_run"]["1"] == 2 / 8 and s["recall_per_run"]["2"] == 1 / 8 and s["recall_per_run_mean"] == 3 / 40
    assert s["novel_clusters"] == ["foo"] and s["novel_dimensions"] == 1  # matched-to-gold and known items are not novel
    assert s["items_matching_dev_only"] == 1 and s["known_items"] == 2
    # runs: {E0,E1}, {E0}, {}, {}, {}: only the pair (1, 2) agrees (1/2); three pairs of empty runs count 0.0 and are reported
    assert s["stability_jaccard"] == pytest.approx(0.05) and s["stability_pairs_with_empty_union"] == 3
    for cls, members in (("U_NEW_DIMENSION", {"G01", "G12", "G13", "G16"}), ("U_NEW_VALUE", {"G02", "G04", "G05", "G07"})):
        assert s["classes"][cls]["recall"] == len(set(s["matched_gold_pooled"]) & members) / 4
    out = judge.discovery_scores({**pooled, "b1": item("B", 1)}, {**labels, "b1": label([E[3]])})
    assert set(out["gate_input"]) == {"recall", "precision", "stability_jaccard"} and out["gate_input"]["recall"]["B"] == 1 / 8
    assert judge.arm_scores({"b": item("B", 1)}, {"b": label()}, "C")["precision"] == 0.0  # no valid items: a number, flagged by valid_items == 0


def test_judge_position_sensitivity_and_dev_only_exclusion():
    E = list(rules.DIMENSIONS)
    pooled = {"a": item("B", 1), "b": item("B", 1, in_budget=False, position=20)}
    labels = {"a": label([E[0]]), "b": label([E[1]])}
    rep = judge.full_report(pooled, labels, judge.load_gold(), ["a"])
    assert rep["judge_based"]["arms"]["B"]["recall_pooled"] == 2 / 8 and rep["sensitivity_positions_below_20"]["arms"]["B"]["recall_pooled"] == 1 / 8
    assert rep["human_audit"] == "PENDING_HUMAN_REVIEW" and rep["dev_only_gold"] == ["G03", "G09"]
    assert not set(rules.DEV_ONLY_GOLD) & set(rules.DIMENSIONS)


def test_judge_human_agreement_kappa_and_the_human_corrected_variant():
    E = list(rules.DIMENSIONS)
    pooled = {"a": item("C", 1), "b": item("C", 1), "c": item("C", 2)}
    labels = {"a": label(["G01"]), "b": label(["G02"]), "c": label(["G04"])}
    same = judge.agreement(labels, {"a": ["G01"], "b": ["G02"]}, ["a", "b"], GOLD)
    assert same["raw_agreement"] == 1.0 and same["kappa"] == 1.0 and not same["unreliable"]
    diff = judge.agreement(labels, {"a": ["G01"], "b": ["G03"]}, ["a", "b"], GOLD)
    assert diff["raw_agreement"] == 0.5 and diff["kappa"] == pytest.approx(0.46875, abs=1e-3) and diff["unreliable"] is True
    with pytest.raises(judge.JudgeError):
        judge.agreement(labels, {"a": ["G01"]}, ["a", "b"], GOLD)  # the human must answer exactly the fixed sample
    rep = judge.full_report(pooled, labels, judge.load_gold(), ["a", "b"], {"a": ["G01"], "b": ["G03"]})
    assert rep["reliability"] == "UNRELIABLE" and "human_corrected_on_sample" in rep
    assert rep["judge_based"]["arms"]["C"]["matched_gold_pooled"] == ["G01", "G02", "G04"]  # headline is the judge's, not silently replaced
    assert rep["human_corrected_on_sample"]["arms"]["C"]["matched_gold_pooled"] == ["G01", "G04"]  # G02 -> human says none of E; G03 is dev-only
    assert judge.full_report(pooled, labels, judge.load_gold(), ["a", "b"], {"a": ["G01"], "b": ["G02"]})["reliability"] == "ACCEPTABLE"


def test_judge_prepare_and_score_end_to_end_on_synthetic_files(tmp_path):
    sc, norm = judge_inputs(tmp_path)
    out = tmp_path / "judge"
    summary = judge.prepare(out, sc, norm)
    assert summary == {"items": 65, "batches": 2, "human_sample_items": 13}
    with pytest.raises(FileExistsError):
        judge.prepare(out, sc, norm)  # nothing is overwritten
    key = json.loads((out / "items_key.json").read_text(encoding="utf-8"))
    assert all("text" not in v for v in key["items"].values()) and key["human_sample"] == judge.human_sample(list(key["items"]))
    for name in ("batch_001_prompt.txt", "batch_002_prompt.txt"):
        prompt = (out / name).read_text(encoding="utf-8")
        assert not re.search(r"\b[BC]-r\d|run_id|\"arm\"|0\.8731", prompt.split("<items>")[1]), name  # the judge sees no key
    manifest = json.loads((out / "prepare_manifest.json").read_text(encoding="utf-8"))
    assert manifest["template_sha256"] == judge.sha256_text(judge.PROMPT_PATH.read_text(encoding="utf-8")) and manifest["batches"] == 2
    raw = tmp_path / "raw"
    raw.mkdir()
    first = key["batches"][0]["item_ids"][0]
    for b in key["batches"]:
        per = {first: {"matched_ids": ["G01"], "cluster": "stale"}} if b["batch"] == 1 else {}
        (raw / f"batch_{b['batch']:03d}.json").write_text(answer(b["item_ids"], **per), encoding="utf-8")
    report = judge.score(raw, None, out)
    gate = json.loads((out / "discovery_scores.json").read_text(encoding="utf-8"))
    assert set(gate) == {"recall", "precision", "stability_jaccard"} and set(gate["recall"]) == {"B", "C"}
    arm = key["items"][first]["arm"]
    assert gate["recall"][arm] == 1 / 8 and report["reliability"] == "PENDING_HUMAN_REVIEW" and len(report["raw_answer_sha256"]) == 2
    assert json.loads((out / "discovery_report.json").read_text(encoding="utf-8"))["gate_input"] == gate
    with pytest.raises(FileExistsError):
        judge.score(raw, None, out)
    (raw / "batch_002.json").unlink()
    (out / "discovery_scores.json").unlink()
    (out / "discovery_report.json").unlink()
    with pytest.raises(judge.JudgeError):
        judge.score(raw, None, out)  # a missing answer is an error, never imputed
    # the gate input feeds the unchanged gate code
    det = analysis.detection_block(kills.build_table([], {"A": [], "B": [], "C": []}, info_fixture()), info_fixture(), with_bootstrap=False)
    assert analysis.gates(det, gate)["verdict"] in {"SUCCESS_FOR_BCE", "INCONCLUSIVE", "EVIDENCE_AGAINST_THESIS"}


def test_judge_touches_no_holdout_mapping_detection_result_or_oracle_code():
    source = (ROOT / "detect" / "judge.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {f"{node.module}.{a.name}" for a in node.names}
    assert imported <= {"argparse", "hashlib", "json", "math", "random", "sys", "pathlib.Path", "bce.dsl", "detect.rules", "detect.slots", "detect.preflight"}, imported
    code_only = source.split('"""', 2)[2]
    for forbidden in ("holdout", "DETECTION_DIR", "DRIFT_DIR", "runs.jsonl", "status.jsonl", "eligibility", "ELIGIBLE", "mutant", "oracle", "violations"):
        assert forbidden not in code_only, forbidden
    assert "chat.completions" not in source and "foundry" not in source  # the module makes no model call


def test_a5_constants_and_unchanged_preregistered_numbers():
    assert (rules.CLEAN_REPS, rules.MUTANT_REPS, rules.KILL_MUTANT_MIN, rules.DENOMINATOR, rules.BUDGETS) == (3, 3, 2, 8, (25, 50, 100))
    assert (rules.RECALL_MARGIN, rules.JACCARD_MIN, rules.INVALID_C_FRACTION, rules.BOOTSTRAP_RESAMPLES, rules.BOOTSTRAP_SEED) == (0.2, 0.4, 0.5, 10_000, 20260311)
    assert (rules.JUDGE_SEED, rules.JUDGE_BATCH_MAX, rules.HUMAN_SAMPLE_FRACTION, rules.KAPPA_MIN) == (20260311, 40, 0.20, 0.6)
