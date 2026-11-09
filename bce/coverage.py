"""Mechanically derive the base coverage representation from the existing scenario suites.

Reads only scenario parameters. It never reads `expect`, oracle codes, the gold list or the truth spec.
Usage: python -I -m bce.coverage experiments/step3_base_coverage_v1.json
"""

import itertools
import json
import sys

from scenarios import make_expanded_clean_scenarios, make_scenarios

DIMENSIONS = (
    "requester_id", "requester_valid", "customer_count", "payment_count", "target_payment_status",
    "target_payment_amount", "payment_currencies", "approval_answer", "tool_faults", "request_pattern",
)
LATTICE = ("requester_valid", "target_payment_status", "target_payment_amount", "approval_answer", "tool_faults", "request_pattern")


def features(s):
    faults = sorted(
        f"{tool}:{(f['mode'] if isinstance(f, dict) else f)}:{(f.get('phase', 'before') if isinstance(f, dict) else 'before')}"
        for tool, f in s["faults"].items()
    )
    return {
        "requester_id": s["requester_id"],
        "requester_valid": s["customer_valid"],
        "customer_count": len(s["fixture"]["customers"]),
        "payment_count": len(s["fixture"]["payments"]),
        "target_payment_status": s["status"],
        "target_payment_amount": s["amount"],
        "payment_currencies": sorted({p.get("currency", "INR") for p in s["fixture"]["payments"]}),
        "approval_answer": "approve" if s["approval_granted"] else "deny",
        "tool_faults": faults or ["none"],
        "request_pattern": "repeat" if len(s["messages"]) > 1 else "single",
    }


def _atoms(feat):
    """(dimension, value) atoms for the lattice dimensions; list-valued ones become one atom per item."""
    out = []
    for dim in LATTICE:
        value = feat[dim]
        for v in (value if isinstance(value, list) else [value]):
            out.append((dim, json.dumps(v)))
    return out


def build():
    entries = []
    suites = (("pairwise", make_scenarios()), ("expanded", make_expanded_clean_scenarios()))
    for suite, scenarios in suites:
        for s in scenarios:
            entries.append({
                "id": s["id"], "suite": suite, "features": features(s), "messages": s["messages"],
                "fixture": s["fixture"], "faults": s["faults"],
            })
    observed = {d: sorted({json.dumps(v) for e in entries for v in (e["features"][d] if isinstance(e["features"][d], list) else [e["features"][d]])}) for d in DIMENSIONS}
    covered_pairs = set()
    for e in entries:
        atoms = _atoms(e["features"])
        covered_pairs.update(itertools.combinations(sorted(atoms), 2))
    lattice_atoms = sorted({a for e in entries for a in _atoms(e["features"])})
    possible = {p for p in itertools.combinations(lattice_atoms, 2) if p[0][0] != p[1][0]}
    covered = {p for p in covered_pairs if p[0][0] != p[1][0]}
    return {
        "version": "step3_base_coverage_v1",
        "derivation": "mechanical from make_scenarios() and make_expanded_clean_scenarios(); parameters only",
        "scenario_count": len(entries),
        "dimensions": [{"name": d, "observed_values": [json.loads(v) for v in observed[d]]} for d in DIMENSIONS],
        "interaction_coverage": {
            "scope": "pairs of observed values across the six lattice dimensions",
            "dimensions": list(LATTICE),
            "observed_pairs_possible": len(possible),
            "observed_pairs_covered": len(covered),
            "uncovered_pairs": sorted([[list(a), list(b)] for a, b in possible - covered]),
        },
        "scenarios": entries,
    }


if __name__ == "__main__":
    with open(sys.argv[1], "x", encoding="utf-8") as handle:
        json.dump(build(), handle, indent=1, sort_keys=True)
        handle.write("\n")
