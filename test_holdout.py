"""Tests for the 3c validation infrastructure. Synthetic fixtures only: no real candidate content,
no agent or LLM call. The executor is a fake that returns scripted violations."""

import json

import pytest

from agent import SYSTEM
from holdout import engine, review, rules, runtime, schema, seal

DIMS = ["G01", "G02"]
FIRST_LINE = SYSTEM.splitlines()[0]


def scenario(tag):
    return {
        "candidate_id": None,
        "customers": [{"id": "C1", "valid": True}],
        "payments": [{"id": "P1", "customer_id": "C1", "amount": 1000, "status": "captured"}],
        "requester_id": "C1",
        "messages": [f"synthetic {tag}"],
        "faults": {},
        "approval": "approve",
        "expected_distinction": "synthetic",
    }


def candidate(cid, dim, code="R2_PAYMENT_NOT_VERIFIED"):
    tag = cid.lower().replace("m", "q")
    return {
        "id": cid, "dimension": dim, "operator": "P1",
        "edit": [{"old": FIRST_LINE, "new": FIRST_LINE + " Synthetic addition."}],
        "trigger_class": {"description": "synthetic", "anchor_values": [], "trigger_values": [], "trigger_fields": []},
        "trigger_instances": [{"id": f"T{i}", "trigger_value": "x", "scenario": scenario(f"{tag}t{i}"),
                               "violating_trace": [], "compliant_trace": []} for i in (1, 2, 3)],
        "neutral_instances": [{"id": f"N{i}", "pairs_with": f"T{i}", "scenario": scenario(f"{tag}n{i}")} for i in (1, 2)],
        "primary_code": code, "intended_codes": [code], "plausibility_note": "synthetic", "distinctness_basis": "synthetic",
    }


class Fake:
    """Scripted executor. `rules` maps (stage, variant, subject) to the violation list returned."""

    def __init__(self, table=None, default=None):
        self.table, self.default, self.calls = table or {}, default or [], 0

    def __call__(self, job):
        self.calls += 1
        viol = self.table.get((job["stage"], job["variant"], job["subject"]), self.default)
        return {"key": runtime.job_key(job), "stage": job["stage"], "variant": job["variant"], "subject": job["subject"],
                "instance": job["instance"], "rep": job["rep"], "transport_failure": False, "replies": ["ok"],
                "calls": [], "violations": list(viol), "models": ["gpt-4.1-mini-x"], "tokens": {"input": 1, "output": 1}}


@pytest.fixture
def session(tmp_path):
    def make(cands, executor=None):
        path = tmp_path / "candidates.json"
        path.write_text(json.dumps({"candidates": cands}), encoding="utf-8")
        s = engine.Run(path, log_dir=tmp_path / "logs", executor=executor, require_committed=False)
        return s
    return make


def pass_s0(s):
    s._record_stage("S0", {r["id"]: {"status": rules.PASS, "details": {}, "rates": {}} for r in s.records}, {})


def test_stage_order_is_enforced(session):
    s = session([candidate("M01", "G01")], Fake())
    with pytest.raises(engine.StageError):
        s.run_stage("S1")  # S0 not complete
    pass_s0(s)
    with pytest.raises(engine.StageError):
        s.run_stage("S2")  # S1 not complete
    s.run_stage("S1")
    with pytest.raises(engine.StageError):
        s.run_stage("S1")  # never twice


def test_failed_candidate_is_terminal_and_never_run_again(session):
    ex = Fake({("S1", "clean", "M01"): ["R2_PAYMENT_NOT_VERIFIED"]})
    s = session([candidate("M01", "G01"), candidate("M02", "G02")], ex)
    pass_s0(s)
    out = s.run_stage("S1")
    assert out["M01"]["status"] == "CLEAN_NOT_CLEAN" and out["M02"]["status"] == rules.PASS
    assert s.active("S2") == ["M02"]
    assert all(j["subject"] == "M02" for j in s.plan("S2"))
    assert s.final_status()["M01"] == ("CLEAN_NOT_CLEAN", "S1")


def test_no_replacement_status_or_path():
    assert not any("REPLAC" in x for x in rules.TERMINAL_STATUSES)
    assert not any("replac" in n.lower() for n in dir(engine.Run))


def test_s2_admission_and_unintended_effect(session):
    code = "R2_PAYMENT_NOT_VERIFIED"
    for viol, expected in [([code] * 1, "STOCHASTIC_ADMISSION_FAILURE"), ([code], None)]:
        pass
    ex = Fake({("S2", "mutant", "M01"): [code]})
    s = session([candidate("M01", "G01")], ex)
    pass_s0(s); s.run_stage("S1")
    assert s.run_stage("S2")["M01"]["status"] == rules.PASS
    ex2 = Fake({("S2", "mutant", "M01"): []})
    s2 = session([candidate("M01", "G01")], ex2)
    s2.runs.path.unlink(missing_ok=True)
    s2.status.path.unlink(missing_ok=True)
    pass_s0(s2); s2.run_stage("S1")
    assert s2.run_stage("S2")["M01"]["status"] == "STOCHASTIC_ADMISSION_FAILURE"


def test_s2_unintended_code(session):
    ex = Fake({("S2", "mutant", "M01"): ["R2_PAYMENT_NOT_VERIFIED", "R3_NON_CAPTURED_REFUNDED"]})
    s = session([candidate("M01", "G01")], ex)
    pass_s0(s); s.run_stage("S1")
    assert s.run_stage("S2")["M01"]["status"] == "UNINTENDED_EFFECT"


def test_s3_neutral_control(session):
    ex = Fake({("S3", "mutant", "M01"): ["R2_PAYMENT_NOT_VERIFIED"]})
    s = session([candidate("M01", "G01")], ex)
    pass_s0(s)
    for st in ("S1", "S2"):
        s.status.append({"type": "stage_complete", "stage": st, "candidates_sha": s.sha,
                         "outcomes": {"M01": {"status": rules.PASS, "details": {}, "rates": {}}}, "extra": {"representatives": {"G01": "M01"}}})
    assert s.run_stage("S3")["M01"]["status"] == "NEUTRAL_CONTROL_FAILURE"


def test_s4_attributable_kill_requires_clean_zero(session):
    s = session([candidate("M01", "G01")])
    code = "R2_PAYMENT_NOT_VERIFIED"
    m = [{"violations": [code]}, {"violations": [code]}, {"violations": []}]
    clean_ok = [{"violations": []}] * 3
    clean_bad = [{"violations": [code]}] + [{"violations": []}] * 2
    assert s.kill_codes("M01", m, clean_ok) == [code]
    assert s.kill_codes("M01", m, clean_bad) == []
    assert s.kill_codes("M01", m[:1] + [{"violations": []}] * 2, clean_ok) == []


def test_s4_other_code_is_not_an_attributable_kill(session):
    s = session([candidate("M01", "G01")])
    m = [{"violations": ["R3_NON_CAPTURED_REFUNDED"]}] * 3
    assert s.kill_codes("M01", m, [{"violations": []}] * 3) == []


def test_representative_is_lowest_passing_id(session):
    ex = Fake({("S1", "clean", "M01"): ["R1_INVALID_CUSTOMER_REFUNDED"]})
    s = session([candidate("M01", "G01"), candidate("M02", "G01"), candidate("M03", "G02")], ex)
    pass_s0(s)
    s.run_stage("S1")
    assert s.representatives() == {"G01": "M02", "G02": "M03"}


def test_s5_flags(session):
    code = "R2_PAYMENT_NOT_VERIFIED"
    cands = [candidate("M01", "G01"), candidate("M02", "G02"), candidate("M03", "G04")]
    s = session(cands)
    pass_s0(s)
    for st in ("S1", "S2", "S3", "S4"):
        s.status.append({"type": "stage_complete", "stage": st, "candidates_sha": s.sha,
                         "outcomes": {c["id"]: {"status": rules.PASS, "details": {}, "rates": {}} for c in cands},
                         "extra": {"representatives": {"G01": "M01", "G02": "M02", "G04": "M03"}}})

    def runs(counts):
        recs = []
        for dim, n in counts.items():
            for r in range(3):
                recs.append({"subject": "M01", "instance": f"REP-{dim}", "variant": "mutant", "violations": [code] if r < n else []})
        return recs

    out, _ = s.evaluate("s5", runs({"G02": 1, "G04": 0}))
    assert out["M01"]["status"] == rules.PASS and out["M01"]["flags"] == ["OVERLAP"]
    out, _ = s.evaluate("s5", runs({"G02": 1, "G04": 3}))
    assert out["M01"]["status"] == "CROSS_TRIGGER_NON_SPECIFIC"


def test_s6_equivalence_drops_higher_id(session):
    s = session([candidate("M01", "G01"), candidate("M02", "G01")])
    pass_s0(s)
    for st in ("S1", "S2", "S3", "S4", "S5"):
        s.status.append({"type": "stage_complete", "stage": st, "candidates_sha": s.sha,
                         "outcomes": {c: {"status": rules.PASS, "details": {}, "rates": {}} for c in ("M01", "M02")}, "extra": {}})
    code = "R2_PAYMENT_NOT_VERIFIED"
    recs = [{"subject": "M01", "instance": "SIB-M02-T1", "variant": "mutant", "violations": [code]} for _ in range(8)]
    recs += [{"subject": "M02", "instance": "SIB-M01-T1", "variant": "mutant", "violations": [code]} for _ in range(8)]
    out, _ = s.evaluate("s6", recs)
    assert out["M01"]["status"] == rules.PASS and out["M02"]["status"] == "VARIANT_EQUIVALENT"


def test_candidates_file_change_is_detected(session, tmp_path):
    s = session([candidate("M01", "G01")], Fake())
    pass_s0(s)
    s.candidates_path.write_text(json.dumps({"candidates": []}), encoding="utf-8")
    s2 = engine.Run(s.candidates_path, log_dir=tmp_path / "logs", require_committed=False)
    with pytest.raises(engine.StageError):
        s2.check_consistency()


def test_logs_are_append_only(tmp_path):
    log = runtime.JsonlLog(tmp_path / "x.jsonl")
    log.append({"a": 1}); log.append({"a": 2})
    assert [r["a"] for r in log.read()] == [1, 2]
    assert not any(hasattr(log, n) for n in ("delete", "update", "write", "clear", "remove"))


def test_resume_does_not_rerun_completed_jobs(session):
    ex = Fake()
    s = session([candidate("M01", "G01")], ex)
    jobs = s.plan("S1") if False else None
    pass_s0(s)
    s.execute(s.plan("S1"))
    n = ex.calls
    s.execute(s.plan("S1"))
    assert ex.calls == n == 30


def test_incomplete_transport_failure_resumes(session):
    class Flaky(Fake):
        def __call__(self, job):
            rec = super().__call__(job)
            if self.calls == 1:
                rec["transport_failure"] = True
            return rec

    s = session([candidate("M01", "G01")], Flaky())
    pass_s0(s)
    with pytest.raises(engine.Incomplete):
        s.run_stage("S1")
    s.run_stage("S1")  # resumes: only the missing run is re-executed
    assert s.executor.calls == 31


def test_degenerate_gate_and_served_model_check(session):
    s = session([candidate("M01", "G01")], Fake())
    recs = [{"replies": ["[max turns exceeded]"]}] * 2 + [{"replies": ["ok"]}] * 8
    with pytest.raises(runtime.InfrastructureFailure):
        s.degenerate_gate(recs)
    s.degenerate_gate([{"replies": ["ok"]}] * 20)
    s.runs.append({"key": "a", "models": ["m1"]}); s.runs.append({"key": "b", "models": ["m2"]})
    with pytest.raises(runtime.InfrastructureFailure):
        s.check_model_consistency()


def test_job_counts_match_the_protocol(session):
    s = session([candidate("M01", "G01"), candidate("M02", "G02")])
    pass_s0(s)
    assert len(s.plan("S1")) == 2 * 3 * rules.S1_REPS
    s.status.append({"type": "stage_complete", "stage": "S1", "candidates_sha": s.sha,
                     "outcomes": {c: {"status": rules.PASS, "details": {}, "rates": {}} for c in ("M01", "M02")}, "extra": {"representatives": {"G01": "M01", "G02": "M02"}}})
    assert len(s.plan("S2")) == 2 * 3 * rules.S2_REPS


def test_attrition_table_marks_untestable(session):
    s = session([candidate("M01", "G01")])
    pass_s0(s)
    s.status.append({"type": "stage_complete", "stage": "S1", "candidates_sha": s.sha,
                     "outcomes": {"M01": {"status": "CLEAN_NOT_CLEAN", "details": {}, "rates": {}}}, "extra": {}})
    t = s.attrition_table()
    assert t["G01"]["CLEAN_NOT_CLEAN"] == 1 and t["G01"]["NOT_DETECTION_TESTABLE"] is True
    assert set(t) == set(rules.ELIGIBLE)


def test_mutant_system_edit_applies_exactly_once():
    c = candidate("M01", "G01")
    assert schema.build_mutant_system(c).count("Synthetic addition.") == 1
    c["edit"][0]["old"] = "never in system"
    with pytest.raises(ValueError):
        schema.build_mutant_system(c)


def test_agent_config_verifies_and_detects_drift():
    runtime.verify_agent_config()
    with pytest.raises(runtime.ConfigError):
        runtime.verify_agent_config(system=SYSTEM + " ")
    with pytest.raises(runtime.ConfigError):
        runtime.verify_agent_config(model="other")
    with pytest.raises(runtime.ConfigError):
        runtime.verify_agent_config(tools=[])


def test_review_packet_is_blinded_and_key_is_separate(session, tmp_path):
    cands = [candidate("M01", "G01"), candidate("M02", "G02")]
    s = session(cands)
    pass_s0(s)
    for st in ("S1", "S2", "S3", "S4", "S5", "S6"):
        s.status.append({"type": "stage_complete", "stage": st, "candidates_sha": s.sha,
                         "outcomes": {c["id"]: {"status": rules.PASS, "details": {}, "rates": {"r": 1}} for c in cands}, "extra": {}})
    packet, key = review.build_packet(s)
    text = json.dumps(packet)
    assert review.packet_leaks(text) == []
    assert set(key) == {"R01", "R02"} and set(key.values()) == {"M01", "M02"}
    assert "M01" not in text and "G01" not in text
    assert review.build_packet(s)[1] == key  # seeded, reproducible
    pp, kp = review.write_packet(s, tmp_path / "rv")
    with pytest.raises(review.ReviewError):
        review.write_packet(s, tmp_path / "rv")  # never overwritten
    yes = {str(i): {"answer": "yes", "reason": "ok"} for i in range(1, 7)}
    answers = {"R01": yes, "R02": {**yes, "3": {"answer": "no", "reason": "activates"}}}
    out = review.outcomes_from_answers(s, answers, kp, pp)
    failed = key["R02"]
    assert out[failed]["status"] == "CONSTRUCT_REVIEW_FAILURE" and out[key["R01"]]["status"] == rules.PASS
    with pytest.raises(review.ReviewError):
        review.outcomes_from_answers(s, {"R01": yes}, kp, pp)


def test_commitment_roundtrip(tmp_path):
    mapping = {"M01": {"slot": 1, "dimension": "G01", "status": "ADMITTED", "last_stage": "S7"}}
    salt = "00" * 32
    c = seal.commitment(salt, mapping)
    assert c == seal.commitment(salt, json.loads(json.dumps(mapping)))
    assert c != seal.commitment("11" * 32, mapping)
    mapping["M01"]["status"] = "VARIANT_EQUIVALENT"
    assert c != seal.commitment(salt, mapping)


def test_s0_set_rules():
    ok = [candidate("M01", "G01"), candidate("M02", "G01")]
    assert schema.candidate_set_errors(ok) == []
    assert schema.candidate_set_errors([candidate("M01", "G01"), candidate("M03", "G01")])  # gap in ids
    assert schema.candidate_set_errors([candidate(f"M0{i}", "G01") for i in range(1, 5)])  # > 3 per dimension


def test_s0_structure_and_catalogue_reject_bad_candidates():
    bad = candidate("M01", "G01", code="R4_DUPLICATE_REFUND")
    out = schema.run_s0([bad])
    assert out["M01"][0] != rules.PASS  # forbidden code can never pass S0
    malformed = candidate("M01", "G01")
    del malformed["neutral_instances"]
    assert schema.run_s0([malformed])["M01"][0] != rules.PASS


class _FakeResponse:
    def __init__(self, model="gpt-4.1-mini-x"):
        self.id, self.model, self.output, self.output_text = "r1", model, [], "Done."
        self.usage = type("U", (), {"input_tokens": 7, "output_tokens": 3})()


class _FakeResponses:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, 0

    def create(self, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("transport down")
        return _FakeResponse()


class _FakeClient:
    def __init__(self, fail=False):
        self.responses = _FakeResponses(fail)


def _job():
    sc = engine.world_scenario(scenario("meta"), "M01-T1")
    return {"stage": "S1", "variant": "clean", "subject": "M01", "instance": "T1", "rep": 0, "scenario": sc, "system": SYSTEM}


def test_run_job_records_required_metadata():
    rec = runtime.run_job(_job(), _FakeClient(), "cfg-hash", "cand-sha")
    assert rec["transport_failure"] is False
    assert "approval_granted" in rec["scenario_params"]
    assert rec["ledger"] == []
    assert rec["served_models_per_response"] == ["gpt-4.1-mini-x"]
    assert rec["models"] == ["gpt-4.1-mini-x"]
    assert rec["tokens"] == {"input": 7, "output": 3}
    assert rec["agent_config_hash"] == "cfg-hash" and rec["candidates_sha"] == "cand-sha"
    assert rec["git_sha"] and rec["timestamp"]


def test_run_job_transport_failure_record():
    client = _FakeClient(fail=True)
    rec = runtime.run_job(_job(), client, "cfg-hash", "cand-sha")
    assert rec["transport_failure"] is True
    assert len(rec["attempt_errors"]) == rules.TRANSPORT_ATTEMPTS == client.responses.calls == 3
    assert rec["ledger"] == [] and rec["served_models_per_response"] == [] and rec["models"] == []
