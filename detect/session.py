"""Append-only, resumable execution of agent jobs (2.14). The executor is injected so tests need no agent."""

from holdout import runtime
from detect import rules


class Incomplete(RuntimeError):
    """Some planned runs have no completed record (transport failures); run again to resume."""


class Session:
    def __init__(self, log_dir, executor):
        self.runs = runtime.JsonlLog(log_dir / rules.RUNS_LOG)
        self.status = runtime.JsonlLog(log_dir / rules.STATUS_LOG)
        self.executor = executor
        self._have = None

    def have(self):
        if self._have is None:
            self._have = {}
            for rec in self.runs.read():
                if not rec.get("transport_failure"):
                    self._have.setdefault(rec["key"], rec)
        return self._have

    def ensure(self, job):
        """The completed record for the job, running it when it has none. None after a transport failure."""
        key = runtime.job_key(job)
        have = self.have()
        if key in have:
            return have[key]
        rec = self.executor(job)
        rec.update(job.get("extra", {}))
        self.runs.append(rec)
        if rec.get("transport_failure"):
            return None
        have[key] = rec
        return rec

    def records(self):
        return self.runs.read()

    def degenerate_gate(self, records=None):
        records = [r for r in (self.records() if records is None else records) if not r.get("transport_failure")]
        bad = sum(1 for r in records if any(x in rules.DEGENERATE_REPLIES for x in r["replies"]))
        if records and bad / len(records) > rules.DEGENERATE_GATE:
            raise runtime.InfrastructureFailure(f"{bad}/{len(records)} runs returned empty or max-turn replies (> {rules.DEGENERATE_GATE:.0%})")
        return bad, len(records)

    def completed(self, kind):
        return [r for r in self.status.read() if r.get("type") == kind]

    def record_status(self, record):
        self.status.append({**record, "git_sha": runtime.git_sha(), "timestamp": runtime.utc_now()})
