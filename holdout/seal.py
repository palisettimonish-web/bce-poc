"""Holdout sealing and the freeze manifest (Amendment 2, 2.19-2.20).

Evaluator side only. `build_eligibility` and `build_freeze` are called once, at the end of 3c;
`verify_freeze` is the hash-verification check that must pass before any 3d call.
"""

import hashlib
import json
import secrets
import sys
from pathlib import Path

from holdout import rules, runtime

ELIGIBILITY = rules.HOLDOUT_DIR / "eligibility.json"
FREEZE_MANIFEST = rules.MANIFEST_DIR / "holdout_freeze.json"


class SealError(RuntimeError):
    pass


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def commitment(salt_hex, mapping):
    """SHA-256(salt bytes || canonical JSON of the mapping)."""
    return hashlib.sha256(bytes.fromhex(salt_hex) + canonical(mapping)).hexdigest()


def build_mapping(run):
    """{candidate_id: {slot, dimension, status, last_stage}} from the finished validation (2.19)."""
    final = run.final_status()
    slots, mapping = {}, {}
    for r in run.records:
        slots[r["dimension"]] = slots.get(r["dimension"], 0) + 1
        status, stage = final[r["id"]]
        mapping[r["id"]] = {"slot": slots[r["dimension"]], "dimension": r["dimension"], "status": status, "last_stage": stage}
    return mapping


def build_eligibility(run, path=ELIGIBILITY, salt_hex=None):
    if Path(path).exists():
        raise SealError("eligibility.json already exists; it is never overwritten")
    if "S7" not in run.completed():
        raise SealError("the mapping is sealed only after S7 is complete")
    salt_hex = salt_hex or secrets.token_hex(32)
    mapping = build_mapping(run)
    doc = {"salt": salt_hex, "mapping": mapping}
    Path(path).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return commitment(salt_hex, mapping)


def recompute_commitment(path=ELIGIBILITY):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return commitment(doc["salt"], doc["mapping"])


def tracked_files(root=rules.ROOT):
    files = [p for p in sorted(rules.HOLDOUT_DIR.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    if rules.VALIDATION_DIR.exists():
        files += [p for p in sorted(rules.VALIDATION_DIR.rglob("*")) if p.is_file()]
    return [p for p in files if p != ELIGIBILITY or True]


def build_freeze(path=FREEZE_MANIFEST, eligibility=ELIGIBILITY):
    if Path(path).exists():
        raise SealError("holdout_freeze.json already exists; it is never overwritten")
    files = {str(p.relative_to(rules.ROOT)): runtime.sha256_file(p) for p in tracked_files()}
    doc = {
        "freeze": "step3c holdout freeze",
        "defined_by": "Amendment 2, section 2.20",
        "commitment": recompute_commitment(eligibility),
        "git_sha": runtime.git_sha(),
        "timestamp": runtime.utc_now(),
        "files": files,
    }
    Path(path).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def verify_freeze(path=FREEZE_MANIFEST):
    """Return a list of problems (empty when every hash and the commitment still match)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = []
    for rel, digest in doc["files"].items():
        p = rules.ROOT / rel
        if not p.exists():
            problems.append(f"missing: {rel}")
        elif runtime.sha256_file(p) != digest:
            problems.append(f"hash differs: {rel}")
    if recompute_commitment() != doc["commitment"]:
        problems.append("mapping commitment does not recompute")
    return problems


if __name__ == "__main__":
    issues = verify_freeze()
    print("OK: holdout freeze verified" if not issues else "\n".join(issues))
    sys.exit(1 if issues else 0)
