"""Append-only, resumable execution of agent jobs (2.14). The executor is injected so tests need no agent.

Amendment 5 (A5.1, A5.2): a job ends in exactly one of three ways. It completes (a record with an agent outcome); it fails in
transport (no outcome, retried on the next invocation); or it is PROVIDER_REJECTED, an execution-level terminal state: every
attempt of one invocation was a deterministic provider refusal, so retrying cannot change it. A rejected job has no agent
outcome and invents none: its record keeps `transport_failure: true` (no violations, no replies) and adds `terminal_state`.
It is not a DSL-invalid scenario; the scenario passed the frozen validator and stays a VALID slot. An authentication failure
stops the run at once (fail fast).
"""

from holdout import rules as holdout_rules
from holdout import runtime
from detect import rules


class Incomplete(RuntimeError):
    """Some planned runs have no completed record (transport failures); run again to resume."""


class AuthenticationFailure(runtime.InfrastructureFailure):
    """Every attempt failed with an authentication error. Nothing else is attempted; fix the credentials and resume."""


def _error_type(entry):
    return entry["error"].split(":", 1)[0].strip()


def classify_failure(rec):
    """None for a completed record; else "AUTH", rules.TERMINAL_REJECTED or "TRANSPORT" for a failed one."""
    if not rec.get("transport_failure"):
        return None
    errors = rec.get("attempt_errors") or []
    if errors and _error_type(errors[-1]) in rules.AUTH_ERROR_TYPES:
        return "AUTH"
    if errors and len(errors) >= holdout_rules.TRANSPORT_ATTEMPTS and all(_error_type(e) in rules.REJECTED_ERROR_TYPES for e in errors):
        return rules.TERMINAL_REJECTED
    return "TRANSPORT"


def is_rejected(rec):
    return bool(rec) and rec.get("terminal_state") == rules.TERMINAL_REJECTED


def is_completed(rec):
    return not rec.get("transport_failure")


class Session:
    def __init__(self, log_dir, executor, guard=None):
        self.runs = runtime.JsonlLog(log_dir / rules.RUNS_LOG)
        self.status = runtime.JsonlLog(log_dir / rules.STATUS_LOG)
        self.executor = executor
        self.guard = guard  # optional callable(record): inspects each newly completed record and may raise (A5.4)
        self._have = None

    def have(self):
        """The first final record per key: a completed run or a PROVIDER_REJECTED terminal record. Transport failures are not final."""
        if self._have is None:
            self._have = {}
            for rec in self.runs.read():
                if is_completed(rec) or is_rejected(rec):
                    self._have.setdefault(rec["key"], rec)
        return self._have

    def ensure(self, job):
        """The final record for the job, running it when it has none. None after a (retryable) transport failure.

        A PROVIDER_REJECTED job is returned as its terminal record and is never executed again. An authentication failure is
        logged and then raises AuthenticationFailure.
        """
        key = runtime.job_key(job)
        have = self.have()
        if key in have:
            return have[key]
        rec = self.executor(job)
        rec.update(job.get("extra", {}))
        kind = classify_failure(rec)
        if kind == rules.TERMINAL_REJECTED:
            rec["terminal_state"] = rules.TERMINAL_REJECTED
        self.runs.append(rec)
        if kind == "AUTH":
            raise AuthenticationFailure(f"authentication failed for {key}: {rec['attempt_errors'][-1]['error'][:160]}; fix the credentials and resume")
        if kind == "TRANSPORT":
            return None
        have[key] = rec
        if kind is None and self.guard is not None:
            self.guard(rec)
        return rec

    def records(self):
        return self.runs.read()

    def degenerate_gate(self, records=None):
        records = [r for r in (self.records() if records is None else records) if is_completed(r)]
        bad = sum(1 for r in records if any(x in rules.DEGENERATE_REPLIES for x in r["replies"]))
        if records and bad / len(records) > rules.DEGENERATE_GATE:
            raise runtime.InfrastructureFailure(f"{bad}/{len(records)} runs returned empty or max-turn replies (> {rules.DEGENERATE_GATE:.0%})")
        return bad, len(records)

    def completed(self, kind):
        return [r for r in self.status.read() if r.get("type") == kind]

    def record_status(self, record):
        self.status.append({**record, "git_sha": runtime.git_sha(), "timestamp": runtime.utc_now()})
