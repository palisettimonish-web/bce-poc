"""The 2.15 model drift smoke test. Bookkeeping is deterministic and a pure function of the logged runs."""

from agent import SYSTEM
from holdout import engine, runtime
from detect import rules
from detect.session import Incomplete, Session

STATUS_DONE = "drift_complete"
SAME, DIFFERENT, UNESTABLISHED = "SAME", "DIFFERENT", "UNESTABLISHED"


def plan(info):
    """Clean agent on the 35 baseline scenarios (1 repetition) and each admitted mutant on trigger instance 1 (3 repetitions)."""
    jobs = []
    for sc in engine.baseline_scenarios():
        for rep in range(rules.DRIFT_CLEAN_REPS):
            jobs.append({"stage": rules.STAGE_DRIFT, "variant": "clean", "subject": "baseline", "instance": sc["id"], "rep": rep,
                         "scenario": sc, "system": SYSTEM})
    for mid, i in info.items():
        inst = i["trigger_instance_1"]
        scenario = engine.world_scenario(inst["scenario"], f"{mid}-{inst['id']}")
        for rep in range(rules.DRIFT_MUTANT_REPS):
            jobs.append({"stage": rules.STAGE_DRIFT, "variant": "mutant", "subject": mid, "instance": inst["id"], "rep": rep,
                         "scenario": scenario, "system": i["system"]})
    return jobs


def reference_models(runs_path=None):
    """The served model string(s) recorded in 3c (the S1-S6 runs)."""
    from holdout import rules as hrules
    path = runs_path or (hrules.VALIDATION_DIR / engine.RUNS_LOG)
    return sorted({m for r in runtime.JsonlLog(path).read() for m in r.get("models", [])})


def evaluate(records, info, reference):
    """Pure. Verdict per 2.15: POTENTIALLY_INVALID flag, DRIFT_SUSPECT per mutant, served-model identity."""
    done = [r for r in records if not r.get("transport_failure")]
    clean = [r for r in done if r["variant"] == "clean"]
    smoke = [{"scenario": r["instance"], "codes": sorted(r["violations"])} for r in clean if r["violations"]]
    served = sorted({m for r in done for m in r["models"]})
    missing_model = [r["key"] for r in done if not r["models"]]
    if missing_model or not reference or not served:
        identity = UNESTABLISHED
    elif served == list(reference):
        identity = SAME
    else:
        identity = DIFFERENT
    mutants = {}
    for mid, i in info.items():
        runs = [r for r in done if r["variant"] == "mutant" and r["subject"] == mid]
        n = sum(1 for r in runs if i["primary_code"] in r["violations"])
        mutants[mid] = {"primary_code": i["primary_code"], "primary_code_runs": n, "runs": len(runs), "drift_suspect": n < rules.DRIFT_MIN_PRIMARY}
    return {
        "type": STATUS_DONE,
        "smoke_clean_runs": len(clean),
        "smoke_violations": smoke,
        "served_models": served,
        "reference_models_3c": list(reference),
        "served_model_identity": identity,
        "served_model_note": ("the served model string was not recorded for every run or no 3c reference exists; identity is not established"
                              if identity == UNESTABLISHED else ""),
        "potentially_invalid": identity == DIFFERENT or bool(smoke),
        "drift_suspect": sorted(m for m, v in mutants.items() if v["drift_suspect"]),
        "mutants": mutants,
    }


def run(session, info, reference):
    """Run (or resume) the smoke test, record the verdict once. Raises Incomplete if some runs have no record."""
    if session.completed(STATUS_DONE):
        raise RuntimeError("the drift smoke test is already complete; it is never re-run (2.15 l.371)")
    jobs = plan(info)
    missing = [j for j in jobs if session.ensure(j) is None]
    if missing:
        raise Incomplete(f"{len(missing)} drift runs have no completed record; run again to resume")
    session.degenerate_gate()
    records = [r for r in session.records() if not r.get("transport_failure")]
    verdict = evaluate(records, info, reference)
    session.record_status(verdict)
    return verdict
