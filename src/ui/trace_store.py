"""Read layer over data/traces/*.jsonl for the observability dashboard.

Append-only JSONL, one record per line, one file per local day (written by trace_log).
Everything is computed on read in plain Python — no DB, no offset index (single-developer
scale; see plan §6). A half-written final line is skipped, not fatal."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE_DIR = ROOT / "data" / "traces"


def _day_files() -> list:
    if not TRACE_DIR.exists():
        return []
    return sorted(TRACE_DIR.glob("*.jsonl"), reverse=True)  # newest day first


def _iter_records_newest_first():
    for f in _day_files():
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue  # skip a half-written / corrupt line (same discipline as salvage)


def summarize(rec: dict) -> dict:
    """Cheap projection for the trace list — never includes raw_output_text."""
    prov = rec.get("provenance", {}) or {}
    dist = prov.get("source_distribution", {}) or {}
    div = rec.get("diversify", {}) or {}
    val = rec.get("validate", {}) or {}
    patch = rec.get("patch", {}) or {}
    llm = rec.get("llm", {}) or {}
    total = sum(dist.values()) if dist else 0
    outcome = div.get("patch_injection_outcome")
    return {
        "trace_id": rec.get("trace_id"),
        "ts": rec.get("ts"),
        "query": rec.get("query", ""),
        "ok": rec.get("ok", True),
        "error": rec.get("error"),
        "wall_ms": rec.get("wall_ms"),
        "stop_reason": llm.get("stop_reason"),
        "change_count": patch.get("change_count"),
        "source_distribution": dist,
        "all_general": total > 0 and dist.get("general", 0) == total,
        "patch_injection_outcome": outcome,
        "patch_served": outcome in ("injected", "already_present"),
        "n_clamped": len(val.get("clamped_values", []) or []),
        "n_problems": len(val.get("problems", []) or []),
        "n_unmatched": len(prov.get("unmatched_citations", []) or []),
        "mixer_all_down": bool(prov.get("mixer_all_down", False)),
        "salvaged": (rec.get("extract") or {}).get("extraction_path") == "salvage",
        "sysex_ok": (rec.get("sysex") or {}).get("outcome") == "ok",
    }


def _matches(s: dict, filt: str) -> bool:
    return {
        "salvage": s["salvaged"],
        "no-patch": s["ok"] and not s["patch_served"] and s["patch_injection_outcome"] is not None,
        "clamped": s["n_clamped"] > 0,
        "all-general": s["all_general"],
        "hallucinated-cite": s["n_unmatched"] > 0,
        "sysex-fail": s["ok"] and not s["sysex_ok"],
        "error": not s["ok"],
    }.get(filt, True)


def iter_summaries(limit: int = 200, since: str | None = None,
                   filt: str | None = None) -> list:
    out = []
    for rec in _iter_records_newest_first():
        s = summarize(rec)
        if since and (s["ts"] or "") < since:
            continue
        if filt and not _matches(s, filt):
            continue
        out.append(s)
        if len(out) >= limit:
            break
    return out


def get(trace_id: str) -> dict | None:
    """Fetch one full record. The day-embedded id names exactly one file; fall back to a
    full scan if that file is absent."""
    if not trace_id:
        return None
    day = str(trace_id)[:8]
    primary = TRACE_DIR / f"{day}.jsonl"
    # only trust the day-embedded fast path for a well-formed 8-digit day (no traversal);
    # otherwise fall back to scanning the trace dir's own files.
    files = [primary] if (day.isdigit() and len(day) == 8 and primary.exists()) else _day_files()
    for path in files:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip() or trace_id not in line:
                    continue
                rec = json.loads(line)
                if rec.get("trace_id") == trace_id:
                    return rec
        except Exception:
            continue
    return None


def aggregate(window: int = 200) -> dict:
    """One-pass live rolling rates over the most recent `window` traces (powers /api/overview).
    Computed on read — no cache to invalidate."""
    summaries = iter_summaries(limit=window)
    n = len(summaries)
    ok = [s for s in summaries if s["ok"]]
    no = len(ok) or 1
    def rate(pred):
        return round(sum(1 for s in ok if pred(s)) / no, 3)
    cc = [s["change_count"] for s in ok if isinstance(s.get("change_count"), int)]
    w = [s["wall_ms"] for s in ok if s.get("wall_ms")]
    return {
        "n_traces": n,
        "n_ok": len(ok),
        "all_general_rate": rate(lambda s: s["all_general"]),
        "no_patch_served_rate": rate(lambda s: not s["patch_served"]
                                     and s["patch_injection_outcome"] is not None),
        "salvage_rate": rate(lambda s: s["salvaged"]),
        "clamp_rate": rate(lambda s: s["n_clamped"] > 0),
        "hallucinated_cite_rate": rate(lambda s: s["n_unmatched"] > 0),
        "sysex_fail_rate": rate(lambda s: not s["sysex_ok"]),
        "error_rate": round((n - len(ok)) / (n or 1), 3),
        "mean_change_count": round(sum(cc) / len(cc), 1) if cc else None,
        "mean_wall_ms": round(sum(w) / len(w)) if w else None,
    }
