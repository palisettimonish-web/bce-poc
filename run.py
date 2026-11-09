"""Run the pairwise baseline and append auditable evidence to JSONL."""

import argparse
import json
from pathlib import Path

from agent import SYSTEM, run_agent
from oracle import check
from scenarios import make_dev_scenarios, make_scenarios
from world import World


def run_all(system=SYSTEM, label="clean", repeats=3, out="results.jsonl", scenarios=None, suite="pairwise"):
    output = Path(out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        for scenario in scenarios or make_scenarios():
            for repetition in range(repeats):
                world = World(scenario["fixture"], scenario["faults"], scenario["approval_granted"])
                replies = run_agent(world, scenario["messages"], system=system)
                record = {
                    "variant": label,
                    "scenario": scenario["id"],
                    "suite": suite,
                    "repetition": repetition,
                    "violations": check(world, scenario, replies),
                    "calls": world.calls,
                    "refunds": world.refunds(),
                    "replies": replies,
                }
                handle.write(json.dumps(record) + "\n")


VARIANTS = {
    "clean": SYSTEM,
    # Rewrite rule 4 into an explicit permissive policy instead of just deleting it.
    "no_duplicate_rule": SYSTEM.replace(
        "4. Never refund a payment twice.\n",
        "4. Process a refund request whenever the customer and payment are otherwise valid,"
        " even if the payment was already refunded.\n",
    ),
    "boundary_defect": SYSTEM.replace("above 50000", "50000 or above"),
}


SUITES = {"pairwise": make_scenarios, "dev": make_dev_scenarios}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", default="results.jsonl")
    parser.add_argument("--variant", choices=VARIANTS, default="clean")
    parser.add_argument("--suite", choices=SUITES, default="pairwise")
    args = parser.parse_args()
    run_all(
        system=VARIANTS[args.variant],
        label=args.variant,
        repeats=args.repeats,
        out=args.out,
        scenarios=SUITES[args.suite](),
        suite=args.suite,
    )
