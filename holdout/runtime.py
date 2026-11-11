"""Startup checks, recording client, append-only logs and single-job execution (Amendment 2, 2.14).

Agent runs go through the existing `agent.run_agent`; `agent.py` is not modified. Every run record
carries the agent config hash, the git SHA, the served model string(s), token usage and a UTC timestamp.
"""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import agent
from holdout import rules
from oracle import check
from world import World

AGENT_CONFIG = rules.MANIFEST_DIR / "agent_config.json"
AMENDMENT2_MANIFEST = rules.MANIFEST_DIR / "prereg_amendment2_freeze.json"
AGENT_CONFIG_KEY = "experiments/step3/manifests/agent_config.json"


class ConfigError(RuntimeError):
    """The agent configuration differs from the frozen one. The runner must not start."""


class InfrastructureFailure(RuntimeError):
    """A stop condition of the preregistration (line 78, 2.14) was hit. Work stops and is reported."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def tools_digest(tools):
    return sha256_bytes(json.dumps(tools, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def verify_agent_config(config_path=AGENT_CONFIG, manifest_path=AMENDMENT2_MANIFEST, model=None, endpoint=None,
                        system=None, tools=None):
    """Return (config, sha256). Raises ConfigError on any mismatch with the frozen Amendment 2 contract."""
    model = agent.MODEL if model is None else model
    endpoint = agent.PROJECT_ENDPOINT if endpoint is None else endpoint
    system = agent.SYSTEM if system is None else system
    tools = agent.TOOLS if tools is None else tools
    digest = sha256_file(config_path)
    frozen = json.loads(Path(manifest_path).read_text(encoding="utf-8"))["files"].get(AGENT_CONFIG_KEY)
    if frozen is None:
        raise ConfigError("agent_config.json is not listed in the Amendment 2 manifest")
    if digest != frozen:
        raise ConfigError(f"agent_config.json hash {digest} != frozen {frozen}")
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if model != config["model_deployment"]:
        raise ConfigError(f"model {model!r} != frozen {config['model_deployment']!r}")
    if endpoint != config["endpoint"]:
        raise ConfigError(f"endpoint {endpoint!r} != frozen {config['endpoint']!r}")
    if sha256_bytes(system.encode("utf-8")) != config["system_sha256"]:
        raise ConfigError("clean SYSTEM hash differs from the frozen agent config")
    if tools_digest(tools) != config["tools_sha256"]:
        raise ConfigError("TOOLS hash differs from the frozen agent config")
    return config, digest


def git_sha():
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=rules.ROOT).stdout.strip()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RecordingClient:
    """Wraps an OpenAI-style client; records the served model string and token usage of each response."""

    def __init__(self, inner):
        self.inner = inner
        self.models = []
        self.input_tokens = 0
        self.output_tokens = 0
        self.responses = self  # `client.responses.create(...)`

    def create(self, **kwargs):
        response = self.inner.responses.create(**kwargs)
        model = getattr(response, "model", None)
        if model is not None:
            self.models.append(model)
        usage = getattr(response, "usage", None)
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        return response


class JsonlLog:
    """Append-only JSONL file. Existing lines are never rewritten; there is no delete or update."""

    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def append(self, record):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def job_key(job):
    return "|".join([job["stage"], job["variant"], job["subject"], job["instance"], str(job["rep"])])


def run_job(job, client, config_hash, candidates_sha, attempts=rules.TRANSPORT_ATTEMPTS):
    """Execute one agent run. Transport/API errors are retried (each attempt logged); outcomes are not."""
    scenario = job["scenario"]
    attempt_log = []
    recorder = RecordingClient(client)
    world = replies = None
    for attempt in range(1, attempts + 1):
        world = World(scenario["fixture"], scenario["faults"], scenario["approval_granted"])
        recorder = RecordingClient(client)
        try:
            replies = agent.run_agent(world, scenario["messages"], system=job["system"], client=recorder)
            break
        except Exception as exc:  # transport / API failure: no response was produced
            attempt_log.append({"attempt": attempt, "error": f"{type(exc).__name__}: {exc}"})
            replies = None
    record = {
        "key": job_key(job),
        "stage": job["stage"],
        "variant": job["variant"],
        "subject": job["subject"],
        "instance": job["instance"],
        "rep": job["rep"],
        "scenario": scenario["id"],
        "scenario_params": {k: scenario[k] for k in ("requester_id", "fixture", "faults", "messages", "approval_granted") if k in scenario},
        "agent_config_hash": config_hash,
        "candidates_sha": candidates_sha,
        "git_sha": git_sha(),
        "timestamp": utc_now(),
        "attempt_errors": attempt_log,
    }
    if replies is None:
        record.update({"transport_failure": True, "replies": [], "calls": [], "ledger": [], "violations": [], "models": [],
                       "served_models_per_response": [], "tokens": None})
    else:
        record.update({
            "transport_failure": False,
            "replies": replies,
            "calls": world.calls,
            "ledger": world.ledger(),
            "violations": check(world, scenario, replies),
            "models": sorted(set(recorder.models)),
            "served_models_per_response": list(recorder.models),
            "tokens": {"input": recorder.input_tokens, "output": recorder.output_tokens},
        })
    return record
