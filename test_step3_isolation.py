"""Structural isolation tests for the BCE side of Step 3. No LLM involved."""

import ast
import json
import re
from pathlib import Path

from bce.inputs import build_prompt

ROOT = Path(__file__).resolve().parent
FORBIDDEN_IMPORTS = {"holdout", "oracle", "evaluate", "truth_spec"}
FORBIDDEN_STRINGS = ("gold_hidden", "truth_spec", "holdout")


def test_bce_modules_import_nothing_from_evaluation_side():
    for path in (ROOT / "bce").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert name.split(".")[0] not in FORBIDDEN_IMPORTS, (path.name, name)


def test_bce_modules_never_reference_evaluation_files():
    for path in (ROOT / "bce").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for needle in FORBIDDEN_STRINGS:
                    assert needle not in node.value, (path.name, needle)


def _leak_tokens():
    gold = json.loads((ROOT / "gold_hidden_dimensions.json").read_text())
    names = [d["name"] for d in gold["dimensions"]]
    codes = ["R1_", "R1B", "R2_", "R3_", "R4_", "R5_", "R5B", "R6_", "R6B", "R7_", "R8_", "R9_", "EXPOSURE_", "T-ID", "T-OWN", "T-STAT", "T-DUP", "T-APPR", "T-FAULT", "T-MONEY", "T-REPORT", "T-STATE", "T-PROC"]
    other = ["o000", "t000", "t001", "no_duplicate_rule", "boundary_defect", "mutant", "holdout", "gold", "truth_spec", "oracle"]
    return names + codes + other


def test_assembled_prompts_contain_no_leak_tokens():
    for arm in ("B", "C"):
        text, hashes = build_prompt(arm, 20)
        assert "assembled_prompt" in hashes
        for token in _leak_tokens():
            assert token not in text, (arm, token)


def test_assembled_prompts_have_no_expected_outcome_field():
    for arm in ("B", "C"):
        text, _ = build_prompt(arm, 20)
        assert '"expect"' not in text and "expect" not in re.findall(r'"(\w+)":', text)


def test_arm_c_adds_coverage_and_arm_b_does_not():
    b, _ = build_prompt("B", 20)
    c, _ = build_prompt("C", 20)
    assert "scenario_count" in c and "scenario_count" not in b
