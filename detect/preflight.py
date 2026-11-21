"""Pre-3e freeze verification (2.20; Amendments 4 and 5). Verification only: it writes nothing and calls no model.

    PYTHONPATH=. python experiments/step3/verify_pre3e_freeze.py

Amendment 5 adds: the new freeze manifest (which also re-pins every Amendment 4 file it did not change and `scenarios.py`),
the Amendment 4 freeze commit as an ancestor, results-directory sealing and history checks, and the per-record ancestry and
configuration check that A4.7 requires (`record_problems`).
"""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

from detect import rules

ROOT = rules.ROOT
MANIFEST = ROOT / "experiments/step3/manifests/pre3e_freeze_a5.json"  # supersedes pre3e_freeze.json (kept, and re-pinned inside this one)
TRACKED_INFRASTRUCTURE = ("detect", "experiments/step3/verify_pre3e_freeze.py", "test_step3e.py", "test_step3e_a5.py")
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
    freeze, sealed, a4 = doc["git_sha"], doc["sealed_3d_commit"], doc["amendment4_freeze_commit"]
    found = set()
    for label, commit in (("freeze commit", freeze), ("sealed 3d commit", sealed), ("Amendment 4 freeze commit", a4)):
        if git("cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
            problems.append(f"{label} not found: {commit}")
        elif not is_ancestor(commit):
            problems.append(f"{label} is not an ancestor of HEAD: {commit}")
        else:
            found.add(commit)
    if {a4, freeze} <= found and not is_ancestor(a4, freeze):
        problems.append("the Amendment 4 freeze commit is not an ancestor of the Amendment 5 freeze commit")
    problems += compare_hashes(doc["files"], _work, _commit(freeze), "infrastructure file")
    problems += compare_hashes(doc["frozen_input_hashes"], _work, _commit(freeze), "frozen input")
    problems += compare_hashes(doc["sealed_3d_files"], _work, _commit(sealed), "sealed 3d artifact")
    tracked = set(git("ls-files", *TRACKED_INFRASTRUCTURE).stdout.decode().split())
    problems += [f"tracked but not in the freeze manifest: {p}" for p in sorted(tracked - set(doc["files"]))]
    status = git("status", "--porcelain", "-uall").stdout.decode()
    problems += [f"working tree not clean: {p}" for p in dirty_paths(status)]
    return problems


# ---------------------------------------------------------------------------- Amendment 5: results integrity (A5.5)

def frozen_config_hash():
    """The agent_config.json hash frozen in the Amendment 2 manifest (the value every run record must carry)."""
    from holdout import runtime
    manifest = json.loads(runtime.AMENDMENT2_MANIFEST.read_text(encoding="utf-8"))
    return manifest["files"][runtime.AGENT_CONFIG_KEY]


def freeze_sha(manifest_path=MANIFEST):
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))["git_sha"]


def record_problems(records, freeze_commit, config_hash, candidates_sha, ancestor=is_ancestor):
    """A4.7 / A5.5: every run record's git SHA has the freeze commit as an ancestor and its frozen hashes match. Pure given `ancestor`."""
    problems, seen = [], {}
    for r in records:
        sha = r.get("git_sha")
        if sha not in seen:
            seen[sha] = bool(sha) and ancestor(freeze_commit, sha)
        if not seen[sha]:
            problems.append(f"{r.get('key')}: git_sha {sha!r} does not descend from the freeze commit {freeze_commit}")
        if r.get("agent_config_hash") != config_hash:
            problems.append(f"{r.get('key')}: agent_config_hash {r.get('agent_config_hash')!r} != frozen {config_hash}")
        if r.get("candidates_sha") != candidates_sha:
            problems.append(f"{r.get('key')}: candidates_sha differs from the frozen candidates file")
    return problems


def _rel(directory):
    return str(Path(directory).resolve().relative_to(ROOT.resolve()))


def sealed_problems(directory, label):
    """The results directory must hold files and every one of them must be committed and unmodified (A5.5)."""
    d = Path(directory)
    if not d.exists() or not any(d.rglob("*.jsonl")):
        return [f"{label}: no results found in {_rel(d)}"]
    status = git("status", "--porcelain", "-uall", "--", _rel(d)).stdout.decode().strip()
    return [f"{label}: results are not committed and unmodified: {line.strip()}" for line in status.splitlines()]


def history_problems(directory, label):
    """A directory that has ever been committed but has no files now was deleted: a re-run would break 'never re-run' (A5.5)."""
    d = Path(directory)
    if d.exists() and any(d.rglob("*")):
        return []
    log = git("log", "--all", "--format=%h", "--", _rel(d)).stdout.decode().split()
    return [f"{label}: {_rel(d)} existed in commit {log[0]} but is missing now; it is never re-run"] if log else []
