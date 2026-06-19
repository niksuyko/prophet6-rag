"""Text -> Prophet-6 patch generation (decisions.md D-020).

Pipeline: retrieve corpus chunks for the sound description (production hybrid+div mode),
then ask the LLM for a JSON patch constrained to the front-panel schema in patch_schema.py.
Values are validated/clamped server-side before reaching the panel UI.

Grounding contract (looser than ask.py, by design): patch design is a creative task, so
the model may use general subtractive-synthesis practice — but every change must say WHERE
it came from: a chunk label (e.g. "Manual - Slop", "reddit:11hzzll") when a retrieved chunk
motivated it, or the literal string "general synthesis" otherwise. The UI surfaces this
distinction so corpus-grounded moves are visually separable from the model's own judgment.

Usage: python src/ui/generate_patch.py "fat juno-style brass"
"""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "retrieve"))
sys.path.insert(0, str(ROOT / "src" / "evaluate"))
import load_env  # noqa: E402,F401  (side effect: ANTHROPIC_API_KEY from .env)
from search import retrieve, _recipe_shaped, ACTION_WEIGHT, ACTION_FLOOR  # noqa: E402

import trace_log  # noqa: E402  (observability M0; appends data/traces/*.jsonl)
from patch_schema import INIT_PATCH, PARAMS, schema_for_prompt, validate_changes  # noqa: E402

try:  # canonical source classifier (provenance_probe); tracing is best-effort
    from provenance_probe import classify as _classify_source  # noqa: E402
except Exception:  # pragma: no cover — fall back so a trace import can never break generation
    def _classify_source(source: str) -> str:
        s = (source or "").lower()
        for tag in ("patch", "manual", "reddit", "article", "video", "translation",
                    "official_kb"):
            if s.startswith(tag):
                return tag
        return "general"

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096      # recorded in each trace as a tunable lever
TEMPERATURE = 0.4      # recorded in each trace as a tunable lever

SYSTEM = """You are a Sequential Prophet-6 sound designer. Given a sound description and
context chunks retrieved from a Prophet-6 knowledge corpus (official manual + community
threads), you program a patch starting from the INIT state.

Rules:
1. Output ONLY a JSON object, no markdown fences, no prose outside it:
   {
     "patch_name": "<short evocative name>",
     "summary": "<2-3 sentences: the sound-design idea behind the patch>",
     "changes": [
       {"param": "<schema id>", "value": <number|string|boolean>,
        "why": "<one sentence: what this move contributes to the requested sound>",
        "source": "<chunk label like 'Manual - Slop' or 'reddit:abc123' if a retrieved
                    chunk motivated this setting, else exactly 'general synthesis'>"}
     ],
     "playing_tip": "<one sentence on how to play/perform it, or ''>"
   }
2. List ONLY parameters that differ from INIT. Every change must use an exact schema id
   and respect its range/options.
3. Prefer settings supported by the context chunks; cite their labels in "source". When
   REAL PATCH examples are provided, adapt from them where they fit the request and cite
   "patch:<id>" for every setting taken or adapted from one. Use "general synthesis"
   honestly for everything else — do not fake citations.
4. Make a complete, playable patch: if nothing would make sound (mixer all down) or the
   amp envelope contradicts the request, fix it. Remember interactions noted in the hints
   (e.g. glide needs both the switch on and rate > 0; pulse width is only audible on pulse
   shapes; effects need fx.on plus a mix above 0).
5. Aim for 10-25 changes — enough to fully realize the sound, no gratuitous moves."""


def chunk_label(c: dict) -> str:
    if c["source_type"] == "manual":
        return f"Manual - {c['section']}"
    if c["source_type"] == "reddit":
        return f"reddit:{c['source_id']}"
    return f"{c['source_type']}:{c['source_id']}"


def _nondefault(params: dict) -> dict:
    from patch_schema import INIT_PATCH
    return {k: v for k, v in params.items() if v != INIT_PATCH[k]}


def real_patch_block(chunks: list[dict], max_patches: int = 3,
                     trace: dict | None = None) -> str:
    """Full structured params for retrieved patch chunks (v2 D-024 retrieve-and-adapt),
    plus one parameter-space neighbor of the best hit for breadth. Pass `trace` to record
    which exemplars were loaded and how the neighbor expansion fared (observability)."""
    import json as _json
    patch_dir = ROOT / "data" / "patches"
    ids = [c["source_id"] for c in chunks if c["source_type"] == "patch"][:max_patches]
    entries, missing = [], []
    for pid in ids:
        p = patch_dir / f"{pid}.json"
        if p.exists():
            entries.append(_json.loads(p.read_text(encoding="utf-8")))
        else:
            missing.append(pid)
    neighbor_outcome, neighbor_distance = "no_entries", None
    if entries:
        neighbor_outcome = "no_neighbor"
        try:
            sys.path.insert(0, str(ROOT / "src" / "patches"))
            from similar import similar_patches
            for n in similar_patches(entries[0]["params"], k=1,
                                     exclude_id=entries[0]["id"]):
                if n["id"] not in {e["id"] for e in entries}:
                    entries.append({"id": n["id"], "name": n["name"],
                                    "params": n["params"]})
                    neighbor_distance = round(n["distance"], 3)
                    neighbor_outcome = "ok"
        except Exception as e:
            neighbor_outcome = f"Exception:{type(e).__name__}"  # was: pass (best-effort)
    if not entries:
        block = ""
    else:
        parts = ["These are REAL Prophet-6 patches (factory/official banks) retrieved for "
                 "this request — settings shown as deviations from INIT. Adapt from them "
                 "when relevant; cite as patch:<id>."]
        for e in entries:
            parts.append(f"<patch id=\"{e['id']}\" name=\"{e['name']}\">\n"
                         f"{_json.dumps(_nondefault(e['params']))}\n</patch>")
        block = "\n\n".join(parts)
    if trace is not None:
        trace["adapt"] = {"patch_ids_selected": ids, "patch_files_missing": missing,
                          "neighbor_outcome": neighbor_outcome,
                          "neighbor_distance": neighbor_distance,
                          "num_patch_exemplars": len(entries),
                          "block_char_len": len(block)}
    return block


def build_context(chunks: list[dict]) -> str:
    return "\n\n".join(
        f"<chunk label=\"{chunk_label(c)}\">\n{c['text']}\n</chunk>" for c in chunks)


def _salvage_truncated(text: str) -> dict:
    """Recover a patch from output cut off mid-JSON (e.g. max_tokens hit): keep the name and
    every COMPLETE change object, drop the truncated tail. Fail-safe over fail-total (D-032)."""
    name = (re.search(r'"patch_name"\s*:\s*"([^"]*)"', text) or [None, "Untitled"])[1]
    summary = (re.search(r'"summary"\s*:\s*"([^"]*)"', text) or [None, ""])[1]
    arr = text[text.find('"changes"'):] if '"changes"' in text else ""
    changes = []
    for obj in re.findall(r"\{[^{}]*\}", arr):  # change objects are flat (no nesting)
        try:
            o = json.loads(obj)
        except json.JSONDecodeError:
            continue
        if "param" in o:
            changes.append(o)
    return {"patch_name": name, "summary": summary, "changes": changes, "playing_tip": ""}


def _extract_json(text: str, meta: dict | None = None) -> dict:
    """Parse the model's JSON, tolerating stray fences/prose, and salvaging truncated output.
    Pass `meta` to record which parse path was taken (observability) — the returned dict is
    identical regardless."""
    info = {"extraction_path": None, "had_markdown_fences": False,
            "salvaged_change_count": 0, "raw_parse_error": None}

    def _done(d: dict, path: str) -> dict:
        info["extraction_path"] = path
        if path == "salvage":
            info["salvaged_change_count"] = len(d.get("changes", []))
        if meta is not None:
            meta.update(info)
        return d

    text = text.strip()
    if text.startswith("```"):
        info["had_markdown_fences"] = True
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return _done(json.loads(text), "json.loads")
    except json.JSONDecodeError as e:
        info["raw_parse_error"] = str(e)
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                return _done(json.loads(m.group(0)), "regex_object")
            except json.JSONDecodeError:
                pass
        return _done(_salvage_truncated(text), "salvage")


def generate_patch(query: str, mode: str = "patch+div", k: int = 8,
                   model: str = DEFAULT_MODEL, grounding: str = "adapt",
                   trace_sink: dict | None = None) -> dict:
    """grounding='adapt' (production, D-024): retrieved patch chunks contribute their
    full structured params and the model adapts real patches. grounding='pure': v1
    behavior (text chunks only) — kept for the measured A/B.

    trace_sink: if given, the observability record is written into this dict instead of
    emitted here, so the caller can emit it outside the generation lock. The public return
    is unchanged either way, so eval callers (provenance_probe, patch_quality, …) are
    unaffected."""
    import anthropic
    t0 = time.time()
    search_trace: dict = {}
    chunks = retrieve(query, k, mode=mode, trace=search_trace)
    adapt_meta: dict = {}
    patch_block = real_patch_block(chunks, trace=adapt_meta) if grounding == "adapt" else ""
    user = (f"Parameter schema (the only valid ids/ranges):\n\n{schema_for_prompt()}\n\n"
            + (f"{patch_block}\n\n" if patch_block else "")
            + f"Context chunks:\n\n{build_context(chunks)}\n\n"
            f"Sound description: {query}")
    client = anthropic.Anthropic()
    msg = client.messages.create(model=model, max_tokens=MAX_TOKENS, temperature=TEMPERATURE,
                                 system=SYSTEM,
                                 messages=[{"role": "user", "content": user}])
    raw_text = msg.content[0].text
    extract_meta: dict = {}
    raw = _extract_json(raw_text, meta=extract_meta)
    val_meta: dict = {}
    changes, problems = validate_changes(raw.get("changes", []), meta=val_meta)
    patch_name = str(raw.get("patch_name", "Untitled"))
    resolved = {**INIT_PATCH, **{c["param"]: c["value"] for c in changes}}
    sysex_meta: dict = {}
    result = {
        "query": query,
        "patch_name": patch_name,
        "summary": str(raw.get("summary", "")),
        "playing_tip": str(raw.get("playing_tip", "")),
        "changes": changes,
        "problems": problems,
        "grounding": grounding,
        "retrieved": [{"label": chunk_label(c), "url": c["source_url"]} for c in chunks],
        "init": INIT_PATCH,
        # MIDI-out (D-030): edit-buffer sysex of the resolved patch; client sends it
        # when the MIDI toggle is on. Computed here so the browser stays a dumb pipe.
        "sysex": _sysex_for(resolved, patch_name, meta=sysex_meta),
    }
    # Observability (M0): build a per-request trace. If a trace_sink dict was passed (by the
    # server), populate it so the caller emits OUTSIDE the generation lock; otherwise emit
    # here (gated by P6_TRACE). Failure-isolated — never blocks the patch.
    record = _build_trace(query=query, mode=mode, k=k, grounding=grounding, model=model,
                          chunks=chunks, raw=raw, raw_text=raw_text, changes=changes,
                          problems=problems, resolved=resolved, patch_name=patch_name,
                          summary=result["summary"], user_prompt=user, msg=msg,
                          search_trace=search_trace, adapt_meta=adapt_meta,
                          extract_meta=extract_meta, val_meta=val_meta, sysex_meta=sysex_meta,
                          wall_ms=int((time.time() - t0) * 1000))
    if record:
        if trace_sink is not None:
            trace_sink.update(record)
        else:
            trace_log.emit(record)
    return result


def _build_trace(*, query, mode, k, grounding, model, chunks, raw, raw_text, changes,
                 problems, resolved, patch_name, summary, user_prompt, msg, search_trace,
                 adapt_meta, extract_meta, val_meta, sysex_meta, wall_ms) -> dict:
    """Assemble the full per-request observability record (plan §2.2). Returns {} on any
    failure so tracing can never break a generated patch."""
    try:
        chunk_labels = [chunk_label(c) for c in chunks]
        final_chunks = [{"chunk_id": c.get("chunk_id"), "source_type": c["source_type"],
                         "source_id": c.get("source_id"), "section": c.get("section"),
                         "label": chunk_label(c)} for c in chunks]
        nondefault = {pid: v for pid, v in resolved.items() if v != INIT_PATCH.get(pid)}
        source_dist: dict = {}
        for c in changes:
            b = _classify_source(c.get("source", ""))
            source_dist[b] = source_dist.get(b, 0) + 1
        clean_params = {c["param"] for c in changes}
        proposed = [c.get("param") for c in raw.get("changes", []) if isinstance(c, dict)]
        narrated_not_delivered = list(dict.fromkeys(
            p for p in proposed if p and p in PARAMS and p not in clean_params))
        mixer_all_down = all(resolved.get(m, 0) == 0 for m in
                             ("mixer.osc1", "mixer.osc2", "mixer.sub_octave", "mixer.noise"))
        # unmatched citations — gated on the loaded patch ids (plan §2.4) to avoid flagging
        # legitimate patch:<id> citations as hallucinations.
        patch_ids = adapt_meta.get("patch_ids_selected", [])
        allow = set(chunk_labels) | {f"patch:{pid}" for pid in patch_ids} | {"general synthesis"}
        unmatched = list(dict.fromkeys(
            c["source"] for c in changes if c.get("source") and c["source"] not in allow))
        usage = getattr(msg, "usage", None)
        ts = trace_log.now_ts()
        return {
            "trace_id": trace_log.new_id(ts), "ts": ts,
            "query": query, "mode": mode, "k": k, "grounding": grounding,
            "model": model, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
            "rrf_k": 60, "action_weight": ACTION_WEIGHT, "action_floor": ACTION_FLOOR,
            "wall_ms": wall_ms, "ok": True,
            "classify": {"recipe_shaped": bool(_recipe_shaped(query)),
                         "matched_alternation_branch": None, "path_uses_result": False},
            "pool": search_trace.get("pool", {}),
            "rerank": search_trace.get("rerank", {}),
            "diversify": search_trace.get("diversify", {}),
            "final_chunks": final_chunks,
            "adapt": adapt_meta,
            "prompt": {"chunk_labels_in_prompt": chunk_labels,
                       "num_context_chunks": len(chunks), "schema_present": True,
                       "prompt_total_chars": len(user_prompt),
                       "est_input_tokens": len(user_prompt) // 4},
            "llm": {"stop_reason": getattr(msg, "stop_reason", None),
                    "usage_output_tokens": getattr(usage, "output_tokens", None),
                    "request_id": getattr(msg, "id", None),
                    "model_returned": getattr(msg, "model", None),
                    "api_exception": None,
                    "raw_output_text": trace_log.cap_raw(raw_text)},
            "extract": extract_meta,
            "validate": {"input_change_count": len(raw.get("changes", [])),
                         "clean_change_count": len(changes), "problems": problems,
                         **val_meta},
            "patch": {"patch_name": patch_name, "summary": summary, "changes": changes,
                      "resolved_nondefault": nondefault, "change_count": len(changes),
                      "narrated_not_delivered": narrated_not_delivered},
            "provenance": {"source_distribution": source_dist,
                           "unmatched_citations": unmatched, "mixer_all_down": mixer_all_down},
            "sysex": sysex_meta,
        }
    except Exception as e:  # fail-safe: tracing must never break generation
        sys.stderr.write(f"[trace] build failed: {type(e).__name__}: {e}\n")
        return {}


def _sysex_for(resolved: dict, name: str, meta: dict | None = None) -> list | None:
    try:
        sys.path.insert(0, str(ROOT / "src" / "patches"))
        from encode_sysex import encode_edit_buffer
        out = encode_edit_buffer(resolved, name)
        if meta is not None:
            try:
                from decode_sysex import NAME_LEN
                truncated = len((name or "").encode("ascii", "replace")) > NAME_LEN
            except Exception:
                truncated = False
            meta.update({"outcome": "ok", "name_truncated": truncated, "value_fallbacks": []})
        return out
    except Exception as e:
        if meta is not None:  # surface the previously-silent encode failure (ISSUE-2)
            meta.update({"outcome": f"Exception:{type(e).__name__}: {e}",
                         "name_truncated": False, "value_fallbacks": []})
        return None  # MIDI is a bonus; never let encoding break generation


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "warm Juno-style chorus pad"
    print(json.dumps(generate_patch(q), indent=2))
