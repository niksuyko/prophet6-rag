"""Corpus-health + golden-set read layer for the dashboard (M4).

Reads the indexed corpus (data/index/chunks.meta.jsonl) and the golden sets. The 25k-chunk
parse is memoized by file mtime — the only place this dashboard touches a large file, and
only when the Corpus/Golden views are opened (plan §6). Nothing here writes, except the
explicit, user-confirmed promote() append to golden_set_v2.jsonl (D-015 ratification).
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHUNKS_META = ROOT / "data" / "index" / "chunks.meta.jsonl"
INDEX_META = ROOT / "data" / "index" / "index_meta.json"
COVERAGE = ROOT / "eval" / "results" / "coverage_report.json"
PATCH_DIR = ROOT / "data" / "patches"
GOLDEN_FILES = [ROOT / "eval" / "golden_set.jsonl", ROOT / "eval" / "golden_set_v2.jsonl"]
GOLDEN_V2 = GOLDEN_FILES[1]

_cache = {"mtime": None, "data": None}


def _load() -> dict:
    """Memoized chunk index: id→type map, source-id set, manual-section blob (for the gate)."""
    if not CHUNKS_META.exists():
        raise ValueError("index not built — data/index/chunks.meta.jsonl is missing")
    mt = CHUNKS_META.stat().st_mtime
    if _cache["mtime"] == mt:
        return _cache["data"]
    by_type, id_to_type, source_ids, manual_sections = {}, {}, set(), []
    with CHUNKS_META.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError:
                continue  # skip a half-written / corrupt line (same discipline as trace_store)
            st = c.get("source_type")
            by_type[st] = by_type.get(st, 0) + 1
            if c.get("chunk_id"):
                id_to_type[c["chunk_id"]] = st
            if c.get("source_id"):
                source_ids.add(c["source_id"])
            if st == "manual" and c.get("section"):
                manual_sections.append(c["section"].lower())
    data = {"n": len(id_to_type), "by_type": by_type, "id_to_type": id_to_type,
            "source_ids": source_ids, "manual_sections": " || ".join(manual_sections)}
    _cache.update(mtime=mt, data=data)
    return data


def _retrieval_freq() -> Counter:
    """How often each chunk_id appears in any recall run's top_chunks (golden-query traffic)."""
    import eval_store
    freq: Counter = Counter()
    for r in eval_store.list_runs("recall"):
        try:
            d = eval_store.load_run(r["file"])
        except Exception:
            continue
        for q in d.get("per_query", []):
            for cid in q.get("top_chunks", []):
                freq[cid] += 1
    return freq


def _coverage() -> dict:
    if not COVERAGE.exists():
        return {}
    d = json.loads(COVERAGE.read_text(encoding="utf-8"))
    cells = d.get("cells", {})
    families, characters = [], []
    for key in cells:
        fam, _, ch = key.partition("|")
        if fam not in families:
            families.append(fam)
        if ch not in characters:
            characters.append(ch)
    gaps = sorted(([k, v] for k, v in cells.items() if v < 3), key=lambda kv: kv[1])
    return {"cells": cells, "families": families, "characters": sorted(characters),
            "pct_cells_3plus": d.get("pct_cells_3plus"), "threshold": 3,
            "gaps": gaps, "fixed_filename": True}


def corpus_health() -> dict:
    data = _load()
    freq = _retrieval_freq()
    id2t = data["id_to_type"]
    served: dict = {}
    for cid in freq:
        served[id2t.get(cid) or "unknown"] = served.get(id2t.get(cid) or "unknown", 0) + 1
    top = [{"chunk_id": cid, "freq": n, "source_type": id2t.get(cid) or "unknown"}
           for cid, n in freq.most_common(15)]
    retrieved = len(freq)
    return {
        "n_chunks": data["n"],
        "model": json.loads(INDEX_META.read_text()).get("model") if INDEX_META.exists() else None,
        "by_source_type": dict(sorted(data["by_type"].items(), key=lambda kv: -kv[1])),
        "retrieval": {
            "distinct_chunks_retrieved": retrieved,
            "served_by_source_type": dict(sorted(served.items(), key=lambda kv: -kv[1])),
            "top_chunks": top,
            "n_recall_runs": len(__import__("eval_store").list_runs("recall")),
        },
        "dead": {
            "never_retrieved": data["n"] - retrieved,
            "note": "Counts chunks never served to any golden query (a small probe set), so a "
                    "high number is expected — read it per-source to spot lanes that never "
                    "surface, not as individual dead chunks.",
        },
        "coverage": _coverage(),
    }


def _read_golden(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # skip a half-written / corrupt line (e.g. a killed promote append)
    return out


def golden_records() -> list:
    recs = []
    for path in GOLDEN_FILES:
        for g in _read_golden(path):
            recs.append({"id": g.get("id"), "query": g.get("query"), "bucket": g.get("bucket"),
                         "expected_targets": g.get("expected_targets"),
                         "param_targets": g.get("param_targets"),
                         "phrasing": g.get("phrasing"), "notes": g.get("notes"),
                         "file": path.name})
    return recs


def golden_gate() -> dict:
    """Replicates check_targets.py against the indexed corpus: every entry must have a
    reachable target (D-005/D-015)."""
    data = _load()
    ids, sections = data["source_ids"], data["manual_sections"]
    unreachable, partial, missing_patch, total = [], [], [], 0
    for path in GOLDEN_FILES:
        for g in _read_golden(path):
            total += 1
            reach = [(str(t.get("match") or "").lower() in sections) if t.get("source_type") == "manual"
                     else (t.get("match") in ids) for t in g.get("expected_targets", [])]
            if g.get("expected_targets") and not any(reach):
                unreachable.append({"id": g.get("id"), "file": path.name,
                                    "targets": g.get("expected_targets")})
            elif g.get("expected_targets") and not all(reach):
                partial.append(g.get("id"))
            for pid in g.get("param_targets", []):
                if not (PATCH_DIR / f"{pid}.json").exists():
                    missing_patch.append({"id": g.get("id"), "patch": pid})
    return {"ok": not unreachable and not missing_patch, "total": total,
            "unreachable": unreachable, "partial": partial, "missing_patch": missing_patch}


def promote(record: dict) -> dict:
    """Append a user-ratified golden entry to golden_set_v2.jsonl (D-015). Validates shape and
    rejects duplicate ids; the caller is expected to have shown the draft for confirmation."""
    rid = record.get("id")
    if not rid or not isinstance(rid, str):
        raise ValueError("record needs a string 'id'")
    if not record.get("query"):
        raise ValueError("record needs a 'query'")
    if not isinstance(record.get("bucket"), int):
        raise ValueError("record needs an integer 'bucket'")
    tgts = record.get("expected_targets")
    if not isinstance(tgts, list) or not all(
            isinstance(t, dict) and t.get("source_type") and isinstance(t.get("match"), str)
            and t.get("match") for t in tgts):
        raise ValueError("expected_targets must be a list of {source_type, match:str}")
    existing = {g.get("id") for g in _read_golden(GOLDEN_V2)}
    if rid in existing:
        raise ValueError(f"id {rid!r} already in golden_set_v2.jsonl")
    line = json.dumps(record, ensure_ascii=False)
    with GOLDEN_V2.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return {"ok": True, "id": rid, "gate": golden_gate(),
            "note": "Appended. Re-run check_targets.py to confirm integrity (D-015)."}
