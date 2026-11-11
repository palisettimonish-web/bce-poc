"""Stage engine for S0-S6 (Amendment 2, 2.1, 2.5-2.9, 2.11).

Mechanical guarantees:
- stages run in the fixed order S0..S7 and batchwise: a stage runs only after the previous stage is
  complete for every candidate, and a stage runs at most once;
- a candidate becomes terminal at its first failed stage and is never run again;
- all logs are append-only, and a stage is evaluated only from the logged runs;
- the candidates file must be committed and unchanged since the first stage record;
- there is no replacement mechanism: a failed candidate stays failed and its slot stays empty.
"""

import json
import subprocess

from agent import SYSTEM
from bce import dsl
from holdout import rules, runtime, schema
from scenarios import make_expanded_clean_scenarios, make_scenarios

RUNS_LOG = "runs.jsonl"
STATUS_LOG = "status.jsonl"


class StageError(RuntimeError):
    """A stage was requested out of order, twice, or on an inconsistent input."""


class Incomplete(StageError):
    """Some planned runs have no completed record yet; run the stage again to resume."""


# ---------------------------------------------------------------------------- inputs

def ensure_committed(path):
    """The candidates file must be tracked and identical to HEAD before any stage is recorded (2.3)."""
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)], capture_output=True, cwd=rules.ROOT)
    dirty = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(path)], capture_output=True, cwd=rules.ROOT)
    if tracked.returncode != 0 or dirty.returncode != 0:
        raise StageError(f"{path} must be committed and unmodified before any stage is run")


def baseline_scenarios():
    return make_scenarios() + make_expanded_clean_scenarios()  # the 35 Arm A scenarios, in order


def world_scenario(raw, sid):
    return dsl.to_world_scenario(raw, sid)


# ---------------------------------------------------------------------------- state

class Run:
    """One validation session over a candidates file and a log directory."""

    def __init__(self, candidates_path, log_dir=rules.VALIDATION_DIR, executor=None, require_committed=True):
        self.candidates_path = candidates_path
        self.records = schema.load_candidates(candidates_path)
        self.by_id = {r["id"]: r for r in self.records}
        self.sha = runtime.sha256_file(candidates_path)
        self.runs = runtime.JsonlLog(log_dir / RUNS_LOG)
        self.status = runtime.JsonlLog(log_dir / STATUS_LOG)
        self.executor = executor
        self.require_committed = require_committed

    # -- bookkeeping --------------------------------------------------------
    def completed(self):
        return {r["stage"]: r for r in self.status.read() if r["type"] == "stage_complete"}

    def check_consistency(self):
        for r in self.status.read():
            if r["candidates_sha"] != self.sha:
                raise StageError("candidates file changed since a stage was recorded; nothing may change after the construction commit")

    def terminal(self, upto_stage):
        """{candidate_id: (status, stage)} from stages strictly before `upto_stage`."""
        done = self.completed()
        out = {}
        for stage in rules.STAGES[: rules.STAGES.index(upto_stage)]:
            if stage not in done:
                continue
            for cid, res in done[stage]["outcomes"].items():
                if cid not in out and res["status"] != rules.PASS:
                    out[cid] = (res["status"], stage)
        return out

    def active(self, stage):
        """Candidate ids still alive at the start of `stage`."""
        term = self.terminal(stage)
        return [r["id"] for r in self.records if r["id"] not in term]

    def final_status(self):
        """{candidate_id: (status, last_stage)} over all completed stages; ADMITTED after S7."""
        done = self.completed()
        term = self.terminal("S7") if "S7" in done else self.terminal(rules.STAGES[-1])
        out = {}
        for r in self.records:
            cid = r["id"]
            if cid in term:
                out[cid] = term[cid]
            elif "S7" in done:
                out[cid] = (rules.ADMITTED, "S7")
            else:
                last = [s for s in rules.STAGES if s in done]
                out[cid] = ("IN_PROGRESS", last[-1] if last else None)
        return out

    def require_order(self, stage):
        done = self.completed()
        if stage in done:
            raise StageError(f"{stage} is already complete and cannot be run again")
        idx = rules.STAGES.index(stage)
        if idx > 0 and rules.STAGES[idx - 1] not in done:
            raise StageError(f"{stage} cannot run before {rules.STAGES[idx - 1]} is complete (batchwise stage order)")

    # -- runs ---------------------------------------------------------------
    def runs_by_key(self):
        out = {}
        for rec in self.runs.read():
            if not rec.get("transport_failure"):
                out.setdefault(rec["key"], rec)
        return out

    def check_model_consistency(self):
        models = {m for rec in self.runs.read() for m in rec.get("models", [])}
        if len(models) > 1:
            raise runtime.InfrastructureFailure(f"served model string changed during 3c: {sorted(models)}")

    def execute(self, jobs):
        """Run the jobs that have no completed record yet. Raises Incomplete if any still lack one."""
        have = self.runs_by_key()
        for job in jobs:
            key = runtime.job_key(job)
            if key in have:
                continue
            if self.executor is None:
                raise StageError("no executor configured")
            rec = self.executor(job)
            self.runs.append(rec)
            self.check_model_consistency()
        have = self.runs_by_key()
        missing = [runtime.job_key(j) for j in jobs if runtime.job_key(j) not in have]
        if missing:
            raise Incomplete(f"{len(missing)} planned runs have no completed record (transport failures); run the stage again to resume")
        return [have[runtime.job_key(j)] for j in jobs]

    def degenerate_gate(self, records):
        bad = sum(1 for r in records if any(x in rules.DEGENERATE_REPLIES for x in r["replies"]))
        if records and bad / len(records) > rules.DEGENERATE_GATE:
            raise runtime.InfrastructureFailure(f"{bad}/{len(records)} runs returned empty or max-turn replies (> {rules.DEGENERATE_GATE:.0%})")

    # -- job planning -------------------------------------------------------
    def _job(self, stage, variant, cid, instance, rep, raw=None, scenario=None, system=SYSTEM):
        if scenario is None:
            scenario = world_scenario(raw, f"{cid}-{instance}")
        return {"stage": stage, "variant": variant, "subject": cid, "instance": instance, "rep": rep, "scenario": scenario, "system": system}

    def _mutant_system(self, cid):
        return schema.build_mutant_system(self.by_id[cid])

    def representatives(self):
        done = self.completed()
        if "S1" not in done:
            raise StageError("representatives are fixed when S1 completes")
        return done["S1"]["extra"]["representatives"]

    def plan(self, stage):
        """The jobs of an agent stage, for the candidates that are still active. Pure."""
        active = self.active(stage)
        jobs = []
        if stage == "S1":
            for cid in active:
                for inst in self.by_id[cid]["trigger_instances"]:
                    jobs += [self._job(stage, "clean", cid, inst["id"], r, raw=inst["scenario"]) for r in range(rules.S1_REPS)]
        elif stage == "S2":
            for cid in active:
                sysm = self._mutant_system(cid)
                for inst in self.by_id[cid]["trigger_instances"]:
                    jobs += [self._job(stage, "mutant", cid, inst["id"], r, raw=inst["scenario"], system=sysm) for r in range(rules.S2_REPS)]
        elif stage == "S3":
            for cid in active:
                sysm = self._mutant_system(cid)
                for inst in self.by_id[cid]["neutral_instances"]:
                    jobs += [self._job(stage, "mutant", cid, inst["id"], r, raw=inst["scenario"], system=sysm) for r in range(rules.S3_REPS)]
                    jobs += [self._job(stage, "clean", cid, inst["id"], r, raw=inst["scenario"]) for r in range(rules.S3_REPS)]
        elif stage == "S4":
            if active:
                for sc in baseline_scenarios():
                    jobs += [self._job(stage, "clean", "baseline", sc["id"], r, scenario=sc) for r in range(rules.S4_REPS)]
            for cid in active:
                sysm = self._mutant_system(cid)
                for sc in baseline_scenarios():
                    jobs += [self._job(stage, "mutant", cid, sc["id"], r, scenario=sc, system=sysm) for r in range(rules.S4_REPS)]
        elif stage == "S5":
            reps = self.representatives()
            for cid in active:
                sysm = self._mutant_system(cid)
                for dim, rep_cid in sorted(reps.items()):
                    if dim == self.by_id[cid]["dimension"]:
                        continue
                    raw = self.by_id[rep_cid]["trigger_instances"][0]["scenario"]
                    jobs += [self._job(stage, "mutant", cid, f"REP-{dim}", r, raw=raw, system=sysm) for r in range(rules.S5_REPS)]
        elif stage == "S6":
            for a, b in self.sibling_pairs(active):
                for src, dst in ((a, b), (b, a)):
                    raw = self.by_id[dst]["trigger_instances"][0]["scenario"]
                    sysm = self._mutant_system(src)
                    jobs += [self._job(stage, "mutant", src, f"SIB-{dst}-T1", r, raw=raw, system=sysm) for r in range(rules.S6_REPS)]
        else:
            raise StageError(f"{stage} is not an agent stage")
        return jobs

    def sibling_pairs(self, active):
        pairs = []
        ordered = sorted(active)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                if self.by_id[a]["dimension"] == self.by_id[b]["dimension"]:
                    pairs.append((a, b))
        return pairs

    # -- evaluation helpers ---------------------------------------------------
    @staticmethod
    def _select(recs, **match):
        return [r for r in recs if all(r[k] == v for k, v in match.items())]

    @staticmethod
    def _count(recs, code):
        return sum(1 for r in recs if code in r["violations"])

    # -- evaluators (pure functions of the logged runs) -------------------------
    def evaluate(self, stage, recs):
        return getattr(self, f"_eval_{stage.lower()}")(recs)

    def _eval_s1(self, recs):
        out = {}
        for cid in self.active("S1"):
            rates, bad = {}, False
            for inst in self.by_id[cid]["trigger_instances"]:
                runs = self._select(recs, subject=cid, instance=inst["id"], variant="clean")
                n = sum(1 for r in runs if r["violations"])
                rates[inst["id"]] = {"runs_with_any_violation": n, "runs": len(runs)}
                bad |= n > 0
            out[cid] = {"status": "CLEAN_NOT_CLEAN" if bad else rules.PASS, "details": {"clean_trigger": rates}, "rates": {"clean_trigger": rates}}
        reps = {}
        for r in self.records:
            if out.get(r["id"], {}).get("status") == rules.PASS:
                reps.setdefault(r["dimension"], r["id"])  # records are in id order: lowest id wins
        return out, {"representatives": reps}

    def _eval_s2(self, recs):
        out = {}
        for cid in self.active("S2"):
            c = self.by_id[cid]
            rates, short, unintended = {}, False, False
            for inst in c["trigger_instances"]:
                runs = self._select(recs, subject=cid, instance=inst["id"], variant="mutant")
                prim = self._count(runs, c["primary_code"])
                other = {code: self._count(runs, code) for code in sorted({x for r in runs for x in r["violations"]} - set(c["intended_codes"]))}
                rates[inst["id"]] = {"primary_code_runs": prim, "runs": len(runs), "non_intended_code_runs": other}
                short |= prim < rules.S2_MIN_PRIMARY
                unintended |= any(n >= rules.S2_UNINTENDED_FAIL for n in other.values())
            status = "STOCHASTIC_ADMISSION_FAILURE" if short else ("UNINTENDED_EFFECT" if unintended else rules.PASS)
            out[cid] = {"status": status, "details": {"mutant_trigger": rates}, "rates": {"mutant_trigger": rates}}
        return out, {}

    def _eval_s3(self, recs):
        out = {}
        for cid in self.active("S3"):
            c = self.by_id[cid]
            clean_bad = sum(1 for r in self._select(recs, subject=cid, variant="clean") if r["violations"])
            mut = self._select(recs, subject=cid, variant="mutant")
            fires = self._count(mut, c["primary_code"])
            if clean_bad:
                status = "CLEAN_NOT_CLEAN"  # the clean precondition is checked first, as in S1 before S2
            elif fires >= rules.S3_NEUTRAL_FAIL:
                status = "NEUTRAL_CONTROL_FAILURE"
            else:
                status = rules.PASS
            rates = {"neutral_mutant_primary_runs": fires, "neutral_mutant_runs": len(mut), "neutral_clean_runs_with_violation": clean_bad}
            out[cid] = {"status": status, "details": rates, "rates": rates}
        return out, {}

    def kill_codes(self, cid, mutant_runs, clean_runs):
        """Intended codes with an attributable kill: >= 2 of 3 mutant runs and 0 of 3 clean runs."""
        c = self.by_id[cid]
        return [
            code for code in c["intended_codes"]
            if self._count(mutant_runs, code) >= rules.KILL_MUTANT_MIN and self._count(clean_runs, code) == 0
        ]

    def _eval_s4(self, recs):
        out = {}
        for cid in self.active("S4"):
            c = self.by_id[cid]
            killers, partial, any_code = [], [], []
            for sc in baseline_scenarios():
                m = self._select(recs, subject=cid, instance=sc["id"], variant="mutant")
                k = self._select(recs, subject="baseline", instance=sc["id"], variant="clean")
                if self.kill_codes(cid, m, k):
                    killers.append(sc["id"])
                for code in c["intended_codes"]:
                    if self._count(m, code) == 1 and self._count(k, code) == 0:
                        partial.append({"scenario": sc["id"], "code": code})
                # original any-code kill (line 64), recorded but not used for exclusion
                if any(self._count(m, code) >= rules.KILL_MUTANT_MIN and self._count(k, code) == 0 for code in {x for r in m for x in r["violations"]}):
                    any_code.append(sc["id"])
            status = "ALREADY_COVERED_BY_BASELINE" if killers else rules.PASS
            details = {"attributable_kill_scenarios": killers, "partial_exposure": partial, "any_code_kill_scenarios": any_code}
            out[cid] = {"status": status, "details": details, "rates": {"baseline_attributable_kills": len(killers), "baseline_partial_exposure": len(partial), "baseline_any_code_kills": len(any_code)}}
        return out, {}

    def _eval_s5(self, recs):
        reps = self.representatives()
        out = {}
        for cid in self.active("S5"):
            c = self.by_id[cid]
            by_dim = {}
            for dim in sorted(reps):
                if dim == c["dimension"]:
                    continue
                runs = self._select(recs, subject=cid, instance=f"REP-{dim}", variant="mutant")
                by_dim[dim] = self._count(runs, c["primary_code"])
            hot = sum(1 for n in by_dim.values() if n >= rules.S5_FIRE_MIN)
            if hot >= rules.S5_NONSPECIFIC_DIMS:
                status, flags = "CROSS_TRIGGER_NON_SPECIFIC", []
            else:
                status, flags = rules.PASS, (["OVERLAP"] if hot == 1 else [])
            out[cid] = {"status": status, "flags": flags, "details": {"primary_code_runs_by_other_dimension": by_dim, "runs_per_dimension": rules.S5_REPS},
                        "rates": {"other_dimension_primary_runs": sorted(by_dim.values(), reverse=True), "runs_per_other_dimension": rules.S5_REPS}}
        return out, {}

    def _eval_s6(self, recs):
        active = self.active("S6")
        out = {cid: {"status": rules.PASS, "details": {}, "rates": {"sibling_primary_runs": []}} for cid in active}
        matrix, excluded = {}, set()
        for a, b in self.sibling_pairs(active):  # ascending id order
            ab = self._count(self._select(recs, subject=a, instance=f"SIB-{b}-T1", variant="mutant"), self.by_id[a]["primary_code"])
            ba = self._count(self._select(recs, subject=b, instance=f"SIB-{a}-T1", variant="mutant"), self.by_id[b]["primary_code"])
            matrix[f"{a}->{b}"] = ab
            matrix[f"{b}->{a}"] = ba
            out[a]["rates"]["sibling_primary_runs"].append(ab)
            out[b]["rates"]["sibling_primary_runs"].append(ba)
            if a in excluded or b in excluded:
                continue  # an excluded candidate is not compared again
            if ab >= rules.S6_EQUIVALENT_MIN and ba >= rules.S6_EQUIVALENT_MIN:
                excluded.add(b)  # the higher id is dropped
                out[b]["status"] = "VARIANT_EQUIVALENT"
                out[b]["details"]["equivalent_to"] = a
        return out, {"sibling_matrix": matrix, "runs_per_direction": rules.S6_REPS}

    # -- stage drivers ------------------------------------------------------
    def _record_stage(self, stage, outcomes, extra):
        self.status.append({"type": "stage_complete", "stage": stage, "candidates_sha": self.sha, "outcomes": outcomes,
                            "extra": extra, "git_sha": runtime.git_sha(), "timestamp": runtime.utc_now()})

    def run_s0(self, record=True):
        """S0: static checks only (no LLM, no agent). With record=False nothing is written (drafting pre-check)."""
        errors = schema.candidate_set_errors(self.records)
        if errors:
            raise StageError("candidate file is invalid as a set: " + "; ".join(errors))
        results = schema.run_s0(self.records)
        outcomes = {cid: {"status": st, "details": det, "rates": {}} for cid, (st, det) in results.items()}
        if record:
            if self.require_committed:
                ensure_committed(self.candidates_path)
            self.check_consistency()
            self.require_order("S0")
            self._record_stage("S0", outcomes, {})
        return outcomes

    def run_stage(self, stage):
        """Execute (or resume) an agent stage and record it. Returns the stage outcomes."""
        if stage not in ("S1", "S2", "S3", "S4", "S5", "S6"):
            raise StageError(f"{stage} is not an agent stage")
        if self.require_committed:
            ensure_committed(self.candidates_path)
        self.check_consistency()
        self.require_order(stage)
        jobs = self.plan(stage)
        recs = self.execute(jobs)
        self.degenerate_gate(recs)
        outcomes, extra = self.evaluate(stage, recs)
        self._record_stage(stage, outcomes, extra)
        return outcomes

    def apply_construct_review(self, outcomes):
        """S7 outcomes computed by holdout.review; recorded here to keep a single stage-completion path."""
        if self.require_committed:
            ensure_committed(self.candidates_path)
        self.check_consistency()
        self.require_order("S7")
        self._record_stage("S7", outcomes, {})

    # -- reporting ------------------------------------------------------------
    def attrition_table(self):
        final = self.final_status()
        table = {}
        for dim in rules.ELIGIBLE:
            row = {"candidates": 0, "ADMITTED": 0}
            for st in rules.TERMINAL_STATUSES:
                row[st] = 0
            table[dim] = row
        for r in self.records:
            row = table[r["dimension"]]
            status = final[r["id"]][0]
            if status != "NO_CANDIDATE":
                row["candidates"] += 1
            if status in row:
                row[status] += 1
        for dim, row in table.items():
            row["final_valid_hidden_mutants"] = row["ADMITTED"]
            row["NOT_DETECTION_TESTABLE"] = row["ADMITTED"] == 0
        return table
