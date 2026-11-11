"""Run one discovery call for arm B or C and store the raw output plus normalized artifacts.

Usage: python -m bce.run_discovery --arm C --run 1 [--n 20] [--out experiments/step3]
Open-loop: this module never executes scenarios. Files are created exclusively and never overwritten.
"""

import argparse
import datetime
import json
import subprocess
import uuid
from pathlib import Path

from agent import MODEL, PROJECT_ENDPOINT, _foundry_client
from bce import dsl
from bce.inputs import ROOT, build_prompt, sha256_file, sha256_text

CONFIG_PATH = ROOT / "experiments" / "step3" / "manifests" / "generation_config.json"
AMENDMENT_MANIFEST = ROOT / "experiments" / "step3" / "manifests" / "prereg_amendment1_freeze.json"
CONFIG_KEY = "experiments/step3/manifests/generation_config.json"


class ConfigError(RuntimeError):
    """The frozen generation configuration is missing, altered, or does not match the run."""


def load_frozen_config(model, endpoint, config_path=CONFIG_PATH, manifest_path=AMENDMENT_MANIFEST):
    """Return (config, sha256) after checking the file against the frozen manifest and the live run.

    Raises ConfigError if the file hash differs from the manifest, or if the model or endpoint in use
    differs from the frozen config. Nothing is invented or defaulted.
    """
    digest = sha256_file(config_path)
    frozen = json.loads(Path(manifest_path).read_text(encoding="utf-8"))["files"].get(CONFIG_KEY)
    if frozen is None:
        raise ConfigError("generation_config.json is not listed in the amendment manifest")
    if digest != frozen:
        raise ConfigError(f"generation_config.json hash {digest} != frozen {frozen}")
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if model != config["model_deployment"]:
        raise ConfigError(f"model {model!r} != frozen {config['model_deployment']!r}")
    if endpoint != config["endpoint"]:
        raise ConfigError(f"endpoint {endpoint!r} != frozen {config['endpoint']!r}")
    return config, digest


def _git_sha():
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def parse_output(text):
    """Strict parse: one JSON object. Returns (obj, error)."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(obj, dict):
        return None, "top level is not an object"
    return obj, None


def normalize(arm, obj, run_id):
    """Split a parsed output into candidates and scenario records with validity. No repair."""
    candidates = []
    if arm == "C":
        for i, c in enumerate(obj.get("candidates", []) if isinstance(obj.get("candidates"), list) else []):
            candidates.append({**c, "run_id": run_id, "position": i} if isinstance(c, dict) else {"raw": c, "run_id": run_id, "position": i})
    scenarios = []
    raw_scenarios = obj.get("scenarios", []) if isinstance(obj.get("scenarios"), list) else []
    for i, s in enumerate(raw_scenarios):
        errors = dsl.validate(s)
        scenarios.append({"run_id": run_id, "position": i, "scenario": s, "valid": not errors, "errors": errors})
    return candidates, scenarios


def run(arm, run_number, n, out, client=None, model=MODEL, endpoint=PROJECT_ENDPOINT, config_path=CONFIG_PATH, manifest_path=AMENDMENT_MANIFEST):
    out = Path(out)
    config, config_hash = load_frozen_config(model, endpoint, config_path, manifest_path)
    prompt, input_hashes = build_prompt(arm, n)
    client = client or _foundry_client()
    run_id = f"{arm}-{run_number:03d}-{uuid.uuid4().hex[:8]}"
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    response = client.responses.create(model=model, input=prompt)
    text = response.output_text or ""
    usage = getattr(response, "usage", None)
    obj, error = parse_output(text)
    candidates, scenarios = normalize(arm, obj, run_id) if obj is not None else ([], [])
    meta = {
        "run_id": run_id,
        "arm": arm,
        "run_number": run_number,
        "git_sha": _git_sha(),
        "provider": "microsoft-foundry-responses",
        "endpoint": endpoint,
        "model": model,
        "generation_config_hash": config_hash,
        "generation_config_id": config["config_id"],
        "configuration": {"requested_scenarios": n, "request_parameters_sent": config["request_parameters_sent"]},
        "seed": config["seed"],
        "timestamp": started,
        "prompt_hash": input_hashes["assembled_prompt"],
        "input_hashes": input_hashes,
        "tokens": {"input": getattr(usage, "input_tokens", None), "output": getattr(usage, "output_tokens", None)},
        "parse_error": error,
        "counts": {
            "candidates": len(candidates),
            "scenarios": len(scenarios),
            "valid_scenarios": sum(s["valid"] for s in scenarios),
        },
        "raw_output_hash": sha256_text(text),
    }
    files = {
        out / "discovery" / arm / f"run_{run_number:03d}_raw.json": {"meta": meta, "prompt": prompt, "raw_output": text},
        out / "normalized" / f"{arm}_run_{run_number:03d}_candidates.json": {"meta": meta, "candidates": candidates},
        out / "scenarios" / f"{arm}_run_{run_number:03d}_scenarios.json": {"meta": meta, "scenarios": scenarios},
    }
    for path, payload in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1)
            handle.write("\n")
    return meta


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=("B", "C"), required=True)
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--out", default="experiments/step3")
    args = parser.parse_args()
    print(json.dumps(run(args.arm, args.run, args.n, args.out)["counts"]))
