"""Read layer over eval/results/*.json for the dashboard (Overview + Run-Diff).

eval/results is read-only ground truth — the dashboard never writes there. Result files
are self-describing ({run, timestamp, mode/model/k, summary scalars, per_bucket, per_query})
and named {ts}_{kind}_{label}.json (coverage_report.json is the one fixed-name exception).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = (ROOT / "eval" / "results").resolve()

# longest-first so 'patch_quality_run' wins over 'patch' etc.
KINDS = ["patch_quality_selftest", "patch_quality_run", "patch_accuracy", "patch_ab",
         "recall", "provenance", "bakeoff", "faithfulness", "coverage"]

# kinds whose headline number is assistant-judged or carries a known artifact (D-019/D-021).
PROVISIONAL = {"bakeoff", "faithfulness", "patch_ab", "patch_quality_run"}


def _parse_name(fn: str):
    stem = fn[:-5] if fn.endswith(".json") else fn
    m = re.match(r"(\d{8}-\d{6})_(.+)", stem)
    ts, rest = (m.group(1), m.group(2)) if m else (None, stem)
    kind = next((k for k in KINDS if rest.startswith(k)), rest.split("_")[0])
    label = rest[len(kind):].lstrip("_") or kind
    return ts, kind, label


def list_runs(kind: str | None = None) -> list:
    out = []
    if not RESULTS.exists():
        return out
    for f in RESULTS.glob("*.json"):
        ts, k, label = _parse_name(f.name)
        if kind and k != kind:
            continue
        out.append({"file": f.name, "ts": ts, "kind": k, "label": label})
    out.sort(key=lambda r: (r["ts"] or ""), reverse=True)
    return out


def load_run(file: str) -> dict:
    """Load one result file, path-validated to eval/results (no traversal)."""
    p = (RESULTS / file).resolve()
    if p.parent != RESULTS or p.suffix != ".json" or not p.exists():
        raise ValueError(f"invalid result file: {file!r}")
    return json.loads(p.read_text(encoding="utf-8"))


# --- headline-scalar extraction per kind: (metric, value, fmt, target, direction) ---
def _scalar(d: dict, kind: str):
    if kind == "recall":
        return ("recall@5", d.get("overall_recall"), "ratio", 0.95, "high")
    if kind == "coverage":
        return ("coverage ≥3 src", d.get("pct_cells_3plus"), "ratio", 0.90, "high")
    if kind == "provenance":
        return ("provenance cited", d.get("cited_ratio"), "ratio", 0.50, "high")
    if kind == "patch_accuracy":
        return ("patch agreement", d.get("mean_active_agreement"), "ratio", None, "high")
    if kind == "faithfulness":
        return ("faithfulness", d.get("overall_faithful_pct"), "pct100", 80.0, "high")
    if kind == "patch_ab":
        return ("A/B judge", d.get("judge_mean"), "raw", None, "high")
    if kind == "bakeoff":
        t = d.get("totals") or {}
        tot = sum(t.values()) or 1
        return ("bake-off RAG win", round(t.get("rag", 0) / tot, 3), "ratio", 0.50, "high")
    return (kind, None, "raw", None, "high")


CAVEAT = {
    "recall": "D-029: a MISS may be an eval-staleness collision — open the per-query drill before reading it as a regression.",
    "coverage": "Fixed-filename report (coverage_report.json) — no trend history until the writer timestamps its output.",
    "patch_accuracy": "Bucket-5 probes only (reference patches exist); buckets 2/3 have no ground-truth reference.",
    "faithfulness": "Assistant-judged — mandatory spot-check; pending contradicted claims (D-019/D-021).",
    "patch_ab": "Citation-stripper artifact (~10 wrong-basis verdicts) flagged — not a ratified number (D-014/D-019).",
    "bakeoff": "Assistant-judged head-to-head — spot-check; B2 judge artifact flagged (D-021).",
}


def summarize(d: dict, kind: str) -> dict:
    metric, value, fmt, target, direction = _scalar(d, kind)
    return {
        "kind": kind, "metric": metric, "value": value, "fmt": fmt,
        "target": target, "direction": direction,
        "provisional": kind in PROVISIONAL, "caveat": CAVEAT.get(kind),
        "run": d.get("run") or d.get("label"), "ts": d.get("timestamp"),
        "extra": {k: d.get(k) for k in ("mode", "model", "k", "n_queries", "totals")
                  if d.get(k) is not None},
    }


def _pq_value(kind: str, q: dict):
    if kind == "recall":
        return 1.0 if q.get("hit") else 0.0
    if kind == "patch_accuracy":
        return (q.get("overall") or {}).get("pct")
    return None


def _pq_detail(kind: str, q: dict) -> dict:
    if kind == "recall":
        return {"matched": q.get("matched"), "top_chunks": q.get("top_chunks")}
    if kind == "patch_accuracy":
        return {"pct": (q.get("overall") or {}).get("pct"),
                "by_group": (q.get("overall") or {}).get("by_group")}
    return {}


def _bucket_value(b: dict):
    if not isinstance(b, dict):
        return None
    for key in ("recall", "pct", "faithful_pct"):
        if key in b:
            return b[key]
    return None


def diff(file_a: str, file_b: str) -> dict:
    """Per-bucket + per-query delta between two same-kind runs. Powers the Run-Diff view —
    the per-query list is where a HIT→MISS regression and its displacing chunk surface."""
    da, db = load_run(file_a), load_run(file_b)
    ka, kb = _parse_name(file_a)[1], _parse_name(file_b)[1]
    if ka != kb:
        raise ValueError(f"runs are different kinds ({ka} vs {kb}); diff needs matching kinds")
    kind = ka
    _, va, fmt, target, direction = _scalar(da, kind)
    metric, vb, _, _, _ = _scalar(db, kind)

    ba, bb = da.get("per_bucket") or {}, db.get("per_bucket") or {}
    buckets = []
    for key in sorted(set(ba) | set(bb)):
        av, bv = _bucket_value(ba.get(key, {})), _bucket_value(bb.get(key, {}))
        buckets.append({"bucket": key, "a": av, "b": bv,
                        "delta": round(bv - av, 3) if av is not None and bv is not None else None})

    qa = {q["id"]: q for q in da.get("per_query", []) if "id" in q}
    qb = {q["id"]: q for q in db.get("per_query", []) if "id" in q}
    common = sorted(set(qa) & set(qb))
    regressed, improved = [], []
    for qid in common:
        av, bv = _pq_value(kind, qa[qid]), _pq_value(kind, qb[qid])
        if av is None or bv is None:
            continue
        if bv < av - 1e-9:
            regressed.append({"id": qid, "bucket": qa[qid].get("bucket"), "a": av, "b": bv,
                              "detail_a": _pq_detail(kind, qa[qid]),
                              "detail_b": _pq_detail(kind, qb[qid])})
        elif bv > av + 1e-9:
            improved.append({"id": qid, "bucket": qb[qid].get("bucket"), "a": av, "b": bv,
                             "detail_a": _pq_detail(kind, qa[qid]),
                             "detail_b": _pq_detail(kind, qb[qid])})

    tripwire = None
    if kind == "recall":
        tripwire = {"target": 0.95, "value": vb, "pass": vb is not None and vb >= 0.95,
                    "note": "D-029: a MISS may be an eval-staleness collision — inspect the "
                            "displaced top_chunks before treating it as a real regression; "
                            "never re-target a golden entry mid-run (D-015)."}
    return {
        "kind": kind, "metric": metric, "fmt": fmt, "target": target, "direction": direction,
        "a": {"file": file_a, "ts": da.get("timestamp"), "label": da.get("run") or da.get("label"), "value": va},
        "b": {"file": file_b, "ts": db.get("timestamp"), "label": db.get("run") or db.get("label"), "value": vb},
        "delta": round(vb - va, 4) if va is not None and vb is not None else None,
        "per_bucket": buckets, "regressed": regressed, "improved": improved,
        "n_common": len(common), "tripwire": tripwire,
    }


# kinds shown as headline KPI tiles on the Overview, in display order.
OVERVIEW_KINDS = ["recall", "coverage", "provenance", "patch_accuracy", "faithfulness", "bakeoff"]


def overview() -> dict:
    import trace_store
    runs = list_runs()
    latest_by_kind = {}
    for r in runs:  # runs already newest-first
        latest_by_kind.setdefault(r["kind"], r)
    kpis = []
    for kind in OVERVIEW_KINDS:
        r = latest_by_kind.get(kind)
        if not r:
            continue
        try:
            kpis.append({**summarize(load_run(r["file"]), kind), "file": r["file"]})
        except Exception:
            continue
    # recall trend (latest 20, oldest→newest) for the sparkline
    history = []
    for r in sorted(list_runs("recall"), key=lambda x: x["ts"] or "")[-20:]:
        try:
            v = load_run(r["file"]).get("overall_recall")
            if v is not None:
                history.append({"ts": r["ts"], "value": v, "label": r["label"]})
        except Exception:
            continue
    return {"live": trace_store.aggregate(), "eval": kpis, "recall_history": history}
