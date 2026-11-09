"""Allowlisted inputs for arms B and C. Nothing outside this module's sources reaches a discovery prompt.

Allowed: agent SYSTEM, agent TOOLS, the base coverage file (parameters only), the DSL text, and the prompt templates.
"""

import hashlib
import json
from pathlib import Path

from agent import SYSTEM, TOOLS
from bce.dsl import DSL_DESCRIPTION

ROOT = Path(__file__).resolve().parent.parent
COVERAGE_PATH = ROOT / "experiments" / "step3_base_coverage_v1.json"
PROMPTS = {"B": ROOT / "bce" / "generic_prompt_v1.txt", "C": ROOT / "bce" / "discovery_prompt_v2.txt"}


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _coverage():
    return json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))


def coverage_summary(coverage):
    return json.dumps(
        {
            "scenario_count": coverage["scenario_count"],
            "dimensions": coverage["dimensions"],
            "pairwise_interaction_coverage": {
                k: v for k, v in coverage["interaction_coverage"].items() if k != "uncovered_pairs"
            },
        },
        indent=1,
        sort_keys=True,
    )


def existing_scenarios(coverage):
    rows = []
    for e in coverage["scenarios"]:
        f = e["features"]
        rows.append(
            {
                "id": e["id"],
                "requester_id": f["requester_id"],
                "customers": e["fixture"]["customers"],
                "payments": e["fixture"]["payments"],
                "messages": e["messages"],
                "faults": e["faults"],
                "approval": f["approval_answer"],
            }
        )
    return "\n".join(json.dumps(r, sort_keys=True) for r in rows)


def build_prompt(arm, n):
    """Assemble the prompt for arm "B" or "C". Returns (text, input_hashes)."""
    template = PROMPTS[arm].read_text(encoding="utf-8")
    coverage = _coverage()
    values = {
        "SYSTEM_PROMPT": SYSTEM,
        "TOOL_DEFINITIONS": json.dumps(TOOLS, indent=1),
        "COVERAGE": coverage_summary(coverage),
        "EXISTING_SCENARIOS": existing_scenarios(coverage),
        "DSL": DSL_DESCRIPTION,
        "N": str(n),
    }
    text = template
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    assert "{{" not in text, "unfilled placeholder"
    hashes = {
        "template": sha256_file(PROMPTS[arm]),
        "coverage": sha256_file(COVERAGE_PATH),
        "system_prompt": sha256_text(SYSTEM),
        "tools": sha256_text(json.dumps(TOOLS, sort_keys=True)),
        "dsl": sha256_text(DSL_DESCRIPTION),
        "assembled_prompt": sha256_text(text),
    }
    return text, hashes
