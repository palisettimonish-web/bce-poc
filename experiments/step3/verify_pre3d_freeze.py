"""Pre-3d freeze check (Amendment 3, A3.6). Verification only; it writes nothing and calls no model.

Run from the repository root before every 3d call:
    PYTHONPATH=. python experiments/step3/verify_pre3d_freeze.py
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
MANIFEST = ROOT / "experiments/step3/manifests/pre3d_freeze.json"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)


def is_ancestor(commit, descendant="HEAD"):
    return git("merge-base", "--is-ancestor", commit, descendant).returncode == 0


def verify(manifest_path=MANIFEST):
    doc = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    problems = []
    freeze = doc["git_sha"]
    if git("cat-file", "-e", f"{freeze}^{{commit}}").returncode != 0:
        problems.append(f"freeze commit not found: {freeze}")
    elif not is_ancestor(freeze):
        problems.append(f"freeze commit is not an ancestor of HEAD: {freeze}")
    for label in ("holdout_freeze_commit", "amendment2_commit"):
        if not is_ancestor(doc[label]):
            problems.append(f"{label} is not an ancestor of HEAD: {doc[label]}")
    for rel, digest in doc["files"].items():
        path = ROOT / rel
        if not path.exists():
            problems.append(f"missing: {rel}")
            continue
        if sha256_bytes(path.read_bytes()) != digest:
            problems.append(f"working copy hash differs: {rel}")
        committed = git("show", f"{freeze}:{rel}")
        if committed.returncode != 0:
            problems.append(f"not in freeze commit: {rel}")
        elif sha256_bytes(committed.stdout) != digest:
            problems.append(f"freeze commit content differs: {rel}")

    from bce.inputs import build_prompt
    from holdout import rules, seal

    problems += [f"holdout: {p}" for p in seal.verify_freeze()]
    candidates = sha256_bytes((rules.ROOT / "holdout/candidates.json").read_bytes())
    if candidates != doc["candidates_sha256"]:
        problems.append("candidates sha256 differs from manifest")
    if seal.recompute_commitment() != doc["holdout_commitment"]:
        problems.append("holdout commitment differs from manifest")
    for arm in ("B", "C"):
        _, hashes = build_prompt(arm, doc["discovery_n"])
        if hashes != doc["prompt_inputs"][arm]:
            problems.append(f"assembled inputs for arm {arm} differ from manifest")
    return problems


if __name__ == "__main__":
    issues = verify()
    print("OK: pre-3d freeze verified" if not issues else "\n".join(issues))
    sys.exit(1 if issues else 0)
