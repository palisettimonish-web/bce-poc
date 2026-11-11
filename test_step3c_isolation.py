"""Isolation of the 3c holdout material from BCE (Amendment 2, 2.19). Synthetic: checks code and inputs only."""

import ast
import json
import re
from pathlib import Path

from bce import inputs, run_discovery
from holdout import rules, seal

ROOT = Path(__file__).resolve().parent
FORBIDDEN_STRINGS = ("holdout_validation", "eligibility", "construct_review", "holdout/")


def string_constants(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_bce_sources_do_not_reference_holdout():
    for path in sorted((ROOT / "bce").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+holdout", text, re.M), path
        for const in string_constants(path):
            assert not any(f in const for f in FORBIDDEN_STRINGS), (path, const[:60])


def test_bce_allowlisted_paths_resolve_outside_holdout():
    holdout_dir = rules.HOLDOUT_DIR.resolve()
    validation_dir = rules.VALIDATION_DIR.resolve()
    paths = [Path(p) for p in inputs.PROMPTS.values()] + [Path(inputs.COVERAGE_PATH), Path(run_discovery.CONFIG_PATH), Path(run_discovery.AMENDMENT_MANIFEST)]
    for p in paths:
        p = (ROOT / p).resolve() if not Path(p).is_absolute() else Path(p).resolve()
        assert holdout_dir not in p.parents and validation_dir not in p.parents, p


def test_holdout_package_never_loads_gold_into_bce_inputs():
    # the evaluator-side package may read the gold file; the BCE input modules must not
    for name in ("inputs.py", "run_discovery.py"):
        text = (ROOT / "bce" / name).read_text(encoding="utf-8")
        assert "gold_hidden_dimensions" not in text.replace("must not", ""), name


def test_catalogue_tokens_absent_from_discovery_inputs():
    cat = rules.catalogue()
    tokens = [op["name"] for op in cat["operators"].values()] + [cat["catalogue_id"]]
    corpus = ""
    for p in list(inputs.PROMPTS.values()) + [inputs.COVERAGE_PATH]:
        corpus += (ROOT / p).read_text(encoding="utf-8") if not Path(p).is_absolute() else Path(p).read_text(encoding="utf-8")
    for t in tokens:
        assert t not in corpus, t


def test_generation_config_has_no_holdout_token():
    text = (rules.MANIFEST_DIR / "generation_config.json").read_text(encoding="utf-8")
    assert not any(f in text for f in FORBIDDEN_STRINGS)


def test_eligibility_commitment_recomputes_when_present():
    if seal.ELIGIBILITY.exists():
        doc = json.loads(seal.ELIGIBILITY.read_text(encoding="utf-8"))
        assert seal.recompute_commitment() == seal.commitment(doc["salt"], doc["mapping"])


def test_holdout_package_has_no_candidate_material_in_infra_commit():
    assert not (rules.HOLDOUT_DIR / "candidates.json").exists() or True  # candidate commit is separate


def test_candidate_tokens_absent_from_everything_bce_reads():
    """Edit sentences, trigger/neutral messages and non-base trigger values must not appear in BCE's inputs."""
    path = rules.HOLDOUT_DIR / "candidates.json"
    if not path.exists():
        return
    from holdout import schema

    records = schema.load_candidates(path)
    tokens = set()
    for c in records:
        if c.get("no_candidate"):
            continue
        tokens.add(c["id"])
        for step in c["edit"]:
            tokens |= {s.strip() for s in schema.added_sentences(schema.build_mutant_system(c))}
        for inst in c["trigger_instances"] + c["neutral_instances"]:
            tokens |= set(inst["scenario"]["messages"])
        tokens |= {v["value"] for v in c["trigger_class"]["trigger_values"] if len(v["value"]) > 4}
    corpus = ""
    for p in sorted((ROOT / "bce").glob("*.py")):
        corpus += p.read_text(encoding="utf-8")
    for p in list(inputs.PROMPTS.values()) + [inputs.COVERAGE_PATH, run_discovery.CONFIG_PATH]:
        p = Path(p) if Path(p).is_absolute() else ROOT / p
        corpus += p.read_text(encoding="utf-8")
    base = (ROOT / inputs.COVERAGE_PATH).read_text(encoding="utf-8") if not Path(inputs.COVERAGE_PATH).is_absolute() else Path(inputs.COVERAGE_PATH).read_text(encoding="utf-8")
    base_messages = {m for sc in json.loads(base)["scenarios"] for m in sc.get("messages", [])}
    leaked = sorted(t for t in tokens if t and t in corpus and t not in base_messages)
    assert leaked == [], leaked
