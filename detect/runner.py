"""3e runners: the 2.15 drift smoke test and the 2.16 detection run.

    PYTHONPATH=. python -m detect.runner drift
    PYTHONPATH=. python -m detect.runner detect [--acknowledge-potentially-invalid] [--acknowledge-unestablished-model]
                                                [--acknowledge-served-model-change]

Every command first runs the pre-3e freeze verification and the frozen agent-config check. Runs are appended to
`experiments/step3/results/` and are resumable; nothing is ever overwritten, regenerated or replaced. Amendment 5: the drift
results must be committed and unmodified before detection starts, every logged record must descend from the freeze commit and
carry the frozen configuration hashes, and a served model that differs from the drift run's stops the run unless acknowledged.
"""

import argparse
import json
import sys

from agent import SYSTEM
from holdout import engine, runtime
from detect import drift, holdout_info, kills, preflight, rules, slots
from detect.session import Incomplete, Session, is_completed, is_rejected

STATUS_DETECT_DONE = "detection_complete"
STATUS_DETECT_START = "detection_invocation"


class ServedModelChange(runtime.InfrastructureFailure):
    """A 3e run was served by a model other than the one the drift run recorded (A5.4). Work stops and is reported."""


def served_mismatches(records, baseline):
    """Keys of completed runs whose served-model list differs from `baseline` (the drift run's). Empty if there is no baseline."""
    if not baseline:
        return []
    return sorted(r["key"] for r in records if is_completed(r) and list(r["models"]) != list(baseline))


def served_guard(baseline, acknowledged):
    """A callable for Session(guard=...) that stops the run on the first run served by another model; None without a baseline."""
    if not baseline:
        return None

    def guard(rec):
        if not acknowledged and list(rec["models"]) != list(baseline):
            raise ServedModelChange(f"{rec['key']} was served by {rec['models']!r}, the drift run by {list(baseline)!r}; "
                                    "report it, then resume with --acknowledge-served-model-change")
    return guard


def scenario_job(slot, variant, subject, system, rep):
    return {
        "stage": rules.STAGE_DETECT, "variant": variant, "subject": subject, "instance": slot["ref"], "rep": rep,
        "scenario": slot["world"], "system": system,
        "extra": {"arm": slot["arm"], "run": slot["run"], "position": slot["position"], "slot": slot["slot"], "scenario_ref": slot["ref"]},
    }


def process_slot(session, slot, info, curtail=True):
    """All runs of one DSL-valid scenario: 3 clean, then 3 per mutant (the third skipped when curtailable, 2.16 l.375).

    A PROVIDER_REJECTED run (A5.1) is final: a rejected clean run rejects every pair of the scenario, so no mutant run is made; a
    rejected mutant run rejects that pair and its remaining repetitions are skipped. Nothing is retried or imputed.
    """
    if slot["status"] != slots.VALID:
        return  # invalid and missing slots execute nothing (SP l.19)
    clean, pending = [], False
    for rep in range(rules.CLEAN_REPS):
        rec = session.ensure(scenario_job(slot, "clean", "clean", SYSTEM, rep))
        if is_rejected(rec):
            return
        pending = pending or rec is None
        clean.append(rec)
    if pending:
        return  # a clean run has no record yet; mutant runs wait for the next invocation
    for mid, i in info.items():
        first = []
        for rep in range(rules.MUTANT_REPS - 1):
            first.append(session.ensure(scenario_job(slot, "mutant", mid, i["system"], rep)))
            if is_rejected(first[-1]):
                break
        if any(r is None or is_rejected(r) for r in first) or len(first) < rules.MUTANT_REPS - 1:
            continue
        if curtail and kills.curtailable(first, clean):
            continue
        session.ensure(scenario_job(slot, "mutant", mid, i["system"], rules.MUTANT_REPS - 1))


def order(slots_by_arm):
    """B and C interleaved slot by slot (so provider drift is not aligned with one arm), then Arm A."""
    out = []
    for k in range(rules.RUNS_PER_ARM * rules.SLOTS_PER_RUN):
        out += [slots_by_arm[a][k] for a in rules.GENERATED_ARMS]
    return out + slots_by_arm["A"]


def load_all_slots(scenario_dir=None):
    out, stats = {}, {}
    for arm in rules.GENERATED_ARMS:
        out[arm], stats[arm] = slots.load_arm_slots(arm, scenario_dir)
    out["A"] = slots.arm_a_slots(engine.baseline_scenarios())
    return out, stats


def run_detection(session, slots_by_arm, info, curtail=True, baseline=None, acknowledged=None):
    """Run or resume the detection experiment and record completion once. Raises Incomplete if runs are missing."""
    if session.completed(STATUS_DETECT_DONE):
        raise RuntimeError("detection is already complete; it is never re-run")
    for slot in order(slots_by_arm):
        process_slot(session, slot, info, curtail)
    records = [r for r in session.records()]
    try:
        kills.build_table(records, slots_by_arm, info)
    except ValueError as exc:
        raise Incomplete(str(exc))
    session.degenerate_gate(records)
    done = [r for r in records if is_completed(r)]
    final_rejected = {r["key"] for r in records if is_rejected(r)}
    summary = {"type": STATUS_DETECT_DONE, "curtail": curtail, "runs": len(done), "provider_rejected_runs": len(final_rejected),
               "transport_failures": len(records) - len(done) - len([r for r in records if is_rejected(r)]),
               "served_models": sorted({m for r in done for m in r["models"]}), "served_model_baseline": list(baseline or []),
               "served_model_mismatches": served_mismatches(records, baseline), "acknowledged": dict(acknowledged or {})}
    session.record_status(summary)
    return summary


def _executor():
    import agent
    config, config_hash = runtime.verify_agent_config()
    client = agent._foundry_client()
    sha = runtime.sha256_file(holdout_info.CANDIDATES)

    def execute(job):
        return runtime.run_job(job, client, config_hash, sha)

    return execute


def _stop(message):
    print(f"STOP: {message}")
    return 1


def _record_problems(session):
    """A5.5: the log's records descend from the freeze commit and carry the frozen configuration hashes."""
    return preflight.record_problems(session.records(), preflight.freeze_sha(), preflight.frozen_config_hash(),
                                     runtime.sha256_file(holdout_info.CANDIDATES))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="detect.runner")
    sub = parser.add_subparsers(dest="phase", required=True)
    sub.add_parser("drift")
    det = sub.add_parser("detect")
    det.add_argument("--acknowledge-potentially-invalid", action="store_true")
    det.add_argument("--acknowledge-unestablished-model", action="store_true")
    det.add_argument("--acknowledge-served-model-change", action="store_true")
    args = parser.parse_args(argv)

    problems = preflight.verify()
    if problems:
        print("\n".join(problems))
        return _stop("pre-3e freeze verification failed")
    info = holdout_info.load_admitted()
    try:
        if args.phase == "drift":
            problems = preflight.history_problems(rules.DRIFT_DIR, "drift")
            if problems:
                return _stop("; ".join(problems))
            session = Session(rules.DRIFT_DIR, _executor())
            problems = _record_problems(session)
            if problems:
                return _stop("; ".join(problems[:5]))
            verdict = drift.run(session, info, drift.reference_models())
            print(json.dumps({k: verdict[k] for k in ("served_model_identity", "served_models", "potentially_invalid", "drift_suspect")}, indent=1))
            return 0
        drift_log = Session(rules.DRIFT_DIR, None)
        done = drift_log.completed(drift.STATUS_DONE)
        if not done:
            return _stop("the 2.15 drift smoke test has not been completed (run `detect.runner drift` first)")
        problems = preflight.sealed_problems(rules.DRIFT_DIR, "drift") + _record_problems(drift_log)
        if problems:
            return _stop("; ".join(problems[:5]) + " (commit the drift results unmodified before detection)")
        verdict = done[-1]
        if verdict["potentially_invalid"] and not args.acknowledge_potentially_invalid:
            return _stop("the drift test flagged POTENTIALLY_INVALID; report it to the user, then rerun with --acknowledge-potentially-invalid")
        unestablished = verdict["served_model_identity"] == drift.UNESTABLISHED
        if unestablished and not args.acknowledge_unestablished_model:
            return _stop("the served model could not be established in the drift run; report it, then rerun with --acknowledge-unestablished-model")
        baseline = [] if unestablished else list(verdict["served_models"])
        problems = preflight.history_problems(rules.DETECTION_DIR, "detection")
        session = Session(rules.DETECTION_DIR, None)
        problems += _record_problems(session)
        if problems:
            return _stop("; ".join(problems[:5]))
        changed = served_mismatches(session.records(), baseline)
        if changed and not args.acknowledge_served_model_change:
            return _stop(f"{len(changed)} logged runs were served by a model other than the drift run's {baseline}; "
                         "report it, then rerun with --acknowledge-served-model-change")
        acknowledged = {"potentially_invalid": args.acknowledge_potentially_invalid, "unestablished_model": args.acknowledge_unestablished_model,
                        "served_model_change": args.acknowledge_served_model_change}
        session = Session(rules.DETECTION_DIR, _executor(), served_guard(baseline, args.acknowledge_served_model_change))
        session.record_status({"type": STATUS_DETECT_START, "acknowledged": acknowledged, "served_model_baseline": baseline,
                               "served_model_guard": "ACTIVE" if baseline else "DISABLED_MODEL_UNESTABLISHED"})
        slots_by_arm, _ = load_all_slots()
        summary = run_detection(session, slots_by_arm, info, baseline=baseline, acknowledged=acknowledged)
        print(json.dumps(summary, indent=1))
        return 0
    except (Incomplete, runtime.InfrastructureFailure, RuntimeError) as exc:
        return _stop(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
