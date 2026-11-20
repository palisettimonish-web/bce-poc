"""Pre-3e freeze verification (2.20; Amendment 4). Verification only: it writes nothing and calls no model.

    PYTHONPATH=. python experiments/step3/verify_pre3e_freeze.py
"""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

from detect import rules

ROOT = rules.ROOT
MANIFEST = ROOT / "experiments/step3/manifests/pre3e_freeze.json"
PRE3D_VERIFIER = ROOT / "experiments/step3/verify_pre3d_freeze.py"
RESULTS_PREFIX = "experiments/step3/results/"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)


def is_ancestor(commit, descendant="HEAD"):
    return git("merge-base", "--is-ancestor", commit, descendant).returncode == 0


def compare_hashes(expected, read_work, read_commit, label="file"):
    """Problems for every expected {path: sha256} that differs in the working copy or in the freeze commit."""
    problems = []
    for rel, digest in sorted(expected.items()):
        work = read_work(rel)
        if work is None:
            problems.append(f"missing {label}: {rel}")
        elif sha256_bytes(work) != digest:
            problems.append(f"working copy hash differs: {rel}")
        committed = read_commit(rel)
        if committed is None:
            problems.append(f"{label} not in the freeze commit: {rel}")
        elif sha256_bytes(committed) != digest:
            problems.append(f"freeze commit content differs: {rel}")
    return problems


def dirty_paths(porcelain):
    """Dirty paths outside the 3e results directory (outputs of the experiment itself)."""
    paths = [line[3:].strip().strip('"') for line in porcelain.splitlines() if line.strip()]
    return [p for p in paths if not p.startswith(RESULTS_PREFIX)]


def _work(rel):
    p = ROOT / rel
    return p.read_bytes() if p.exists() else None


def _commit(commit):
    def read(rel):
        out = git("show", f"{commit}:{rel}")
        return out.stdout if out.returncode == 0 else None
    return read


def _pre3d_problems():
    spec = importlib.util.spec_from_file_location("verify_pre3d_freeze", PRE3D_VERIFIER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [f"pre-3d: {p}" for p in module.verify()]


def verify(manifest_path=MANIFEST):
    doc = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    problems = _pre3d_problems()
    freeze, sealed = doc["git_sha"], doc["sealed_3d_commit"]
    for label, commit in (("freeze commit", freeze), ("sealed 3d commit", sealed)):
        if git("cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
            problems.append(f"{label} not found: {commit}")
        elif not is_ancestor(commit):
            problems.append(f"{label} is not an ancestor of HEAD: {commit}")
    problems += compare_hashes(doc["files"], _work, _commit(freeze), "infrastructure file")
    problems += compare_hashes(doc["sealed_3d_files"], _work, _commit(sealed), "sealed 3d artifact")
    tracked = set(git("ls-files", "detect", "experiments/step3/verify_pre3e_freeze.py", "test_step3e.py").stdout.decode().split())
    problems += [f"tracked but not in the freeze manifest: {p}" for p in sorted(tracked - set(doc["files"]))]
    status = git("status", "--porcelain", "-uall").stdout.decode()
    problems += [f"working tree not clean: {p}" for p in dirty_paths(status)]
    return problems
