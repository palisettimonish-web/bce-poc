"""3e runners: the 2.15 drift smoke test and the 2.16 detection run.

    PYTHONPATH=. python -m detect.runner drift
    PYTHONPATH=. python -m detect.runner detect [--acknowledge-potentially-invalid]

Every command first runs the pre-3e freeze verification and the frozen agent-config check. Runs are appended to
`experiments/step3/results/` and are resumable; nothing is ever overwritten, regenerated or replaced.
"""

import argparse
import json
import sys

from agent import SYSTEM
from holdout import engine, runtime
from detect import drift, holdout_info, kills, preflight, rules, slots
from detect.session import Incomplete, Session

STATUS_DETECT_DONE = "detection_complete"


def scenario_job(slot, variant, subject, system, rep):
    return {
        "stage": rules.STAGE_DETECT, "variant": variant, "subject": subject, "instance": slot["ref"], "rep": rep,
        "scenario": slot["world"], "system": system,
        "extra": {"arm": slot["arm"], "run": slot["run"], "position": slot["position"], "slot": slot["slot"], "scenario_ref": slot["ref"]},
    }


def process_slot(session, slot, info, curtail=True):
    """All runs of one DSL-valid scenario: 3 clean, then 3 per mutant (the third skipped when curtailable, 2.16 l.375)."""
    if slot["status"] != slots.VALID:
        return  # invalid and missing slots execute nothing (SP l.19)
    clean = [session.ensure(scenario_job(slot, "clean", "clean", SYSTEM, rep)) for rep in range(rules.CLEAN_REPS)]
    if any(c is None for c in clean):
        return  # a clean run has no record yet; mutant runs wait for the next invocation
    for mid, i in info.items():
        first = [session.ensure(scenario_job(slot, "mutant", mid, i["system"], rep)) for rep in range(rules.MUTANT_REPS - 1)]
        if any(r is None for r in first):
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


def run_detection(session, slots_by_arm, info, curtail=True):
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
    done = [r for r in records if not r.get("transport_failure")]
    summary = {"type": STATUS_DETECT_DONE, "curtail": curtail, "runs": len(done), "transport_failures": len(records) - len(done),
               "served_models": sorted({m for r in done for m in r["models"]})}
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


def main(argv=None):
    parser = argparse.ArgumentParser(prog="detect.runner")
    sub = parser.add_subparsers(dest="phase", required=True)
    sub.add_parser("drift")
    det = sub.add_parser("detect")
    det.add_argument("--acknowledge-potentially-invalid", action="store_true")
    args = parser.parse_args(argv)

    problems = preflight.verify()
    if problems:
        print("\n".join(problems))
        print("STOP: pre-3e freeze verification failed")
        return 1
    info = holdout_info.load_admitted()
    if args.phase == "drift":
        session = Session(rules.DRIFT_DIR, _executor())
        verdict = drift.run(session, info, drift.reference_models())
        print(json.dumps({k: verdict[k] for k in ("served_model_identity", "served_models", "potentially_invalid", "drift_suspect")}, indent=1))
        return 0
    drift_log = Session(rules.DRIFT_DIR, None)
    done = drift_log.completed(drift.STATUS_DONE)
    if not done:
        print("STOP: the 2.15 drift smoke test has not been completed (run `detect.runner drift` first)")
        return 1
    if done[-1]["potentially_invalid"] and not args.acknowledge_potentially_invalid:
        print("STOP: the drift test flagged POTENTIALLY_INVALID; report it to the user, then rerun with --acknowledge-potentially-invalid")
        return 1
    slots_by_arm, _ = load_all_slots()
    session = Session(rules.DETECTION_DIR, _executor())
    summary = run_detection(session, slots_by_arm, info)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
