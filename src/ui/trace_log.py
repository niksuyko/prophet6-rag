"""Append-only trace logging for the patch-generation pipeline (observability M0).

One trace = one JSON object = one line in ``data/traces/{YYYYMMDD}.jsonl`` — the same
single-contract JSONL idiom as ``chunks.jsonl`` / ``golden_set.jsonl``, inspectable with
``tail``/``jq`` and uncommitted (``data/`` is gitignored).

Tracing is **default-ON with failure isolation**: ``emit()`` never raises, so a trace-disk
problem can never turn a good patch into an error (D-032 fail-safe). Set ``P6_TRACE=0`` to
disable it for a clean deterministic eval run.

The trace id embeds its day (``{YYYYMMDD}-{HHMMSS}-{6hex}``) so a reader can open exactly
one day-file to fetch it.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE_DIR = ROOT / "data" / "traces"

# raw_output_text is capped so a runaway response can't bloat the log (see emit()).
RAW_CAP = 2048  # keep first + last RAW_CAP chars


def enabled() -> bool:
    return os.environ.get("P6_TRACE", "1") != "0"


def now_ts() -> str:
    """Timestamp in the same format as eval/results filenames (%Y%m%d-%H%M%S)."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def new_id(ts: str | None = None) -> str:
    """Day-embedded trace id, e.g. 20260618-142233-9f2a1c."""
    return f"{ts or now_ts()}-{os.urandom(3).hex()}"


def cap_raw(text: str) -> str:
    """Keep first + last RAW_CAP chars of a long LLM response, marking the elision."""
    if text is None:
        return ""
    if len(text) <= 2 * RAW_CAP:
        return text
    dropped = len(text) - 2 * RAW_CAP
    return f"{text[:RAW_CAP]}\n...[{dropped} chars elided]...\n{text[-RAW_CAP:]}"


def emit(record: dict) -> None:
    """Append one trace record as a JSON line. Never raises (fail-safe)."""
    if not enabled():
        return
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        day = str(record.get("trace_id") or now_ts())[:8]
        line = json.dumps(record, ensure_ascii=False, default=str)
        with (TRACE_DIR / f"{day}.jsonl").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except Exception as e:  # fail-safe: surface the type to stderr, never propagate
        sys.stderr.write(f"[trace] emit failed: {type(e).__name__}: {e}\n")
