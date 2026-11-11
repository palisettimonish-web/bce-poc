"""Command line for the 3c validation stages (run by the user; the only code path that calls the agent).

    python -m holdout.validate s0 [--dry-run]
    python -m holdout.validate run S1|S2|S3|S4|S5|S6
    python -m holdout.validate packet            # writes the blinded S7 packet and key
    python -m holdout.validate review ANSWERS    # records S7 from the answers file
    python -m holdout.validate attrition
"""

import argparse
import json
import sys
from pathlib import Path

from holdout import engine, review, rules, runtime

CANDIDATES = rules.HOLDOUT_DIR / "candidates.json"


def make_executor(candidates_sha):
    config, config_hash = runtime.verify_agent_config()  # refuses to start on any mismatch
    import agent

    client = agent._foundry_client()
    return lambda job: runtime.run_job(job, client, config_hash, candidates_sha)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="holdout.validate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s0 = sub.add_parser("s0")
    s0.add_argument("--dry-run", action="store_true", help="check only; nothing is recorded")
    sub.add_parser("run").add_argument("stage", choices=["S1", "S2", "S3", "S4", "S5", "S6"])
    sub.add_parser("packet")
    sub.add_parser("review").add_argument("answers")
    sub.add_parser("attrition")
    parser.add_argument("--candidates", default=str(CANDIDATES))
    args = parser.parse_args(argv)

    path = Path(args.candidates)
    session = engine.Run(path)
    if args.cmd == "s0":
        out = session.run_s0(record=not args.dry_run)
    elif args.cmd == "run":
        session.executor = make_executor(session.sha)
        out = session.run_stage(args.stage)
    elif args.cmd == "packet":
        out = [str(p) for p in review.write_packet(session)]
    elif args.cmd == "review":
        answers = json.loads(Path(args.answers).read_text(encoding="utf-8"))
        session.apply_construct_review(review.outcomes_from_answers(session, answers))
        out = session.final_status()
    else:
        out = session.attrition_table()
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
