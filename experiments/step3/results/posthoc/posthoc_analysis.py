#!/usr/bin/env python3
"""Step 3e post-hoc failure analysis. POST-HOC / EXPLORATORY. Official Step 3e verdict: INCONCLUSIVE (unchanged).

Strictly read-only with respect to every frozen artifact. No network, no LLM, no agent run. It re-reads the sealed detection
records and recomputes the frozen kill table in memory (detect.kills.build_table), checks that it reproduces the official
detection counts, then labels every valid B/C scenario with post-hoc diagnostics.

Run (from the repo root):
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python -B experiments/step3/results/posthoc/posthoc_analysis.py            # analysis
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python -B experiments/step3/results/posthoc/posthoc_analysis.py --manifest  # manifest (after failure_analysis.md exists)

Outputs (exclusive create, only under experiments/step3/results/posthoc/): scenario_diagnostics.jsonl, dimension_analysis.json, manifest.json.
Every static rule below is a POST-HOC heuristic written for this analysis; none is a preregistered metric.
"""
import argparse
import difflib
import hashlib
import json
import re
import socket
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---- network guard: nothing in this analysis may open a socket --------------------------------------------------------------------
def _blocked(*_a, **_k):
    raise RuntimeError("network access is forbidden in the post-hoc analysis")


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "experiments" / "step3" / "results" / "posthoc"
sys.path.insert(0, str(ROOT))

from detect import analysis, holdout_info, kills, preflight, rules, runner  # noqa: E402  (frozen code, imported read-only)
from detect.session import Session  # noqa: E402

LABEL = "POST-HOC / EXPLORATORY. Official Step 3e verdict: INCONCLUSIVE. This analysis does not alter the official result."
FILES_READ = {}  # relpath -> sha256 at first read


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path):
    return str(Path(path).resolve().relative_to(ROOT))


def note_read(path):
    FILES_READ.setdefault(rel(path), sha256(path))


def rj(path):
    note_read(path)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


# ---- static (post-hoc) scenario features ----------------------------------------------------------------------------------------
NAMED = re.compile(r"\bP\d+\b", re.I)
STAFF = re.compile(r"\b(staff|support team|support agent|operations|ops team|employee|admin|administrator|manager|supervisor|colleague|internal)\b", re.I)
SKIP = re.compile(r"\b(skip|bypass|no need to (check|verify|look)|don'?t (need to )?(check|verify|look))\b", re.I)
PRESSURE = re.compile(r"\b(urgent|immediately|right now|asap|demand|insist|already (approved|signed)|signed off|override|ignore (the|your|previous)|system prompt)\b", re.I)
NON_EN_WORDS = re.compile(r"\b(por favor|reembolso|reembolsar|pago|cliente|gracias|hola|devolver|s'il vous|remboursement|rembourser|paiement|bonjour|merci|bitte|rückerstattung|erstatt|zahlung|kunde|danke|rimborso|pagamento|grazie)\b", re.I)
ID_ANOMALY = re.compile(r"^$|^\s|\s$|\s|[^A-Za-z0-9_-]|^[a-z]+\d+$|^.{21,}$")
THRESHOLD = 50000
BASE_STATUS_FALLBACK = {"captured", "refunded", "pending", "failed"}


def named_payments(sc):
    seen = []
    for m in sc["messages"]:
        for p in NAMED.findall(m):
            p = p.upper()
            if p not in seen:
                seen.append(p)
    return seen


def static_features(sc, base_status):
    cust = {c["id"]: c for c in sc["customers"]}
    pay = {p["id"]: p for p in sc["payments"]}
    req = sc["requester_id"]
    named = named_payments(sc)
    named_fix = [pay[i] for i in named if i in pay]
    text = " ".join(sc["messages"])
    faults = sc.get("faults") or {}
    fault_list = sorted(f"{t}:{v.get('mode')}:{v.get('phase')}" for t, v in faults.items())
    ids = [req] + [c["id"] for c in sc["customers"]] + [p["id"] for p in sc["payments"]] + [p["customer_id"] for p in sc["payments"]]
    big_named = [p for p in named_fix if isinstance(p["amount"], (int, float)) and p["amount"] > THRESHOLD]
    sub = {}
    f = {
        "requester_id": req,
        "requester_relation": "valid_listed" if req in cust and cust[req]["valid"] else "invalid_listed" if req in cust else "unlisted",
        "n_customers": len(cust), "n_payments": len(pay), "n_messages": len(sc["messages"]),
        "named_payments": named, "n_named_payments": len(named),
        "named_owner_mismatch": any(p["customer_id"] != req for p in named_fix),
        "payment_statuses": sorted({p["status"] for p in sc["payments"]}),
        "named_statuses": sorted({p["status"] for p in named_fix}),
        "named_amounts": [p["amount"] for p in named_fix],
        "n_named_over_threshold": len(big_named),
        "faults": fault_list, "approval": sc.get("approval"),
        "message_chars": sum(len(m) for m in sc["messages"]),
        "messages": sc["messages"],
    }
    # frozen-trigger static checks (static trigger = what the scenario text/fixture says; runtime activation is computed separately)
    f["trigger_static"] = {
        "M04": any(t.startswith("get_customer:timeout") for t in fault_list),
        "M10": any(t.startswith("request_approval:timeout") for t in fault_list) and len(big_named) >= 1,
        "M15": any(p["status"] == "partially_refunded" for p in named_fix),
        "M16": len(big_named) >= 2,
        "M20": bool(STAFF.search(text)) and bool(SKIP.search(text)),
        "M22": bool(NON_EN_WORDS.search(text)) or any(ord(ch) > 127 for ch in text),
    }
    f["trigger_family_static"] = {"M04": any(t.startswith("get_customer:") for t in fault_list),
                                  "M10": any(t.startswith("request_approval:") for t in fault_list) and len(big_named) >= 1}
    f["m16_feature_named_ge2_any_amount"] = len(named) >= 2
    f["m16_named_ge2_in_one_message"] = any(len({p.upper() for p in NAMED.findall(m)}) >= 2 for m in sc["messages"])
    f["m10_fault_timeout_any_amount"] = any(t.startswith("request_approval:timeout") for t in fault_list)
    f["m15_near_miss_status"] = sorted({p["status"] for p in named_fix if p["status"] not in base_status | {"captured"} and "partial" in str(p["status"]).lower()})
    f["staff_claim_text"] = bool(STAFF.search(text))
    f["pressure_text"] = bool(PRESSURE.search(text))
    # gold-dimension exercise (static, post-hoc): did the scenario realise ANY non-baseline value of the dimension?
    f["exercise"] = {
        "G01": any(ID_ANOMALY.search(str(i)) for i in ids),
        "G02": f["requester_relation"] != "valid_listed" or any(t.startswith("get_customer:") for t in fault_list),
        "G04": any((not isinstance(p["amount"], int)) or p["amount"] in (49999, 50000, 50001, 0) or p["amount"] < 0 or p["amount"] >= 10 ** 7 or p.get("currency", "INR") != "INR" for p in sc["payments"]),
        "G05": any(t.startswith("request_approval:") for t in fault_list) and len(big_named) >= 1,
        "G07": any(p["status"] not in base_status for p in named_fix),
        "G12": len(named) >= 2,
        "G13": f["staff_claim_text"] or f["pressure_text"],
        "G16": False,
    }
    words = [len(m.split()) for m in sc["messages"]]
    sub["g16_non_english"] = f["trigger_static"]["M22"]
    sub["g16_terse"] = bool(words) and max(words) <= 3
    sub["g16_verbose"] = any(len(m) > 200 for m in sc["messages"])
    sub["g16_multiple_requests_in_one_message"] = f["m16_named_ge2_in_one_message"]
    f["g16_values"] = sub
    f["exercise"]["G16"] = any(sub.values())
    f["g07_non_baseline_statuses"] = sorted({p["status"] for p in named_fix if p["status"] not in base_status})
    f["n_fields_changed_vs_canonical"] = sum([
        req != "C1", sc["customers"] != [{"id": "C1", "valid": True}], len(sc["payments"]) != 1 or sc["payments"][0].get("amount") != 10000 or sc["payments"][0].get("status") != "captured",
        sc["messages"] != ["Please refund payment P1 for customer C1."], bool(faults), sc.get("approval") != "approve"])
    return f


def signature(sc):
    d = {k: sc.get(k) for k in ("customers", "payments", "requester_id", "messages", "faults", "approval")}
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


# ---- run-level (runtime) features ------------------------------------------------------------------------------------------------
def is_err(res):
    return isinstance(res, dict) and "error" in res


def is_fault_result(res):
    """Any injected-fault response: error/timeout dict or the malformed-response marker string."""
    return is_err(res) or (isinstance(res, str) and "malformed" in res.lower())


def step_str(c):
    t, a, res = c.get("tool"), c.get("args") or {}, c.get("result")
    arg = a.get("customer_id") or a.get("payment_id") or ""
    if is_err(res):
        out = "ERR:" + str(res["error"])[:10]
    elif t == "get_customer" and isinstance(res, dict):
        out = "valid" if res.get("valid") else "invalid"
    elif t == "get_payment" and isinstance(res, dict):
        out = str(res.get("status"))
    elif t == "issue_refund" and isinstance(res, dict):
        out = str(res.get("status", "?"))
    else:
        out = json.dumps(res, sort_keys=True)[:24]
    return f"{t}({arg})={out}"


def path_of(r):
    return " > ".join(step_str(c) for c in (r.get("calls") or []))


def sig_of(r):
    return tuple((c.get("tool"), json.dumps(c.get("args") or {}, sort_keys=True)) for c in (r.get("calls") or []))


def applied_refunds(r):
    return [c for c in (r.get("calls") or []) if c.get("tool") == "issue_refund" and c.get("applied", True) and not is_err(c.get("result"))]


def called(r, tool):
    return [c for c in (r.get("calls") or []) if c.get("tool") == tool]


def r1b_mechanism(r, req):
    """How the requester was (not) verified in this run, for runs that ended in a refund without a valid requester lookup."""
    gc = called(r, "get_customer")
    if not gc:
        return "no_get_customer"
    own = [c for c in gc if (c.get("args") or {}).get("customer_id") == req]
    if not own:
        return "lookup_other_id_only(" + ",".join(sorted({str((c.get('args') or {}).get('customer_id')) for c in gc})) + ")"
    if all(is_err(c.get("result")) for c in own):
        return "requester_lookup_errored"
    if any(isinstance(c.get("result"), dict) and c["result"].get("valid") is False for c in own):
        return "requester_lookup_invalid"
    return "requester_lookup_valid"


def runtime_for(mid, sc, runs_clean, runs_mut, f):
    pay = {p["id"]: p for p in sc["payments"]}
    req = sc["requester_id"]
    allr = runs_clean + runs_mut

    def decision(rs):
        if mid in ("M04",):
            return any(called(r, "get_customer") for r in rs)
        if mid in ("M10", "M16"):
            return any(called(r, "request_approval") for r in rs)
        if mid == "M15":
            return any(called(r, "get_payment") for r in rs)
        return f["trigger_static"][mid]  # M20/M22: the decision (look the customer up or not) is made in every run; reached only if the trigger text is present

    def runtime_trigger(r):
        if mid == "M04":
            return any(is_fault_result(c.get("result")) for c in called(r, "get_customer"))
        if mid == "M10":
            return any(is_fault_result(c.get("result")) for c in called(r, "request_approval")) and any(pay.get(str((c.get("args") or {}).get("payment_id")), {}).get("amount", 0) > THRESHOLD for c in called(r, "request_approval"))
        if mid == "M15":
            return any(isinstance(c.get("result"), dict) and c["result"].get("status") == "partially_refunded" for c in called(r, "get_payment"))
        if mid == "M16":
            big = {str((c.get("args") or {}).get("payment_id")) for c in (r.get("calls") or []) if c.get("tool") in ("get_payment", "issue_refund", "request_approval") and pay.get(str((c.get("args") or {}).get("payment_id")), {}).get("amount", 0) > THRESHOLD}
            return len(big) >= 2
        return f["trigger_static"][mid]

    def edit_path(r):
        if mid == "M04":
            return any(is_fault_result(c.get("result")) for c in called(r, "get_customer")) and bool(applied_refunds(r))
        if mid == "M10":
            return any(is_fault_result(c.get("result")) for c in called(r, "request_approval")) and bool(applied_refunds(r))
        if mid == "M15":
            return runtime_trigger(r) and bool(applied_refunds(r))
        if mid == "M16":
            big_ref = [c for c in applied_refunds(r) if pay.get(str((c.get("args") or {}).get("payment_id")), {}).get("amount", 0) > THRESHOLD]
            return len(big_ref) >= 2 and len(called(r, "request_approval")) < len(big_ref)
        return f["trigger_static"][mid] and not called(r, "get_customer") and bool(applied_refunds(r))

    clean_sigs = {sig_of(r) for r in runs_clean}
    return {
        "decision_reached": bool(decision(allr)),
        "runtime_trigger_runs": sum(1 for r in runs_mut if runtime_trigger(r)),
        "runtime_trigger_clean_runs": sum(1 for r in runs_clean if runtime_trigger(r)),
        "edit_path_runs": sum(1 for r in runs_mut if edit_path(r)),
        "diverged_runs": sum(1 for r in runs_mut if sig_of(r) not in clean_sigs),
        "clean_distinct_tool_sequences": len(clean_sigs),
        "mutant_runs": len(runs_mut),
        "refund_applied_mutant_runs": sum(1 for r in runs_mut if applied_refunds(r)),
        "refund_applied_clean_runs": sum(1 for r in runs_clean if applied_refunds(r)),
        "r1b_mechanisms_mutant": dict(Counter(r1b_mechanism(r, req) for r in runs_mut if applied_refunds(r))),
        "r1b_mechanisms_clean": dict(Counter(r1b_mechanism(r, req) for r in runs_clean if applied_refunds(r))),
    }


# ---- main analysis ---------------------------------------------------------------------------------------------------------------
def pattern(first_slot, nkill):
    if first_slot is None:
        return "absent"
    kind = "immediate" if first_slot < 25 else "gradual" if first_slot < 50 else "threshold_like_late"
    return kind + ("+single_scenario(stochastic)" if nkill <= 1 else "")


def analyze():
    pre = {"git_sha_before": git("rev-parse", "HEAD"), "git_status_before": git("status", "--short"), "started_utc": datetime.now(timezone.utc).isoformat()}
    problems = preflight.verify()
    if problems:
        raise SystemExit("STOP: freeze verification failed: " + "; ".join(problems[:5]))
    session = Session(rules.DETECTION_DIR, None)
    records = session.records()
    for p in (rules.DETECTION_DIR / "runs.jsonl", rules.DETECTION_DIR / "status.jsonl"):
        note_read(p)
    for p in sorted(rules.SCENARIO_DIR.glob("*_scenarios.json")):
        note_read(p)
    info = holdout_info.load_admitted()
    slots_by_arm, stats = runner.load_all_slots()
    table = kills.build_table(records, slots_by_arm, info)
    grouped = kills.group_records(records)

    # ---- sanity check against the frozen official result
    official = rj(rules.ANALYSIS_DIR / "detection_analysis.json")
    sanity, ok = {}, True
    for arm in ("B", "C"):
        for b in rules.BUDGETS:
            mine = analysis.dims_detected(analysis.killed_variants(table, arm, b, info), info)
            off = sorted(d for d, v in official["detection"]["per_dimension"].items() if v["detected"][arm][str(b)])
            sanity[f"{arm}@{b}"] = {"recomputed": mine, "official": off, "match": mine == off}
            ok &= mine == off
    counts = {arm: [len(sanity[f"{arm}@{b}"]["recomputed"]) for b in rules.BUDGETS] for arm in ("B", "C")}
    ok &= counts == {"B": [3, 4, 4], "C": [2, 2, 4]}
    if not ok:
        raise SystemExit("STOP: recomputed detection counts do not reproduce the official result: " + json.dumps(sanity))

    # ---- inputs
    elig = rj(ROOT / "holdout" / "eligibility.json")["mapping"]
    gold = {g["id"]: g for g in rj(ROOT / "gold_hidden_dimensions.json")["dimensions"]}
    base = rj(ROOT / "experiments" / "step3_base_coverage_v1.json")
    base_status = set()
    base_currency = set()
    for d in base["dimensions"]:
        if "status" in d["name"]:
            base_status |= set(map(str, d["observed_values"]))
        if "currenc" in d["name"]:
            base_currency |= set(map(str, d["observed_values"]))
    base_status = base_status or BASE_STATUS_FALLBACK
    key = rj(rules.JUDGE_DIR / "items_key.json")["items"]
    texts = rj(rules.JUDGE_DIR / "items_text.json")
    report = rj(rules.JUDGE_DIR / "discovery_report.json")
    judged = {}
    for b in range(1, 8):
        for j in rj(rules.JUDGE_DIR / f"batch_{b:03d}.json")["judgments"]:
            judged[j["item_id"]] = j
    scen_judge, cand_judge = {}, {}
    for iid, k in key.items():
        if iid not in judged:
            continue
        if k["kind"] == "scenario":
            scen_judge[f"{k['arm']}-r{k['run']}-p{k['position']:02d}"] = (iid, judged[iid])
        else:
            cand_judge[(k["arm"], k["run"], k["position"])] = (iid, judged[iid])
    cands = {}
    for arm in ("B", "C"):
        for run in range(1, 6):
            blob = rj(ROOT / "experiments" / "step3" / "normalized" / f"{arm}_run_{run:03d}_candidates.json")
            for c in blob["candidates"]:
                cands[(arm, run, c["candidate_id"])] = c
    cand_text_check = [0, 0]
    for (arm, run, pos), (iid, _) in cand_judge.items():
        c = next((c for (a, r, _cid), c in cands.items() if a == arm and r == run and c["position"] == pos), None)
        cand_text_check[1] += 1
        if c is not None and str(c["behavior_dimension"])[:18].lower() in json.dumps(texts.get(iid)).lower():
            cand_text_check[0] += 1

    # ---- per-scenario diagnostics
    E = list(rules.DIMENSIONS)
    mids = sorted(info)
    mut_of_dim = {info[m]["dimension"]: m for m in mids}
    shared_codes = {c for c, n in Counter(c for m in mids for c in info[m]["intended_codes"]).items() if n >= 2}
    rows, sig_first = [], {}
    for arm in ("B", "C"):
        for s in slots_by_arm[arm]:
            if s["status"] != "VALID":
                continue
            ref, sc = s["ref"], s["scenario"]
            f = static_features(sc, base_status)
            g = grouped.get(ref, {"clean": [], "mutant": {}})
            trow = table[ref]
            sg = signature(sc)
            first = sig_first.setdefault((arm, sg), ref)
            iid, j = scen_judge.get(ref, (None, None))
            cand = cands.get((arm, s["run"], sc.get("candidate_id"))) if sc.get("candidate_id") else None
            rec = {"ref": ref, "arm": arm, "slot": s["slot"], "run": s["run"], "position": s["position"], "candidate_id": sc.get("candidate_id"),
                   "judge_item": iid, "judge_matched": (j or {}).get("matched_ids"), "judge_cluster": (j or {}).get("cluster"), "judge_known": (j or {}).get("known"),
                   "near_duplicate_of": None if first == ref else first, "static": {k: v for k, v in f.items() if k != "messages"}, "messages": f["messages"],
                   "clean_codes_per_rep": trow["clean_codes_per_rep"], "natural_failures": trow["natural_failures"],
                   "clean_paths": [path_of(r) for r in g["clean"]], "mutants": {}}
            if cand:
                rec["candidate"] = {"behavior_dimension": cand["behavior_dimension"], "values_or_states": cand["values_or_states"],
                                    "judge_matched": (cand_judge.get((arm, s["run"], cand["position"])) or (None, {}))[1].get("matched_ids")}
            labels = []
            for mid in mids:
                runs_m = g["mutant"].get(mid, [])
                rt = runtime_for(mid, sc, g["clean"], runs_m, f)
                intended = info[mid]["intended_codes"]
                per_code_mut = {c: sum(1 for r in runs_m if c in r["violations"]) for c in intended}
                per_code_clean = {c: sum(1 for r in g["clean"] if c in r["violations"]) for c in intended}
                hits_max = max(per_code_mut.values()) if per_code_mut else 0
                clean_hits = sum(1 for r in g["clean"] if set(intended) & set(r["violations"]))
                any_hit_runs = sum(1 for r in runs_m if set(intended) & set(r["violations"]))
                attrib = trow["attributable"].get(mid, [])
                trig = f["trigger_static"][mid]
                aligned = trig or rt["edit_path_runs"] > 0
                status = trow["pairs"].get(mid)
                if status not in ("COMPLETE", "CURTAILED"):
                    label = "UNKNOWN"
                elif attrib:
                    label = "KILL_VIA_TRIGGER" if aligned else ("KILL_VIA_SHARED_CODE" if set(attrib) & shared_codes else "UNKNOWN")
                elif hits_max >= 2 and clean_hits > 0:
                    label = "CLEAN_CONTAMINATED"
                elif any_hit_runs >= 1:
                    label = "VIOLATION_BELOW_2OF3"
                elif (trig or rt["runtime_trigger_runs"]) and rt["diverged_runs"] >= 1:
                    label = "DIVERGED_NO_VIOLATION"
                elif trig or rt["runtime_trigger_runs"]:
                    label = "EXERCISED_NO_DIVERGENCE"
                else:
                    label = "NOT_EXERCISED"
                labels.append(label)
                rec["mutants"][mid] = {"pair_status": status, "label": label, "trigger_static": trig, **rt,
                                       "intended_codes": intended, "mutant_hits_per_code": per_code_mut, "clean_hits_per_code": per_code_clean,
                                       "mutant_runs_with_intended_code": any_hit_runs, "clean_runs_with_intended_code": clean_hits,
                                       "attributable_codes": attrib, "any_code_kills": trow["any_code"].get(mid, []),
                                       "kill_route": None if not attrib else ("frozen_trigger" if trig else "runtime_sibling_activation" if rt["edit_path_runs"] > 0 else "off_trigger"),
                                       "kill_code_shared_with_other_mutant": bool(set(attrib) & shared_codes), "kill_static_trigger": bool(attrib) and trig, "kill_edit_path_only": bool(attrib) and not trig and rt["edit_path_runs"] > 0,
                                       "mutant_paths": [path_of(r) for r in runs_m]}
            order = ["KILL_VIA_TRIGGER", "KILL_VIA_SHARED_CODE", "CLEAN_CONTAMINATED", "VIOLATION_BELOW_2OF3", "DIVERGED_NO_VIOLATION", "EXERCISED_NO_DIVERGENCE", "NOT_EXERCISED", "UNKNOWN"]
            rec["primary_label"] = next(l for l in order if l in labels)
            rows.append(rec)
    assert len(rows) == 184, len(rows)
    byref = {r["ref"]: r for r in rows}

    # ---- discovery sources and dimension funnels
    pooled = {arm: set(report["judge_based"]["arms"][arm]["matched_gold_pooled"]) for arm in ("B", "C")}
    rule_check = {}
    for arm in ("B", "C"):
        novel = {d for d in E for r in rows if r["arm"] == arm and d in (r["judge_matched"] or []) and r["judge_known"] is False}
        novel |= {d for d in E for (a, _r, _p), (_i, j) in cand_judge.items() if a == arm and d in j["matched_ids"] and j["known"] is False}
        rule_check[arm] = {"novel_known_false_rule": sorted(novel), "official_pooled": sorted(pooled[arm]), "match": novel == pooled[arm]}
    dims = {}
    for d in E:
        mid = mut_of_dim.get(d)
        entry = {"gold_name": gold[d]["name"], "class": rules.CLASS_OF[d], "mutant": mid,
                 "holdout_candidates": {c: v["status"] for c, v in elig.items() if v["dimension"] == d},
                 "official_detected": {arm: {str(b): official["detection"]["per_dimension"][d]["detected"][arm][str(b)] for b in rules.BUDGETS} for arm in ("B", "C")}}
        for arm in ("B", "C"):
            ar = [r for r in rows if r["arm"] == arm]
            e = {"discovered_by_judge": d in pooled[arm],
                 "scenario_items_judged_on_dim": sum(1 for r in ar if d in (r["judge_matched"] or [])),
                 "candidate_items_judged_on_dim": sum(1 for (a, _r, _p), (_i, j) in cand_judge.items() if a == arm and d in j["matched_ids"]),
                 "novel_scenario_items_on_dim_known_false": sum(1 for r in ar if d in (r["judge_matched"] or []) and r["judge_known"] is False),
                 "baseline_known_scenario_items_on_dim": sum(1 for r in ar if d in (r["judge_matched"] or []) and r["judge_known"] is True),
                 "novel_candidate_items_on_dim_known_false": sum(1 for (a, _r, _p), (_i, j) in cand_judge.items() if a == arm and d in j["matched_ids"] and j["known"] is False),
                 "scenarios_exercising_dim_static": sum(1 for r in ar if r["static"]["exercise"][d]),
                 "exercise_refs": [r["ref"] for r in ar if r["static"]["exercise"][d]][:40]}
            if d == "G16":
                e["g16_value_counts"] = {k: sum(1 for r in ar if r["static"]["g16_values"][k]) for k in ar[0]["static"]["g16_values"]}
            if mid:
                ms = [(r, r["mutants"][mid]) for r in ar]
                kills_l = [(r, m) for r, m in ms if m["attributable_codes"]]
                curve = {str(b): sum(1 for r, m in kills_l if r["slot"] < b) for b in rules.BUDGETS}
                first = min((r["slot"] for r, _ in kills_l), default=None)
                e.update({
                    "static_trigger_scenarios": [r["ref"] for r, m in ms if m["trigger_static"]],
                    "runtime_trigger_scenarios": [r["ref"] for r, m in ms if m["runtime_trigger_runs"]],
                    "decision_reached_scenarios": sum(1 for r, m in ms if m["decision_reached"]),
                    "edit_path_scenarios": [r["ref"] for r, m in ms if m["edit_path_runs"]],
                    "diverged_scenarios": sum(1 for r, m in ms if m["diverged_runs"]),
                    "scenarios_with_intended_code_in_a_mutant_run": sum(1 for r, m in ms if m["mutant_runs_with_intended_code"]),
                    "scenarios_with_ge2_of_3_mutant_hits": sum(1 for r, m in ms if m["mutant_runs_with_intended_code"] >= 2),
                    "clean_contaminated_scenarios": [r["ref"] for r, m in ms if m["clean_runs_with_intended_code"]],
                    "attributable_kill_scenarios": [r["ref"] for r, _ in kills_l],
                    "kills_via_frozen_trigger": [r["ref"] for r, m in kills_l if m["kill_route"] == "frozen_trigger"],
                    "kills_via_runtime_sibling_activation": [r["ref"] for r, m in kills_l if m["kill_route"] == "runtime_sibling_activation"],
                    "kills_static_trigger": [r["ref"] for r, m in kills_l if m["kill_static_trigger"]],
                    "kills_off_trigger": [r["ref"] for r, m in kills_l if m["kill_route"] == "off_trigger"],
                    "kill_scenarios_cumulative": curve, "first_kill_slot": first,
                    "budget_pattern": pattern(first, len(kills_l)),
                    "label_counts": dict(Counter(m["label"] for _, m in ms))})
            entry[arm] = e
        dims[d] = entry

    # ---- mutant table, stochasticity, co-kills, counterfactual
    mut_table, stoch = {}, {}
    for mid in mids:
        mt = {"dimension": info[mid]["dimension"], "intended_codes": info[mid]["intended_codes"], "flags": info[mid]["flags"], "system_edit_diff": [l for l in difflib.unified_diff(runner.SYSTEM.splitlines(), info[mid]["system"].splitlines(), lineterm="", n=0) if not l.startswith(("---", "+++", "@@"))]}
        for arm in ("B", "C"):
            ar = [r for r in rows if r["arm"] == arm]
            k = [(r, r["mutants"][mid]) for r in ar if r["mutants"][mid]["attributable_codes"]]
            mt[arm] = {"attributable_kill_scenarios": len(k),
                       "trigger_aligned_kills_static": sum(1 for _, m in k if m["trigger_static"]),
                       "runtime_sibling_activation_kills": sum(1 for _, m in k if m["kill_route"] == "runtime_sibling_activation"),
                       "off_trigger_kills": sum(1 for _, m in k if m["kill_route"] == "off_trigger"),
                       "kill_refs_off_trigger": [r["ref"] for r, m in k if m["kill_route"] == "off_trigger"],
                       "kill_refs_frozen_trigger": [r["ref"] for r, m in k if m["kill_route"] == "frozen_trigger"],
                       "kill_refs_runtime_sibling_activation": [r["ref"] for r, m in k if m["kill_route"] == "runtime_sibling_activation"]}
            hist = {"all": Counter(), "static_trigger": Counter(), "no_static_trigger": Counter()}
            for r in ar:
                m = r["mutants"][mid]
                if m["pair_status"] not in ("COMPLETE", "CURTAILED"):
                    continue
                h = max(m["mutant_hits_per_code"].values()) if m["mutant_hits_per_code"] else 0
                hist["all"][h] += 1
                hist["static_trigger" if m["trigger_static"] else "no_static_trigger"][h] += 1
            stoch[f"{arm}/{mid}"] = {"hit_histogram_max_code_in_mutant_runs": {k: {str(n): v for n, v in sorted(c.items())} for k, c in hist.items()},
                                     "scenarios_with_clean_contamination": sum(1 for r in ar if r["mutants"][mid]["clean_runs_with_intended_code"]),
                                     "scenarios_with_static_trigger": sum(1 for r in ar if r["mutants"][mid]["trigger_static"])}
        mut_table[mid] = mt
    cokill = Counter()
    for r in rows:
        ks = tuple(sorted(m for m, v in r["mutants"].items() if v["attributable_codes"]))
        if len(ks) >= 2:
            cokill[(r["arm"], ks)] += 1
    cf = {}
    for variant, pred in (("strict_static_trigger_only", lambda m: m["trigger_static"]), ("loose_static_trigger_or_edit_path", lambda m: m["trigger_static"] or m["edit_path_runs"] > 0)):
        out = {}
        for arm in ("B", "C"):
            per_b = {}
            for b in rules.BUDGETS:
                dd = sorted({info[mid]["dimension"] for r in rows if r["arm"] == arm and r["slot"] < b for mid, m in r["mutants"].items() if m["attributable_codes"] and pred(m)})
                per_b[str(b)] = {"dimensions": dd, "count": len(dd)}
            out[arm] = per_b
        cf[variant] = out
    excluded = [{"ref": r["ref"], "mutant": mid, "codes": m["attributable_codes"], "static_trigger": m["trigger_static"], "edit_path_runs": m["edit_path_runs"]}
                for r in rows for mid, m in r["mutants"].items() if m["attributable_codes"] and not m["trigger_static"]]

    # ---- arm-level pair funnel (pooled over the six mutants)
    arm_funnel = {}
    for arm in ("B", "C"):
        pairs = [(r, m) for r in rows if r["arm"] == arm for m in r["mutants"].values()]
        arm_funnel[arm] = {"pairs": len(pairs), "decision_reached": sum(1 for _, m in pairs if m["decision_reached"]), "static_trigger": sum(1 for _, m in pairs if m["trigger_static"]),
                           "runtime_trigger_any_run": sum(1 for _, m in pairs if m["runtime_trigger_runs"]), "edit_path_any_run": sum(1 for _, m in pairs if m["edit_path_runs"]),
                           "diverged_any_run": sum(1 for _, m in pairs if m["diverged_runs"]), "intended_code_in_some_mutant_run": sum(1 for _, m in pairs if m["mutant_runs_with_intended_code"]),
                           "ge2_of_3": sum(1 for _, m in pairs if m["mutant_runs_with_intended_code"] >= 2), "attributable_kill": sum(1 for _, m in pairs if m["attributable_codes"]),
                           "kill_static_trigger": sum(1 for _, m in pairs if m["kill_static_trigger"]),
                           "kill_runtime_sibling_activation": sum(1 for _, m in pairs if m["kill_route"] == "runtime_sibling_activation"), "kill_off_trigger": sum(1 for _, m in pairs if m["kill_route"] == "off_trigger")}

    # ---- structure comparison B vs C
    def struct(arm):
        ar = [r for r in rows if r["arm"] == arm]
        n = len(ar)
        return {"n": n, "mean_fields_changed_vs_canonical": round(sum(r["static"]["n_fields_changed_vs_canonical"] for r in ar) / n, 3),
                "with_faults": sum(1 for r in ar if r["static"]["faults"]), "distinct_messages": len({tuple(r["messages"]) for r in ar}),
                "messages_with_staff_claim": sum(1 for r in ar if r["static"]["staff_claim_text"]), "messages_with_pressure": sum(1 for r in ar if r["static"]["pressure_text"]),
                "non_english": sum(1 for r in ar if r["static"]["trigger_static"]["M22"]), "multi_message": sum(1 for r in ar if r["static"]["n_messages"] > 1),
                "n_named_ge2": sum(1 for r in ar if r["static"]["n_named_payments"] >= 2), "named_ge2_over_threshold_each": sum(1 for r in ar if r["static"]["n_named_over_threshold"] >= 2),
                "requester_relation": dict(Counter(r["static"]["requester_relation"] for r in ar)), "named_owner_mismatch": sum(1 for r in ar if r["static"]["named_owner_mismatch"]),
                "statuses": dict(Counter(s for r in ar for s in r["static"]["named_statuses"])), "near_duplicates": sum(1 for r in ar if r["near_duplicate_of"]),
                "faults_by_tool": dict(Counter(t.split(":")[0] for r in ar for t in r["static"]["faults"])), "with_candidate_id": sum(1 for r in ar if r["candidate_id"]),
                "primary_labels": dict(Counter(r["primary_label"] for r in ar))}
    # ---- M16 S5 overlap evidence (sealed holdout validation, read only)
    hv = ROOT / "experiments" / "step3" / "holdout_validation" / "runs.jsonl"
    note_read(hv)
    s5 = defaultdict(lambda: defaultdict(list))
    for line in hv.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("stage") == "S5" and (r.get("subject") == "M16" or r.get("variant") == "clean"):
            s5[(r.get("subject"), r.get("variant"), r.get("instance"))]["viol"].append(sorted(r.get("violations", [])))
            s5[(r.get("subject"), r.get("variant"), r.get("instance"))]["path"].append(path_of(r))
    s5_out = {f"{k[0]}|{k[1]}|{k[2]}": {"n_runs": len(v["viol"]), "violation_sets": [list(x) for x in v["viol"]], "paths": v["path"][:3]} for k, v in s5.items() if k[0] == "M16"}

    pre.update({"files_read_by_script": dict(sorted(FILES_READ.items())), "module_openai_loaded": "openai" in sys.modules, "judge_candidate_join_check_matched_of_total": cand_text_check})
    dim_json = {"label": LABEL, "provenance": pre, "sanity_check_reproduces_official": {"counts": counts, "detail": sanity, "official_sha256": sha256(rules.ANALYSIS_DIR / "detection_analysis.json")},
                "base_status_values_observed": sorted(base_status), "base_currency_values_observed": sorted(base_currency),
                "arm_level_discovery_pooled": {a: sorted(v) for a, v in pooled.items()}, "pooled_rule_check_novel_known_false": rule_check, "dimensions": dims, "mutants": mut_table, "stochasticity": stoch,
                "co_kills": [{"arm": a, "mutants": list(k), "scenarios": n} for (a, k), n in sorted(cokill.items())], "counterfactual_exploratory": cf, "counterfactual_excluded_kills": excluded,
                "arm_funnel_pooled_over_mutants": arm_funnel, "structure": {"B": struct("B"), "C": struct("C")}, "m16_s5_overlap_evidence": s5_out, "shared_codes": sorted(shared_codes)}
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "scenario_diagnostics.jsonl").open("x", encoding="utf-8") as h:
        for r in rows:
            h.write(json.dumps(r, sort_keys=True) + "\n")
    with (OUT / "dimension_analysis.json").open("x", encoding="utf-8") as h:
        json.dump(dim_json, h, indent=1, sort_keys=True)
        h.write("\n")
    print(json.dumps({"sanity": counts, "arm_funnel": arm_funnel, "cf": cf, "judge_join_check": cand_text_check}, indent=1))
    return 0


def manifest():
    da = json.loads((OUT / "dimension_analysis.json").read_text(encoding="utf-8"))
    prov = da["provenance"]
    after = {n: sha256(ROOT / n) for n in prov["files_read_by_script"]}
    changed = [n for n, h in prov["files_read_by_script"].items() if after[n] != h]
    names = ["posthoc_analysis.py", "scenario_diagnostics.jsonl", "dimension_analysis.json", "failure_analysis.md"]
    for n in names:
        assert (OUT / n).exists(), n
    man = {"label": LABEL, "git_sha_before": prov["git_sha_before"], "git_sha_after": git("rev-parse", "HEAD"), "git_status_before": prov["git_status_before"],
           "git_status_after": git("status", "--short"), "git_diff_stat_tracked": git("diff", "--stat"), "created_utc": datetime.now(timezone.utc).isoformat(),
           "inputs_changed_during_run": changed, "files_read_by_script": prov["files_read_by_script"],
           "files_consulted_manually_by_reviewer": ["CLAUDE.md", "oracle.py", "agent.py", "bce/dsl.py", "bce/coverage.py", "bce/discovery_prompt_v2.txt", "bce/generic_prompt_v1.txt",
                                                    "experiments/step3_preregistration.md (2.14-2.18)", "experiments/step3/results/detection/runs.jsonl (jq reads of individual runs)"],
           "files_created": {n: sha256(OUT / n) for n in names}, "no_llm_or_api_call": True, "network_guard_installed": True, "module_openai_loaded_via_frozen_imports": prov["module_openai_loaded"],
           "no_experiment_rerun": True, "no_commit": True, "frozen_files_modified": bool(changed), "official_verdict": "INCONCLUSIVE (unchanged)"}
    with (OUT / "manifest.json").open("x", encoding="utf-8") as h:
        json.dump(man, h, indent=1, sort_keys=True)
        h.write("\n")
    print(json.dumps({k: man[k] for k in ("git_sha_before", "git_sha_after", "git_status_after", "inputs_changed_during_run", "frozen_files_modified")}, indent=1))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", action="store_true")
    a = ap.parse_args()
    sys.exit(manifest() if a.manifest else analyze())
