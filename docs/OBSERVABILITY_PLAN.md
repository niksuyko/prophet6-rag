# Prophet-6 RAG Observability Dashboard — Implementation Plan

## 1. Framing

**Goal.** A single-developer, local diagnostic surface that answers one question end-to-end: *why is this generated patch wrong, and which lever do I pull to fix it?* Patch accuracy is the product; everything here exists to make accuracy debuggable and to make regressions visible.

**Attribution principle.** Every generated patch flows through four stages, and every defect attributes to exactly one of them:

| Stage | Code locus | When it's the culprit | Lever |
|---|---|---|---|
| **retrieve** | `search.py` (`stratified_hybrid_search` → `_actionability` rerank → `dedupe_by_source` → `_diversify_actionable`) | the right chunk never reached the prompt | **corpus** (acquire/re-chunk) or **retrieval mode** (`ACTION_FLOOR`, `ACTION_WEIGHT`, RRF `k`, lane stratification) |
| **ground** | `generate_patch.real_patch_block` (`:73-104`) | a patch chunk was retrieved but no exemplar loaded | **corpus** (patch JSON integrity) or **retrieval mode** |
| **constrain** | the `SYSTEM` prompt + `schema_for_prompt()` | the model emitted a bad/under-grounded/truncated patch | **system prompt** |
| **validate** | `patch_schema.validate_changes` (`:296-331`) | a requested move was clamped/dropped/coerced silently | **system prompt** (range/vocab guidance) or schema text |

Every metric in this plan terminates in one of four levers: **corpus**, **retrieval mode**, **system prompt**, **golden set**.

**Ethos / explicit non-recommendations.** The existing stack is stdlib `http.server` on `127.0.0.1:8765`, a NumPy dot-product vector store, and vanilla static HTML/CSS/JS — chosen (D-001/D-009/D-010/D-020) for "no extra infrastructure, debuggable by printing." This dashboard extends that exactly:

- **Do NOT use LangChain / LlamaIndex / any RAG framework.** Nothing in the pipeline needs an orchestration abstraction; the file contracts already are the orchestration.
- **No Flask/FastAPI/React/Chart.js/D3, no build step, no npm, no SaaS telemetry (Datadog/Grafana).**
- **The only new persistence** is an *optional, light, local trace store*: append-only JSONL day-files under `data/traces/`. No SQLite, no DB — see §6 for the explicit trip-point that would justify revisiting that.

**Critical scope correction (applies throughout).** The naïve framing "emit one rich record at `generate_patch.py:165`" is only half-right. At line 165, in scope, are: `query`, the **final 8 `chunks`** (captured at `:152`, carrying `chunk_id`/`source_type`/`source_id`/`section`), the `changes`, `problems`, and the LLM response object. But the **25-chunk pool, RRF scores, actionability scores, rank-before/after, and diversify internals live inside `search.py` and are discarded before `retrieve()` returns.** Therefore `retrieve()`/`patch_diverse_search`/`_diversify_actionable` **must be widened with a `trace` out-param dict** that they populate in place; `generate_patch` passes one through and merges it into the emitted record. This is stated once here and assumed everywhere below.

Also note: the patch designer path (`mode="patch+div"`) **never calls `expand_query`** (only `rewrite_search` mode does). The Haiku-rewrite failure modes from the grounding are **out of scope** for this dashboard and appear as no stage.

---

## 2. Trace Data Model & Instrumentation

One trace = one JSON object = one line in `data/traces/{YYYYMMDD}.jsonl` (append-only, one file per local day). This mirrors `chunks.jsonl` and `golden_set.jsonl`, so the same `for line in f: json.loads(line)` idiom applies. Traces live under `data/` (uncommitted, like the corpus) — **not** under `eval/`, which stays read-only ground truth.

### 2.1 Storage, gating, failure isolation

- **Writer:** a ~30-line `src/ui/trace.py` exposing `emit(record)` → `json.dumps(record, ensure_ascii=False, default=str)` + `f.write(line+"\n")` + `flush()` in append mode. `_generate_lock` (`server.py:68`) already serializes `/api/patch`, so writes never interleave.
- **Gating: default-ON with failure isolation.** Tracing is the dashboard's only live data source; defaulting it off would leave the Overview/Trace views empty. So `emit()` always runs, wrapped in `try/except` that logs the swallowed exception **type** to stderr (via `log_message`) and never re-raises. An env override `P6_TRACE=0` disables it for a clean deterministic eval run. This is the "fail-safe, not silent-and-total" rule (D-032/ISSUE-2): the *trace* may fail silently; the *patch* must never fail because of tracing.
- **Trace id:** `{YYYYMMDD}-{HHMMSS}-{6hex}` (day-embedded, e.g. `20260618-142233-9f2a1c`). The day prefix lets `get(id)` open exactly one file. **No uuid4.**
- **No rotation infra:** a "clear traces" button `os.remove`s old day-files. `raw_output_text` is capped (first+last 2 KB with a truncation marker) so a runaway response can't bloat the log.

### 2.2 Record schema (grouped by stage)

Field names match the grounding's `trace_fields` 1:1. The live patch path is fixed (`mode="patch+div"`, `k=8`, `grounding="adapt"`, `model="claude-sonnet-4-6"`), so several envelope fields are constants today but recorded explicitly to survive a future config change.

```
trace_record = {
  # ---- envelope ----
  "trace_id":    str,    # {YYYYMMDD}-{HHMMSS}-{6hex} — also the day-file key
  "ts":          str,    # %Y%m%d-%H%M%S (same fmt as eval/results)
  "query":       str,
  "mode":        "patch+div", "k": 8, "grounding": "adapt"|"pure",
  "model":       "claude-sonnet-4-6", "temperature": 0.4, "max_tokens": 4096,
  "rrf_k":       60,     # RRF constant — recorded as a tunable lever (NEW, see metrics)
  "action_weight": 1.0,  # ACTION_WEIGHT — recorded as a tunable lever (NEW)
  "action_floor":  1.0,  # ACTION_FLOOR  — recorded as a tunable lever (NEW)
  "wall_ms":     int, "ok": bool,   # ok=false if any exception bubbled to server.py:70

  # ---- classify (search.py:228-238) — DIAGNOSTIC ONLY ----
  # patch+div ALWAYS treats query as recipe-shaped (search.py:195-196) and IGNORES this.
  "classify": { "recipe_shaped": bool, "matched_alternation_branch": str|null,
                "path_uses_result": false },

  # ---- pool (search.py:112-133) — REQUIRES search.py trace out-param ----
  "pool": {
    "pool_chunks": [ {"chunk_id":str,"source_type":str,"source_id":str,"section":str|null,
                      "rrf":float,"sim":float} ],   # the 25 candidates, fully attributed
    "lanes_present_in_pool": [str],
    "per_lane_contribution_counts": {str:int},      # D-024 skew detector
    "top_similarity_range": [float,float]
  },

  # ---- rerank (search.py:191-203) — REQUIRES trace out-param ----
  "rerank": {
    "actionability_by_chunk": {chunk_id: {"score":float,"term_hits":int,"imp_hits":int,
                                          "num_hits":int,"chat_hits":int}},  # components (184-188)
    "rel_rrf_vs_action_rrf":  {chunk_id: {"rel":float,"act":float}},
    "rank_before_after":      [[chunk_id,int,int]],
    "deduped_to_overflow":    [chunk_id]            # dedupe_by_source (136-145)
  },

  # ---- diversify (search.py:206-222) — REQUIRES trace out-param ----
  "diversify": {
    "final_topk_chunk_ids":     [str],              # the exact 8 (line 222)
    "groups_already_satisfied": [str],
    "injected_swaps": [ {"group":str,"evicted_chunk_id":str,"evicted_rank":int,
                         "swap_in_chunk_id":str,"swap_in_action":float,"slot":int} ],
    "patch_injection_outcome":  str,  # NEW. injected | no_candidate_in_pool
                                      #          | all_below_floor | already_present
    "candidates_below_floor":   [ {"chunk_id":str,"action":float} ]  # computed SEPARATELY:
                                      # members where act < ACTION_FLOOR (code keeps only ABOVE)
  },

  # ---- final_chunks: captured at generate_patch.py:152 (NOT from lossy `retrieved` labels) ----
  "final_chunks": [ {"chunk_id":str,"source_type":str,"source_id":str,
                     "section":str|null,"label":str} ],   # label = chunk_label(c), 60-65

  # ---- adapt / real_patch_block (generate_patch.py:73-104) — REQUIRES return-widening ----
  "adapt": {
    "patch_ids_selected":  [str],   # source_type=="patch", [:3] (line 79)
    "patch_files_missing": [str],   # data/patches/{id}.json absent (82-84)
    "neighbor_outcome":    str,     # ok | no_entries | Exception:<Type> (bare except 94-95)
    "neighbor_distance":   float|null, "num_patch_exemplars": int, "block_char_len": int
  },

  # ---- prompt (generate_patch.py:154-157) ----
  "prompt": { "chunk_labels_in_prompt":[str], "num_context_chunks":int,
              "schema_present":bool, "prompt_total_chars":int, "est_input_tokens":int },

  # ---- llm (generate_patch.py:158-162) ----
  "llm": { "stop_reason":str, "usage_output_tokens":int, "request_id":str,
           "model_returned":str, "api_exception":str|null,
           "raw_output_text":str },   # captured BEFORE _extract_json mutates it (capped 2KB+2KB)

  # ---- extract (generate_patch.py:129-143) ----
  "extract": { "extraction_path":"json.loads"|"regex_object"|"salvage",
               "had_markdown_fences":bool, "salvaged_change_count":int,
               "salvage_dropped_fields":[str], "raw_parse_error":str|null },

  # ---- validate (patch_schema.py:296-331) — clamped_values via OUT-PARAM dict (NEW) ----
  "validate": {
    "input_change_count":int, "clean_change_count":int,
    "problems":[str],                               # already collected (303,310,323)
    "clamped_values":[ {"param":str,"proposed":num,"clamped":num,"min":num,"max":num} ], # NEW (312)
    "noop_dropped":[str],                           # val==init (326-327)
    "select_fuzzy_matched":[ {"param":str,"proposed":str,"matched":str} ],   # (321)
    "coerced_toggle":[ {"param":str,"proposed":str,"bool":bool} ]            # (314-315)
  },

  # ---- patch: the actual delivered patch (the most direct "what did it do" surface) ----
  "patch": {
    "changes": [ {"param":str,"value":any,"why":str,"source":str} ],  # validated clean changes (165)
    "resolved_nondefault": {param: value},   # {**INIT_PATCH, **changes} minus init-equal params
    "change_count": int,                     # vs SYSTEM rule 5 target 10-25
    "narrated_not_delivered": [str]          # NEW. params named in why/summary but absent from
                                             # clean changes (catches noop/clamp-to-init erasure)
  },

  # ---- provenance (generate_patch.py:163-179) ----
  "provenance": {
    "source_distribution": {str:int},        # general synthesis vs label vs patch:<id>
    "unmatched_citations": [str],            # GATED on adapt.patch_ids_selected (see below)
    "mixer_all_down":      bool              # NEW: osc1/osc2/sub_octave/noise all 0 on resolved
  },

  # ---- sysex (generate_patch.py:182-188) ----
  "sysex": { "outcome":"ok"|"Exception:<Type>:<msg>",   # _sysex_for swallows ALL today (187-188)
             "name_truncated":bool, "value_fallbacks":[ {"offset":int,"param":str,"value":str} ] }
             # NOTE: sysex length is a constant 1176 by construction when outcome==ok — NOT a
             # per-request signal. It belongs only in encode_sysex selftest as an invariant.
}
```

### 2.3 Hook points (minimal, non-invasive)

| Locus | Change | Notes |
|---|---|---|
| `search.py` `patch_diverse_search` (`:191`), `_diversify_actionable` (`:206`) | add optional `trace: dict\|None = None` out-param; populate `pool`/`rerank`/`diversify` in place | `_actionability` results and `fused` are already in scope — copy them. `candidates_below_floor` is computed **separately** (re-evaluate `act` for members *below* the floor; code line 216 keeps only above). `patch_injection_outcome` classifies the patch group: `already_present` (continue at 214) / `no_candidate_in_pool` / `all_below_floor` (members exist, `cands` empty after 216) / `injected`. **Highest-value new field.** |
| `generate_patch` `:152` | capture the 8 `chunks` (full attribution) into `final_chunks` | labels alone are lossy (manual collapses `section` into the label) |
| `generate_patch.real_patch_block` (`:73-104`) | return `(block_str, adapt_meta)` | `patch_ids_selected`=`ids` (79); `patch_files_missing` recorded in the load loop (82-84); bare `except` (94-95) sets `neighbor_outcome="Exception:"+type(e).__name__` instead of `pass` |
| `generate_patch` `:159-162` | capture `msg.stop_reason`, `msg.usage.output_tokens`, `msg.id`, and `msg.content[0].text` **before** `_extract_json`; `_extract_json` returns `(dict, extract_meta)` | the raw text is the replay anchor |
| `patch_schema.validate_changes` (`:296-331`) | **add an optional `meta: dict\|None = None` out-param**, keep the public return `(clean, problems)` byte-identical | populates `clamped_values` (when line 312 changes the value), `noop_dropped`, `select_fuzzy_matched`, `coerced_toggle`. Out-param chosen specifically so the eval caller (`eval/patch_accuracy.py`) and seeded/temp-0 runs are unchanged. **Second-highest-value new field.** |
| `_sysex_for` (`:182-188`) | replace bare `except: return None` with `except Exception as e:` recording `sysex.outcome` | |
| `server.py do_POST` (`:58-71`) | build envelope (`trace_id`, `ts`, `wall_ms`, `ok`) and call `trace.emit()` **after the response is sent and after `_generate_lock` is released**; the `except` branch (70) emits a partial `ok=false` record | solves the "server 500 flattening" failure where the traceback is lost |

Net code change: ~6 return/param widenings, three new computations (`clamped_values`, `patch_injection_outcome`, `narrated_not_delivered`), one writer module. No control-flow change on the success path.

### 2.4 Two gated dependencies (critic fixes)

- **`provenance.unmatched_citations` requires `adapt.patch_ids_selected`.** The allow-set is `chunk_labels_in_prompt ∪ {"patch:"+id for id in patch_ids_selected} ∪ {"general synthesis"}`. Without the `real_patch_block` return-widening, every legitimate `patch:<id>` citation would false-positive as hallucinated. **Therefore `unmatched_citations` ships only in the milestone that widens `real_patch_block` (M0 second PR), not the first PR.**
- **`sysex` length is dropped as a per-request signal.** `encode_edit_buffer` returns exactly 1176 bytes by construction or raises; length is constant-when-ok and `None`-when-failed. The real signals are `outcome`, `value_fallbacks`, `name_truncated`.

### 2.5 Determinism & replay

- The record captures every input to the non-deterministic step (`model`, `temperature=0.4`, `max_tokens`, `rrf_k`, `action_weight`, `action_floor`, the assembled context). Retrieval is deterministic (NumPy dot-product), so given `final_topk_chunk_ids` the prompt is reproducible exactly.
- **`raw_output_text` is the replay anchor**: the entire post-LLM half (`extract → validate → provenance → sysex`) re-runs offline with zero API calls by feeding it back through `_extract_json`/`validate_changes` — consistent with D-017's "deterministic and free on re-run."
- The dashboard does **no live retrieval-replay** (see §6). To reproduce a *new* generation, re-issue the stored `query` through the existing `/api/patch` path.
- Decoded-patch values shown from `adapt.patch_ids_selected` inherit the D-023 provisional caveat (selector orders, `fx.on` per ISSUE-3) — badged provisional, never asserted.

### 2.6 Mapping a captured trace to the golden set

Because `final_chunks` stores `{chunk_id, source_type, source_id, section}` (not just the lossy label), promotion is near-mechanical and produces a *valid* `recall.py` target:

1. **`query`** copies across.
2. **`expected_targets`**: the analyst picks the chunk(s) that *should* have been served (a `patch` `source_id` sitting in `candidates_below_floor`, or a manual chunk that lost narrowly in the pool) and writes `{source_type, match}` using `recall.py`'s rules — **manual → `section` substring, all others → `source_id`** (NOT `chunk_id`; that's why `final_chunks` must carry both).
3. **`bucket`**: inferred from `classify.matched_alternation_branch` + the family/character vocab (`build_golden_v2.py`) → bucket 2/3.
4. **`param_targets`** (bucket-5): if `adapt.patch_ids_selected` is non-empty, those are the natural reference patches, scorable directly by `eval/patch_accuracy.py`.
5. The new line is validated by `check_targets.py` (D-005/D-015) before it joins the set.

### 2.7 Example trace record

A `make a fat vintage juno bass` request that produced an all-"general synthesis" patch — fully diagnosed:

```json
{
  "trace_id": "20260618-142233-9f2a1c",
  "ts": "20260618-142233",
  "query": "make a fat vintage juno bass",
  "mode": "patch+div", "k": 8, "grounding": "adapt",
  "model": "claude-sonnet-4-6", "temperature": 0.4, "max_tokens": 4096,
  "rrf_k": 60, "action_weight": 1.0, "action_floor": 1.0,
  "wall_ms": 6184, "ok": true,
  "classify": { "recipe_shaped": true, "matched_alternation_branch": "verb+noun", "path_uses_result": false },
  "pool": {
    "pool_chunks": [
      {"chunk_id":"red_1a2b#3","source_type":"reddit","source_id":"1a2b","section":null,"rrf":0.0301,"sim":0.58},
      {"chunk_id":"man_filters#0","source_type":"manual","source_id":"manual","section":"Filters","rrf":0.0277,"sim":0.55}
    ],
    "lanes_present_in_pool": ["reddit","manual","article","reddit-recipes"],
    "per_lane_contribution_counts": {"reddit":14,"manual":6,"article":5,"patch":0},
    "top_similarity_range": [0.31, 0.58]
  },
  "rerank": {
    "actionability_by_chunk": {"man_filters#0":{"score":6.0,"term_hits":4,"imp_hits":2,"num_hits":3,"chat_hits":0}},
    "rel_rrf_vs_action_rrf": {"man_filters#0":{"rel":0.0163,"act":0.0166}},
    "rank_before_after": [["man_filters#0",1,0],["red_1a2b#3",0,1]],
    "deduped_to_overflow": ["red_1a2b#7"]
  },
  "diversify": {
    "final_topk_chunk_ids": ["man_filters#0","red_1a2b#3","red_9z8y#1","art_synthsecrets#4","man_osc#2","red_4k5l#0","man_env#1","art_juno#3"],
    "groups_already_satisfied": ["manual/official_kb","reddit"],
    "injected_swaps": [],
    "patch_injection_outcome": "no_candidate_in_pool",
    "candidates_below_floor": []
  },
  "final_chunks": [
    {"chunk_id":"man_filters#0","source_type":"manual","source_id":"manual","section":"Filters","label":"Manual - Filters"},
    {"chunk_id":"red_1a2b#3","source_type":"reddit","source_id":"1a2b","section":null,"label":"reddit:1a2b"}
  ],
  "adapt": { "patch_ids_selected": [], "patch_files_missing": [], "neighbor_outcome": "no_entries", "neighbor_distance": null, "num_patch_exemplars": 0, "block_char_len": 0 },
  "prompt": { "chunk_labels_in_prompt": ["Manual - Filters","reddit:1a2b","reddit:9z8y","article:synthsecrets","Manual - Oscillators","reddit:4k5l","Manual - Envelopes","article:juno"], "num_context_chunks": 8, "schema_present": true, "prompt_total_chars": 9120, "est_input_tokens": 2280 },
  "llm": { "stop_reason": "end_turn", "usage_output_tokens": 980, "request_id": "req_01ABCxyz", "model_returned": "claude-sonnet-4-6", "api_exception": null, "raw_output_text": "{\"patch_name\":\"Vinyl Bass\",\"changes\":[{\"param\":\"filter.cutoff\",\"value\":300,\"why\":\"open the low-pass for body\",\"source\":\"general synthesis\"}, ...]}" },
  "extract": { "extraction_path": "json.loads", "had_markdown_fences": false, "salvaged_change_count": 0, "salvage_dropped_fields": [], "raw_parse_error": null },
  "validate": {
    "input_change_count": 16, "clean_change_count": 15,
    "problems": ["lfo.shape: option 'rev-saw' not in [...] — dropped"],
    "clamped_values": [ {"param":"filter.cutoff","proposed":300,"clamped":164,"min":0,"max":164} ],
    "noop_dropped": ["glide.rate"],
    "select_fuzzy_matched": [],
    "coerced_toggle": [ {"param":"unison.on","proposed":"engaged","bool":false} ]
  },
  "patch": {
    "changes": [ {"param":"filter.cutoff","value":164,"why":"open the low-pass for body","source":"general synthesis"} ],
    "resolved_nondefault": {"filter.cutoff":164,"mixer.osc1":127,"...":"..."},
    "change_count": 15,
    "narrated_not_delivered": ["glide.rate"]
  },
  "provenance": { "source_distribution": {"general synthesis": 15}, "unmatched_citations": [], "mixer_all_down": false },
  "sysex": { "outcome": "ok", "name_truncated": false, "value_fallbacks": [] }
}
```

**What this tells the developer, and which lever:** `provenance.source_distribution` is 100% "general synthesis" — the corpus contributed nothing. Root cause is one hop upstream: `diversify.patch_injection_outcome == "no_candidate_in_pool"` and `pool.per_lane_contribution_counts.patch == 0` — no patch chunk ever entered the pool, so `adapt.patch_ids_selected` is empty and `real_patch_block` returned `""`. **Lever: corpus/coverage**, not the prompt. Secondarily, `validate.clamped_values` shows `filter.cutoff=300` silently clamped to 164 (duller bass, invisible today) and `coerced_toggle` shows `unison.on` flipped *off* from `"engaged"` (thin-patch bug) → **lever: system prompt** (toggle/range vocabulary). `patch.narrated_not_delivered=["glide.rate"]` catches a move the `why` text describes but validation erased. The record is a ready bucket-2 golden candidate.

---

## 3. Metrics & Insights Catalog

Tiered by unit. Tier 1 = one request (inspector rail). Tiers 2–4 = aggregates. Each entry marks signals that **exist** (reuse a script/field) vs **GAP** (new computation + where). The two highest-value new fields to build first: **`clamped_values`** (`patch_schema.py:312`, silent today) and **`patch_injection_outcome`** (`search.py:216`, upstream cause of all-general patches).

### Tier 1 — Per-request trace

| # | Metric | Compute | GOOD / BAD | Lever |
|---|---|---|---|---|
| 1.1 | **Provenance distribution** (headline) | reuse `provenance_probe.classify(source)` over `patch.changes`; render stacked bar in `--patch/--manual/--reddit/--general` | mix with `patch:<id>` present / **all-`general synthesis`** | ties to 1.6/1.7: patch served but all-general → **system prompt**; none served → **retrieval/corpus** |
| 1.2 | **Hallucinated citations** | GAP. set-diff (§2.4), **gated on `patch_ids_selected`** | empty / any fabricated `reddit:xxxx` | **system prompt** (tighten contract); persistent → **golden set** probe |
| 1.3 | **Salvage / truncation** | GAP (trivial): `stop_reason`, `usage` vs 4096, `extraction_path`, `had_markdown_fences` | `end_turn`+clean / `max_tokens`+salvage (partial by construction, `playing_tip=''`) | **system prompt** (cap change count) or raise `max_tokens`; fences → prompt drift |
| 1.4 | **Validation: clamps/rejects/drops** | `problems` exists; `clamped_values`/`noop_dropped`/`select_fuzzy_matched`/`coerced_toggle` GAP (out-param) | few/none / many clamps on same param (D-033 bias), large drop gap | repeated offender → **system prompt** range/vocab; unmatched selects → schema text |
| 1.5 | **Change count vs 10–25** | `len(patch.changes)` | in-band / far below (1.3/1.4) or above | see 1.3/1.4/system prompt |
| 1.6 | **Patch chunk served?** | GAP: `patch_ids_selected`, `patch_files_missing` | ≥1 loaded / empty → `real_patch_block=''` → all-general | empty pool → **corpus**; floored → 1.7; missing file → **corpus** (`check_targets`) |
| 1.7 | **Injection / floor outcome** | GAP (2nd-highest): `patch_injection_outcome`, `candidates_below_floor`, `injected_swaps` (slot catches double-eviction) | injected/satisfied / `all_below_floor` with a real patch chunk | **retrieval mode** (lower `ACTION_FLOOR`, extend `_PARAM_TERMS`) |
| 1.8 | **Actionability components** | GAP: `_actionability` returns component dict (`term/imp/num/chat`, `:184-188`) | actionable scores above floor / settings-rich chunk at 0 (vocab gap) or one `thanks` floors it | **retrieval mode** (tune `_PARAM_TERMS`/`_CHATTER`) |
| 1.9 | **Pool & rerank trace** | GAP (search.py out-param): pool ids, lanes, `per_lane_contribution_counts`, `top_similarity_range`, `rank_before_after`, `deduped_to_overflow` | patch lane ≥1 / lane=0 (root of 1.6), uniformly low sim (off embedding), better same-bank exemplar stranded | **retrieval mode** / **corpus** |
| 1.10 | **Neighbor expansion** | GAP: success vs swallowed-exception-type, `neighbor_distance` | near neighbor / swallowed `KeyError` (malformed JSON) or far neighbor (drift) | **corpus** (JSON integrity); far → **retrieval mode** (distance cutoff) |
| 1.11 | **Prompt budget & sysex** | GAP: `prompt_total_chars`/`est_input_tokens`; `sysex.outcome`/`value_fallbacks`/`name_truncated` (**not length** — §2.4) | under truncation budget; `outcome==ok` no fallbacks / big prompt + 4096 cap; `sysex` exception (silent today) | prompt bloat → **system prompt**; sysex fail → encoder (surface, don't hide) |
| 1.12 | **Recipe classification (diagnostic-only)** | GAP, **display with caveat**: patch path ignores `_recipe_shaped` (always recipe-shaped, `:195-196`) | matters for **Q&A only** | **retrieval mode** (regex) *for ask.py*; record + the "ignored on patch path" fact so the two paths are never conflated |
| 1.13 | **Narrated-not-delivered** (NEW) | GAP: params named in `why`/summary prose but absent from clean `changes` (noop/clamp-to-init erasure) | empty / any → "user reads it in the explanation but it's not on the panel" | **system prompt** (don't narrate dropped moves) or **validation** review |
| 1.14 | **Delivered param set** (NEW, near-free) | `patch.resolved_nondefault` + `patch.changes` (in scope at 165) | the direct "what did the patch actually do" surface | n/a — context for all other levers |

### Tier 2 — Aggregate trends (rolling, live requests)

All **GAP for live requests** — every existing number is golden-sample-only. Source = `data/traces/*.jsonl`, computed on read.

| # | Metric | Closes gap | Lever |
|---|---|---|---|
| 2.1 | **Live provenance rate** — per-request *cited-fraction distribution* + all-general % | closes "per-request provenance RATE" (probe is pooled-aggregate only) | correlate with 2.2/2.3 |
| 2.2 | **Salvage/truncation rate** over time | — | **system prompt** / `max_tokens` |
| 2.3 | **Clamp/reject rate + top offending params** | surfaces the D-033 systematic-bias param (e.g. `lfo.rate` always clamped high) | **system prompt** / schema |
| 2.4 | **Patch-served rate + floor-block rate** | — | floored → **retrieval mode**; empty-pool → **corpus** |
| 2.5 | **Change-count distribution** vs 10–25 | — | 1.3/1.4 |
| 2.6 | **Same-bank dedupe-loss rate** (NEW) — % requests where a patch exemplar lost to `dedupe_by_source` overflow | named failure (`search.py:136-145`) starving popular banks; aggregates Tier-1 `deduped_to_overflow` | **retrieval mode** (per-bank cap) / **corpus** |

### Tier 3 — Experiment loop (offline eval, regression surface)

Reuses the harness wholesale: every scored script self-describes via `{run, timestamp, mode/model/k, summary, per_bucket, per_query}` and writes `eval/results/{ts}_{kind}_{label}.json`. **GAP:** no manifest / "latest per kind" rollup and no run-to-run delta — the dashboard computes both (glob + parse filename + diff vs prior same-kind run).

| # | Metric | Source | Caveat (must surface) | Lever |
|---|---|---|---|---|
| 3.1 | **v1 recall@5 tripwire** (≥0.95; 0.951→0.902 FAIL) | `recall.py` `overall_recall`+`per_query` | **never a bare red dot** — D-029 eval-staleness collisions; show MISS drill-down (which `top_chunks` displaced the target) | dilution → **retrieval mode**; staleness → **golden set** re-target (never mid-run, D-015) |
| 3.2 | **Patch param accuracy** (`mean_active_agreement`, per-section-group) | `patch_accuracy.py` (`resolve_full`/`score_against`/`SECTION_GROUPS`) | **bucket-5 only** (18 probes); buckets 2/3 have no reference | weak group → **system prompt** / **corpus** exemplars |
| 3.3 | **Reference-free quality** (roundtrip/rubric/judge) | `patch_quality.py` + `--selftest` separation | judge can't hear; roundtrip = consistency not correctness | **system prompt** / **corpus** per `judge_missing` |
| 3.4 | **A/B win rate** (adapt vs pure) | `patch_ab.py` | **citation-stripper missed `[patch:]` → ~10 wrong-basis verdicts** ("measured judge artifact"); flag, don't present raw | **retrieval mode** (grounding) / **corpus** |
| 3.5 | **Offline provenance** (`cited_ratio`, `by_source`) | `provenance_probe.py` | offline analogue of 2.1 | as 1.1 |
| 3.6 | **Faithfulness & bake-off** (Q&A, secondary) | `faithfulness.py`/`bakeoff.py` | mandatory spot-check; 6 pending contradicted claims; B2 judge artifact → `[provisional — pending builder review]` | Q&A path (`ask.py`), secondary panel |
| 3.7 | **Run-to-run deltas + latest-per-kind rollup** | GAP: glob+parse+diff | `coverage_report.json` is **fixed-filename** (overwrites; no history) — flag + recommend timestamping the writer | negative delta = alarm; link to drill-down (cause, not just sign — D-029) |

### Tier 4 — Corpus health

| # | Metric | Compute | GOOD / BAD | Lever |
|---|---|---|---|---|
| 4.1 | **Coverage matrix** (families×characters, ≥3 sources, ≥90%) | reuse `coverage_report.py --write`; heatmap `--manual` covered / `--warm-2` gap; axes from `coverage_matrix.yaml` | ≥90% / any gap cell (predicts all-general for that sound) | **corpus** (the acquisition shopping list) |
| 4.2 | **Corpus utilization / dead chunks** | GAP: aggregate `recall.py` `top_chunks` set-diff against `chunks.jsonl` | broad utilization / large dead set | **corpus** (re-chunk/drop) or **retrieval mode** |
| 4.3 | **Per-source retrieval frequency** | GAP: histogram of `top_chunks` | healthy spread / over-relied head + long tail | **corpus** / **golden set** |
| 4.4 | **Retrieved-but-never-cited** | GAP: join live traces (`final_chunks` labels) vs `change.source` | cited / consistently ignored (relevance≠actionability, ties 1.8) | **retrieval mode** / **corpus** |
| 4.5 | **Target reachability** (PASS/FAIL gate) | reuse `check_targets.py`; GAP = parse output to a `.status` pill | PASS / UNREACHABLE/MISSING PATCH (unanswerable corpus, D-005/D-015) | **corpus** restore / **golden set** fix |

### Cross-cutting display conventions

- **Provisional labelling (D-019/D-021):** assistant-judged metrics (3.3 judge, 3.4 A/B, 3.6) render a `[provisional — pending builder review]` badge; known artifacts get an inline `.tip`/`.problems` callout.
- **Decoded params provisional (ISSUE-4/D-023):** selector orders, `fx.on` (ISSUE-3) marked low-confidence.
- **Surface silent failures (ISSUE-2 ethos):** `sysex` exception, swallowed neighbor exception, silent clamps all get an explicit visible state.
- **Recall never a bare dot (D-029):** 3.1 always links the per-query MISS drill-down.
- **Tunable-lever knobs recorded:** `rrf_k=60`, `action_weight=1.0`, `action_floor=1.0` ride in the envelope so a rerank-flip regression can be correlated with a knob change.

### Build-order priority
1. **`clamped_values` (`patch_schema.py:312`) + `patch_injection_outcome` (`search.py:216`)** — unblock 1.4, 1.7, 2.3, 2.4.
2. **Per-request trace** (search.py out-param + `final_chunks` at 152 + emit after 165) — unblocks all Tier 1/2.
3. **Glob/parse `eval/results/` → latest-per-kind + delta** (3.7) — unblocks Tier 3.
4. **Aggregate `top_chunks` vs `chunks.jsonl`** (4.2/4.3) + timestamp `coverage_report.json` (4.1 trend).

---

## 4. Information Architecture & Views

The dashboard is a static trio **`src/ui/static/dash.html` / `dash.css` / `dash.js`** (one name, used everywhere), served by the same `ThreadingHTTPServer`, with new read-only routes in `Handler.do_GET`. It reuses the `.topbar` (62px, `#0c0d12cc` + `blur(14px)`) and the `PROPHET·6` wordmark, swapping the `STUDIO` tag for `OBSERVABILITY`. The `:root` modern-surround tokens are factored into a shared `base.css` (both `studio.html` and `dash.html` `<link>` it), excluding the `--face`/`--cream`/`--seg` hardware tokens. No build step, no framework — same `_send_json` + `fetch('/api/...')` idiom.

Nav is a left-aligned `.zoom` segmented control in the topbar — **Overview / Trace / Diff / Corpus / Golden** — with deep links via `?v=trace&id=...` (matching `studio.js`'s `?q=` convention). All views use the `.workspace` grid (`minmax(0,1fr)` main + `384px` rail).

### New server routes (read-only, stdlib, file-backed)

| Route | Returns | Source |
|---|---|---|
| `GET /api/traces?limit&since&filter` | reverse-chrono trace **summaries** (id, ts, query, stop_reason, source_distribution, injection_outcome, n_clamped, n_problems, mixer_all_down) — never `raw_output_text` | scan `data/traces/*.jsonl`, newest day-file first |
| `GET /api/trace/{id}` | one full record (id day-prefix → open exactly one file, **linear scan, no offset index**) | `data/traces/{day}.jsonl` |
| `GET /api/eval/runs?kind` | run manifest from `{ts}_{kind}_{label}.json` filenames, latest-per-kind | `glob('eval/results/*.json')` filename parse |
| `GET /api/eval/run/{file}` | one result file verbatim (path-validated to `eval/results/`) | file read |
| `GET /api/eval/diff?a&b` | per-bucket / per-query delta between two same-kind runs | two result files |
| `GET /api/corpus` | `index_meta.json` + streamed `chunks.jsonl` lane counts + dead-chunk join vs pooled `top_chunks` — **computed lazily, only on Corpus-view open** | `data/index/` + `data/chunks/` |
| `GET /api/coverage` | `coverage_report.json` + `coverage_matrix.yaml` (axes) | `eval/results/` + `eval/` |
| `GET /api/golden` | `golden_set*.jsonl` + `check_targets.py` gate state | `eval/` |
| `GET /api/overview` | KPI rollup: latest-per-kind summary scalars + **live** rolling provenance/clamp/injection/salvage rates over recent traces (corpus dead-chunk join **excluded** — too heavy for the summary) | merge of the above |

### View 1 — Overview / Health

KPI tile row (`.stats`, each `.stat` = `flex:1; min-width:84px`, mono `.n` over uppercase `.k`), colored by threshold: **v1 recall@5** (`.n.amber`, target 0.95 — green ≥, red <, says FAIL today at 0.902), **provenance cited_ratio**, **patch active-agreement** (bucket-5 caveat `?`), **coverage** (90% line), **A/B adapt win-rate**, **faithfulness %**. Each tile carries a **trend sparkline** (inline `<svg>` polyline over timestamped same-kind runs — the `0.951→0.902→0.829` D-024/D-027/D-029/D-035 history as a chart). 

Right-rail alarm tiles (`.problems`/`.tip`), each a click-target deep-linking to a pre-filtered Trace Explorer:
- **Tripwire alarm** (`--warm-2` if <0.95) — carries the D-029 staleness caveat inline ("misses may be eval-staleness collisions — open: re-target vs freeze"), never a bare red number.
- **Salvage-rate**, **silent-clamp**, **no-patch-served** (highest-value: predicts all-general), **silent-failure** (sysex/neighbor exceptions surfaced — ISSUE-2 ethos).
- Provisional metrics wear `[provisional — pending builder review]` micro-badges; the A/B tile carries the citation-stripper artifact caveat.

### View 2 — Trace Explorer

Left: `.change`-style trace list (query left, mono outcome + provenance dot right, 2px health-colored left border), filterable via `.chip` row (`salvage` / `no-patch` / `clamped` / `all-general` / `hallucinated-cite` / `sysex-fail`). Selecting a row loads a top-to-bottom **stage rail** (collapsible `.section-title` cards) walking the live path. Right `384px` rail = the focused stage's raw artifact.

Stage cards (the **classify card explicitly states "patch path ignores this"**; **no `expand` stage** — `expand_query` is never on the patch path):

1. **Query & classification** — `recipe_shaped`, `matched_alternation_branch`, the "ignored on patch path" note.
2. **Retrieval pool (k=25)** — `pool_chunks` ranked table (lane dot, `rrf`, `sim`); `per_lane_contribution_counts` stacked bar (D-024 skew); `top_similarity_range` gauge.
3. **Actionability rerank + RRF** — per-chunk component breakdown + `rel_rrf_vs_action_rrf`; a real-patch chunk sinking below k glows `--warm-2`.
4. **Diversity injection** — `final_topk_chunk_ids`, `injected_swaps` (group/evicted/slot); the hero field `patch_injection_outcome` + `candidates_below_floor` distinguishes "floored out" vs "no patch in pool."
5. **Grounding block** — `patch_ids_selected` (empty → red), `patch_files_missing`, `neighbor_outcome`(+exception type), `neighbor_distance`, `block_char_len`.
6. **Prompt assembly** — `chunk_labels_in_prompt`, `prompt_total_chars`, `temperature/max_tokens/model`; big-prompt-vs-4096 flagged.
7. **LLM output & parse** — `stop_reason` (red if `max_tokens`), `usage` vs 4096, full `raw_output_text` in mono pre, `extraction_path`, fences, salvage fields.
8. **Validation / clamping** — `problems`, `clamped_values` (`cutoff 300→164`), `noop_dropped`, `select_fuzzy_matched`, `coerced_toggle`; each silent mutation a `--blue` chip.
9. **Provenance** — `source_distribution` stacked bar; `unmatched_citations` `--warm-2` (gated on `patch_ids_selected`).
10. **Final patch + sysex** — `patch.resolved_nondefault` + `patch.changes` table (the direct "what did it do"), `narrated_not_delivered`, `change_count` vs 10–25, `mixer_all_down`, `sysex.outcome`/`value_fallbacks`/`name_truncated` (no length); decoded params carry the D-023 caveat.

Each card has a one-line **"lever" footer**.

### View 3 — Experiment / Run-Diff

Two `.ghost` run pickers (from `/api/eval/runs`). Picking two same-kind runs yields: **headline delta band** (`+0.049` green / `−0.049` red — the D-035 `0.902→0.829` event made first-class), **per-bucket delta table**, **per-golden-item regressed/improved list** (joins `per_query` by `id`; HIT→MISS red, MISS→HIT green; recall shows both runs' `matched`/`top_chunks` side by side — the D-027 displacement story; patch_accuracy shows `by_group` deltas), and a **tripwire verdict strip** (PASS/FAIL vs 0.95 with the D-029 staleness caveat). Each regressed `id` deep-links into the Trace Explorer or Golden view.

### View 4 — Corpus Health

Reads `/api/corpus` (lazy, on view-open). **Coverage heatmap** (10×8, 4 excluded gray; `--warm-2` <3 / `--manual` ≥3; `pct_cells_3plus` vs 90%; note the fixed-filename no-trend caveat). **Lane distribution** stacked bar by `source_type`. **Retrieval-frequency histogram** (over-relied head + tail). **Dead-chunk list** (zero top-k appearances; lane + section; ISSUE-3/D-023 caveats on fx.on/selectors). A heatmap cell deep-links to the Golden view filtered to that family/character.

### View 5 — Golden-Set

Reads `/api/golden`. **Reachability gate strip** (`check_targets.py` PASS/FAIL). **Query inventory table** (41 v1 + 85 v2, keyed by id/bucket, with `expected_targets`/`param_targets`/`phrasing`, sortable by bucket and latest HIT/MISS). **Gap surface** (cells with corpus coverage but no probe, and inverse). **Promote-a-failing-request-to-golden**: a `.primary` button on a live trace row drafts a JSONL record (`query` verbatim, guessed `bucket`, `expected_targets` pre-filled from `final_chunks` as valid `{source_type, match}` tuples per §2.6), shows it in a `.popover` for review, appends to `golden_set_v2.jsonl` on confirm, then nudges to re-run `check_targets.py`. The developer ratifies before it lands (D-015); the draft wears a provisional flag.

### Click-paths: "bad patch" → "pull this lever"

1. **All-'general synthesis' → corpus or floor.** Overview no-patch alarm → Trace filtered `no-patch` → Diversity card. `candidates_below_floor` lists a real patch chunk floored <1.0 → **lower `ACTION_FLOOR` / widen `_PARAM_TERMS`** (`search.py:216`/`184-188`). `patch_ids_selected==[]` + pool shows zero patch-lane → Corpus dead-chunk/lane view → **acquire exemplars for that cell** (Golden gap surface confirms the hole).
2. **Missing requested move → validation.** Trace → Validation card. In `problems` → **system prompt schema framing**. In `clamped_values` → **tighten SYSTEM range guidance**. In `noop_dropped`/`coerced_toggle` (`'enabled'→False`) → **SYSTEM toggle vocabulary**. In `narrated_not_delivered` → **stop narrating dropped moves**.
3. **Truncated patch → prompt budget.** Salvage alarm → LLM card (`max_tokens` + `usage≈4096`) × Prompt card `prompt_total_chars` → **trim `real_patch_block` max_patches or raise max_tokens**.
4. **Aggregate low provenance → dead corpus.** Provenance KPI low → Trace filtered `all-general` → common pool lane gap → Corpus dead-chunk list → **ingest/re-chunk that lane** (Diff view then confirms improvement without tripping the v1 tripwire, D-024).
5. **Regression after a change → run-diff → root cause.** Overview sparkline dips → Run-Diff → HIT→MISS rows → click `id` → Trace shows the displacing chunk (D-027) → **per-source dedupe / lane weighting**, or if eval-staleness → **re-target the golden entry** (never mid-run, D-015). The tripwire strip decides merge/revert (D-035), FAIL shown with cause.

---

## 5. Visual Design System

A **sibling page** of the patch panel, not a new product. The cardinal rule (from the grounding): **adopt the modern-surround tokens, never the hardware-face skin** (`.dial`/`.led`/`.dispwin`/`.capbtn`/`--face`/`--cream`/`--seg` are reserved for the one physical unit). The dashboard is the chrome *around* the synth.

### 5.1 Token strategy: shared `base.css`

Factor the modern-surround `:root` half of `studio.css` (explicitly excluding the hardware-face block) into `src/ui/static/base.css`, `<link>`ed by both `studio.html` and `dash.html`. `dash.css` then adds only the few widgets Studio lacks (sparkline, score-bar table, heatmap, diff viewer). Reuse the body canvas verbatim:

```css
body {
  background:
    radial-gradient(1100px 560px at 80% -8%, #181a24 0%, transparent 60%),
    radial-gradient(900px 500px at 0% 0%, #15161d 0%, transparent 55%), var(--bg);
  background-attachment: fixed;   /* --bg = #08090c */
}
```

### 5.2 Color usage (real tokens)

| Token | Hex | Dashboard role |
|---|---|---|
| `--bg` | `#08090c` | canvas (with radial gradients) |
| `--surface` | `#14161d` | KPI cards, table rows, default panels |
| `--surface-2` | `#181b23` | raised rows, active segmented button |
| `--raised` | `#1d212b` | popover flyouts (`.popover`) |
| `--border` / `--border-soft` | `#272b37` / `#1f222c` | borders / dividers, gridlines, section rules |
| `--text` / `--text-dim` / `--text-faint` | `#eceef3` / `#969ba9` / `#646a78` | primary / secondary / eyebrow+placeholder |
| `--amber` | `#ff9d44` | **signature accent** — brand dot, focus ring, active/selected, primary metric |
| `--amber-soft` | `#ffb86a` | mono metric values (matches `.change .pval`) |
| `--warm-2` | `#ff6a4d` | error/FAIL/gap |
| `--blue` | `#6fa8ff` | links, info callouts |

**Provenance bars reuse the exact badge tokens** (no new colors): `--manual #7fd08a` / `--reddit #ff9d5c` / `--patch #6fb8ff` / `--general #9aa3b2` on their dark tinted pill fills (`#16271a`/`#2e1d10`/`#102434`/`#20242c`). An all-`--general` bar is the unmistakable headline symptom.

**Metric health — reuse the existing semantic tokens directly, do NOT invent new variables.** The other sections (Metrics/IA) use `--manual`/`--amber`/`--warm-2` raw, and the grounding's reuse rule says "adopt the `:root` block verbatim." So the convention is: **OK = `--manual #7fd08a`** (already the done-status dot), **WARN/attention = `--amber #ff9d44`**, **BAD/FAIL = `--warm-2 #ff6a4d`** (already the error-status dot). Tinted callout fills reuse the existing `.tip` (info: bg `#101a26` / border `#1d3144` / text `#b9d2ec`) and `.problems` (error: bg `#261616` / border `#4a2727` / text `#e9a7a7`) recipes verbatim. No new hex values are introduced. A one-class modifier (`.n.ok`/`.n.warn`/`.n.bad`) maps to these existing tokens, mirroring the existing `.n.amber`.

**Severity discipline:** color means *state*, not decoration. A KPI tile is neutral `--text` white by default and takes a health color only on threshold crossing (recall <0.95 → bad; coverage <90% → warn). The eye lands on the one red number.

### 5.3 Typography

Reuse the Studio `@import` verbatim: **Inter** (400/500/600/700) prose/labels, **JetBrains Mono** (500/600) every number/value/chunk_id/timestamp. Do **not** pull the hardware 7-seg `Consolas` italic.

| Element | Spec | Mirrors |
|---|---|---|
| Wordmark | 19px/700, `letter-spacing:2px`, amber `·` | `.wordmark .mark` |
| Page tag pill | 10px/600, `letter-spacing:4px`, bordered | swap `STUDIO`→`OBSERVABILITY` |
| KPI number | `700 19px/1 "JetBrains Mono"` | `.stat .n` |
| KPI key | 10px/600 UPPERCASE `.8px`, `--text-faint` | `.stat .k` |
| Section eyebrow | 10px/600 UPPERCASE `1.5px` + trailing hairline | `.section-title` |
| View heading | 22px/700 `-.2px` | `.result h2` |
| Table value / chunk_id | `600 12.5px/1 "JetBrains Mono"` | `.change .pval` |
| Status text | 12.5px/500 | `.status` |

### 5.4 Layout grid

Mirror Studio's shell so chrome aligns when tabbing between pages: `body` full-height flex column; verbatim `.topbar` (62px, `#0c0d12cc`, `blur(14px)`, `z-index:30`); `.workspace` grid (`minmax(0,1fr) 384px`); `.inspector` rail (`border-left`, bg `#0b0c11`, `.inspector-inner{overflow-y:auto;padding:20px}`); `.stage-bar` sub-toolbar (`.status` dot left, `.zoom` segmented control right). Custom scrollbar: `11px`, thumb `#232734` + `3px transparent border` + `background-clip:padding-box`. Radius **9–11px cards/inputs, 20px pills, 13px popovers**; `--shadow` on elevated cards. Two breakpoints: `@media(max-width:1180px)` collapses to one column (rail below, `border-top`); `@media(max-width:720px)` wraps the topbar.

### 5.5 Component library (vanilla JS, restyle existing classes)

- **KPI stat card** — reuse `.stat`/`.stats` verbatim + `.n.ok/.warn/.bad` modifier.
- **Trend sparkline** (`.spark`) — inline `<svg>` ≈140×34, one `<polyline>` (`--amber`, 1.5px), latest point a 2.5px dot, threshold a dashed `--border` rule. Closes the no-trend gap.
- **Retrieval-pool table** — 25-chunk table: `chunk_id` (mono), `lane` (provenance-tinted dot), `rrf`/`actionability` as inline `<div class="bar">` (width `=score/max`), `Δrank` chip. Floored rows `--warm-2` left border; injected row `--manual` left border. Reuses `.change`'s 2px-left-border idiom.
- **Lane/provenance stacked bars** — `per_lane_contribution_counts` and `source_distribution` in the four provenance tokens; legend uses `.badge` pills.
- **Prompt/output diff viewer** — `.popover` two-pane mono flyout: left = prompt summary, right = `raw_output_text`; `unmatched_citations` highlighted (error), `clamped_values`/`noop_dropped` highlighted (warn) with `proposed → clamped (min,max)` tooltip; `max_tokens` paints a banner. Surfaces the two grounding-flagged silent failures first.
- **Run-diff table** — metric · A · B · Δ; Δ colored by sign/threshold. The honest-reporting surface.
- **Coverage heatmap** — CSS-grid `<div>`s, background interpolated across the existing health hues by source count; 4 excluded cells hatched; counts in mono. No SVG.

### 5.6 Charting: hand-rolled inline SVG + styled `<div>`, zero libraries

Justified by ethos (D-020 no-build static frontend, D-010 transparent-by-inspection, no-heavy-deps constraint). Sparklines/trend = one `<polyline>` + threshold `<line>`. Score/stacked bars + heatmap = styled `<div>`s with percentage widths (no SVG). Run-diff/pool = `<table>`/CSS grid. **Canvas rejected** (loses DOM inspectability/hover/accessibility); **any chart lib rejected** (violates the named no-extra-dep rule). SVG over canvas specifically so each datum stays a real DOM node you can hover/title/token-color.

### 5.7 Data-density & accessibility

- **Small-multiple sparkline KPIs**, **progressive disclosure** (Overview glanceable → 384px rail detail → Trace 13-stage drill), color only on threshold crossing, eyebrow+hairline section dividers, mono-aligned numeric columns, and honest-data labels (provisional pills + `.tip` caveats; eval-staleness gets a `.tip` not a bare red dot).
- **Contrast:** `--text` on `--surface` ≈13:1 (AAA); `--text-dim` ≈5.2:1 (AA at 12px+); `--text-faint` ≈2.7:1 reserved for large/uppercase decorative labels only — never a load-bearing number. Health tokens on dark all clear AA (`--manual`≈8.5:1, `--warm-2`≈5.1:1, `--amber`≈8:1).
- **Never color-alone:** every state doubled with glyph/text (`.status` dot + label; floored/injected rows + explicit tag; provenance bar + mono %). **Focus:** amber ring (`border #4a4030` + `box-shadow 0 0 0 3px #ff9d4422`) on every control; view-switchers are real `<button>`s in `role="group"`. **Motion:** reuse only `pulse`/`pop`/`spin`; no chart animation.

### 5.8 ASCII wireframe — Overview

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ PROPHET·6  [OBSERVABILITY]   ⟦ run: 20260618-1432_recall_w7  ▾ ⟧   [Refresh] [Studio →]│  .topbar 62px, blur
├──────────────────────────────────────────────────────────────────────────────────────┤
│ ● data as of 2026-06-18 14:32 (local)      View ⟦Overview│Trace│Diff│Corpus│Golden⟧    │  .stage-bar + .zoom
├───────────────────────────────────────────────────────────────────┬────────────────────┤
│  ┌────────────┐┌────────────┐┌────────────┐┌────────────┐┌───────┐ │  RUNS              │
│  │0.902  bad  ││ 100%   ok  ││ 0.71       ││ 0.78       ││ w7    │ │  recall  20260618  │  right rail 384px
│  │V1 RECALL@5 ││ COVERAGE   ││ PROV. CITED││ PATCH ACT. ││ LABEL │ │  ▸0.902  ✗ FAIL    │  (.inspector,#0b0c11)
│  │ ╲╱╲___0.95 ││ ▁▃▅▇█ 90% ││ ▂▄▃▅ ─cited││ ▃▄▅▆ agree?││ MONO  │ │  cover   20260618  │
│  └────────────┘└────────────┘└────────────┘└────────────┘└───────┘ │  ▸100%   ✓         │
│    sparkline KPI tiles (.stat + .spark), health-colored .n         │  ─────────────────  │
│                                                                    │  RUN DIFF  w6 → w7 │
│  RETRIEVAL HEALTH ─────────────────────────────────────────       │  recall 0.951→0.902│
│   v1 tripwire   ████████████████████░░  0.902  bad < 0.95         │   Δ -0.049  ✗       │
│     ↳ D-029: misses may be eval-staleness collisions  (ⓘ tip)     │                    │
│   pool lane mix █patch ███manual ██reddit ░general                 │  [provisional —    │
│  GENERATION HEALTH ────────────────────────────────────────       │   judge artifacts  │
│   stop_reason=max_tokens   3 / 50 runs   warn (salvage path)      │   flagged, D-021]  │
│   clamped values (silent)  12 across runs warn                    │                    │
│   all-'general' patches    4 / 50  bad  → no patch lane           │                    │
└───────────────────────────────────────────────────────────────────┴────────────────────┘
```

### 5.9 ASCII wireframe — Trace Explorer

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ PROPHET·6  [OBSERVABILITY]   ⟦ trace: "fat vintage juno bass"  20260618-142233 ▾ ⟧     │
├──────────────────────────────────────────────────────────────────────────────────────┤
│ ● adapt · sonnet-4-6 · k=8 · temp 0.4 · floor 1.0    View ⟦Overview│Trace│…⟧           │
├───────────────────────────────────────────────────────────────────┬────────────────────┤
│ PIPELINE  (click a stage)   (no expand stage — off patch path)     │ STAGE: diversify   │
│  classify ─ POOL ─ rerank ─[DIVERSIFY]─ adapt ─ prompt ─ LLM ─ ⟶   │  inject (actionable)│
│   ✓(ign)    ✓     ✓        ⚠ patch✗     ∅      ✓       ✓          │  ───────────────── │
│  ⟶ extract ─ validate ─ patch ─ provenance ─ sysex                 │  patch group:      │
│     ✓        3 mut⚠   15chg   general✗     ok ✓                   │   injection ✗       │
│                                                                    │   outcome:          │
│ RETRIEVAL POOL  (25 → rerank → top-8)                              │    no_candidate_in_ │
│  CHUNK_ID        LANE   RRF              ACT             Δrk        │    pool             │
│  manual:Filters  ●man   ████████░ .071   ██░░ 1.8       +0        │   ACTION_FLOOR 1.0  │
│  reddit:1a2b     ●red   ██████░░░ .058   ███░ 2.4       +1        │   cands below floor:│
│  art:synthsecr   ●art   ████░░░░░ .041   ██░░ -1.0      -3        │    (none — lane=0)  │
│  …  patch lane contributes 0 chunks  ⚠                            │  groups satisfied:  │
│                                                                    │   manual, reddit    │
│ FINAL TOP-8 → PROMPT (9,120 chars · schema ✓ · 8 chunks)         │  ───────────────── │
│  provenance ░░░░░░░░░░░░░░░░░░  ✗ ALL 'general synthesis' (15)    │  ⇒ NO patch served  │
│  validate: cutoff 300→164 (clamp) ⚠  unison.on 'engaged'→off ⚠   │   → patch_ids = []  │
│  [ view prompt / output diff ▸ ]   stop_reason: end_turn          │   → all cite general│
│                                                                    │   LEVER: corpus /   │
│                                                                    │     ACTION_FLOOR    │
└───────────────────────────────────────────────────────────────────┴────────────────────┘
```

The rail shows `_diversify_actionable` (search.py:206–222): `patch_injection_outcome="no_candidate_in_pool"`, the causal chain to empty `real_patch_block`, and the literal lever — the highest-value diagnostic, surfaced as the first thing the eye lands on.

---

## 6. Backend & Integration Architecture

### Decision: extend `src/ui/server.py`, NOT a sibling server

The most valuable data source is the live patch path, and tracing it requires a write hook *inside the running process* of `generate_patch` (the record is the dict assembled at `:165` plus the search.py out-param data). A sibling server can't see that without IPC/duplication. Adding routes to the existing `Handler` is strictly simpler:

- `Handler(SimpleHTTPRequestHandler)` already serves `src/ui/static/` and dispatches `/api/*` via `_send_json` — new routes are 4-line branches.
- `ThreadingHTTPServer` already gives concurrency, so dashboard polling doesn't block a generation.
- One process = one warmed BGE model shared by designer and dashboard (a sibling would re-warm BGE for nothing).
- Served as a sibling static trio `dash.{html,css,js}` in `src/ui/static/`. The README launch command is unchanged; `python src/ui/server.py 8765` now also serves `/dash.html`.

### Endpoints

All `GET`, all `application/json` via `_send_json`. The dashboard never mutates pipeline state (it reads traces/eval files; it does **not** re-run retrieval — see "no replay" below). Routes per §4. The corpus dead-chunk join is **lazy, only on Corpus-view open**, and is **kept out of `/api/overview`** (too heavy for the summary rollup).

### Trace storage: append-only JSONL, Python aggregation on read. No SQLite.

One JSONL file per local day under `data/traces/` (`data/traces/20260618.jsonl`), one record per line — mirroring the `chunks.jsonl` single-contract convention and `eval/results/*.json` self-describing convention, inspectable by `cat`/`tail`. A small `src/ui/trace_store.py`:

- `append(record)` — open current day-file, write `json.dumps + "\n"`, flush.
- `iter_summaries(limit, since, filter)` — reverse-iterate day-files (newest filename first), yield the cheap summary projection, stop at `limit`.
- `get(trace_id)` — the day-embedded id (`{YYYYMMDD}-{HHMMSS}-{6hex}`) names exactly one file; **linear scan of that one day-file** (sub-ms at single-dev scale). **No offset index** (premature).
- `aggregate(window)` — one pass for the live rates `/api/overview` needs (all-general %, no-patch-injected %, mean clamps, `max_tokens` count). **Computed on read, not precomputed** — no cache to invalidate, no background job. These are the one genuinely new measurement the backend produces (closing the "per-request provenance RATE" / "live provenance" gaps).

**Why not SQLite (stdlib, would be allowed):** single-dev, dozens-to-hundreds of traces per session; aggregations are O(n) over a few day-files — trivially fast in plain Python. A schema/migrations/binary `.db` you can't `git diff` or `tail` is exactly the infra D-001/D-010 reject. **Explicit trip-point to revisit:** traces exceed ~10⁵ rows, *or* cross-day trend queries make linear scans laggy. Neither holds today.

The only acceptable cache: if the corpus full-scan (25,544 lines) is ever too slow, memoize in a module-level dict keyed by `chunks.jsonl` mtime. In-process, no second store.

### Concurrency with `_generate_lock`

- `generate_patch` runs under `with _generate_lock` (`server.py:68`). The trace write must **not** extend that critical section: the record is fully assembled when `generate_patch` returns, so the `Handler` `_send_json`s the response first, **then** `trace_store.append(...)` **outside the `with` block** — zero added lock-hold time.
- Dashboard read endpoints **never acquire `_generate_lock`** (file reads only); `ThreadingHTTPServer` serves them on a separate thread concurrently with a generation. A reader catching a half-written final line skips it (per-line `try/except`, same discipline as `_salvage_truncated`).
- **No live retrieval-replay endpoint** (dropped as scope creep): it would re-warm/use the embedding model under `_generate_lock` and add a lock-contending path. The stored trace already carries the pool; to re-run a query, use the existing `/api/patch` path.

### Performance: tracing never slows the live path

1. **Fire-and-forget after the response** (above), wrapped in `try/except`→`log_message`, never re-raising — a trace-disk failure must not turn a good patch into a 500.
2. **No synchronous aggregation on the hot path** — generation writes one raw line; roll-ups computed lazily on dashboard read.
3. **Capture-not-compute** — `clamped_values`, `patch_injection_outcome`, `raw_output_text` are observations of existing control flow, not extra passes.

### Reading `eval/results/`

Read-only ground truth; the dashboard never writes there. Filenames are parsed *without opening* to build the manifest (`kind ∈ {recall, patch_accuracy, patch_ab, provenance, faithfulness, bakeoff, patch_quality_selftest, patch_quality_run}`); "latest per kind" = max-timestamp per group. Summary scalars via a fixed key map (`recall.overall_recall`, `patch_accuracy.mean_active_agreement`, `provenance.cited_ratio`, `bakeoff.totals`, `coverage_report.pct_cells_3plus`). Two caveats carried through to the UI (not flattened): recall MISS rows pass `matched`/`top_chunks` for D-029 staleness adjudication; bakeoff/faithfulness `label` surfaced verbatim so a flagged judge-artifact run is never presented as ratified.

### Touch points

- `src/ui/server.py` — add `GET` branches; add post-lock `trace_store.append`. ~30 lines.
- `src/ui/generate_patch.py` — return enriched trace (or `(result, trace)`); capture `final_chunks` at 152, LLM fields at 159-162; `clamped_values` + injection-outcome merge.
- `src/retrieve/search.py` — `trace` out-param on `patch_diverse_search`/`_diversify_actionable`.
- `src/ui/patch_schema.py` — optional `meta` out-param on `validate_changes` (public return unchanged).
- `src/ui/trace.py` + `src/ui/trace_store.py` — **new**, stdlib only.
- `data/traces/` — **new**, gitignored.
- `src/ui/static/{base.css, dash.html, dash.css, dash.js}` — **new**; `studio.html` re-points to `base.css`.

No new dependencies, no build step, no second process, no datastore.

---

## 7. Implementation Roadmap, Milestones & Risks

Ordering principle: **instrumentation before UI, offline artifacts before live wiring, highest-diagnostic-value fields first.** Each milestone ships independent value.

### Dependency graph

```
M0 (trace logging, no UI) ──┬─> M1 (Trace Explorer)
                            └─> M2 (Overview + aggregates) ──> M3 (Run-Diff)
M4 (Corpus + Golden) ── reads eval/results + chunks.jsonl, independent of M0 ──┘
```

- M1, M2 hard-depend on M0. M3 depends on M2. M4 is independent (reads artifacts that exist today) but wants M1's `base.css` + route scaffolding.

### M0 — Instrumentation + Trace Logging (zero UI) · effort M

- `src/ui/trace.py` (`emit()` → **default-ON, failure-isolated**, `P6_TRACE=0` to disable; daily JSONL under `data/traces/`).
- One rich record emitted **after the response is sent** (envelope built in `server.py`, body assembled around `generate_patch.py:165`), with `final_chunks` captured at `:152` and the search.py out-param data merged in.
- **The three new computations:** `clamped_values` (`patch_schema.py:312`, via `validate_changes` `meta` out-param — public return unchanged), `patch_injection_outcome`+`candidates_below_floor` (`search.py:216`, via `_diversify_actionable` `trace` out-param; below-floor list computed separately), `narrated_not_delivered`.
- Post-hoc flags from data already present: `mixer_all_down`, `sysex.outcome` (replace the swallowed `except` in `_sysex_for`).
- **Files:** `generate_patch.py`, `patch_schema.py`, `search.py`, new `trace.py`/`trace_store.py`, `.gitignore`.
- **Value (no UI):** `grep`/`jq` over `data/traces/*.jsonl` answers "why all-general?" (`patch_injection_outcome`) and "was my cutoff clamped?" (`clamped_values`) — questions the code cannot answer today.

### M1 — Trace Explorer · effort M

- New static trio `dash.{html,css,js}` (Studio idiom: `$`/`sleep`, `fetch`+`res.json()`+`(!res.ok||data.error)`, `innerHTML` templates). Factor `base.css` (modern-surround tokens only); re-point `studio.html`.
- Routes `GET /api/traces` + `GET /api/trace/{id}`.
- `.workspace` grid + 14-stage timeline (the `expand` stage is **absent** — off-path) + 384px raw-field rail; provenance badges; all-general lights `--warm-2`.
- **`unmatched_citations` ships here, not in the first PR** (depends on the `real_patch_block` return-widening — §2.4).
- **Value:** click any patch → see the lever.

### M2 — Aggregate Metrics + Overview · effort M–L

- `GET /api/overview` (live rolling rates; corpus dead-chunk join **excluded**) + eval-results loader (glob/parse filename → latest-per-kind, closing that gap).
- KPI tiles (v1 recall@5 / patch active-agreement / provenance cited_ratio / coverage), flow-health strip, recent-traces list linking into M1.
- **Honesty affordances are deliverables, not polish:** provisional badges + caveats on judge/decoded-selector numbers; the bake-off citation-stripper artifact flagged (D-014/D-019/D-021).
- **Value:** one screen ties live silent-failure rates to offline accuracy.

### M3 — Experiment / Run-Diff · effort M

- `GET /api/eval/runs?kind` + `GET /api/eval/diff?a&b`; A/B `.zoom` selector; HIT→MISS drill-down with both runs' `top_chunks` side by side (D-027).
- Eval-staleness disambiguation (D-029) flag on recall MISS rows. v1-recall trend sparkline (D-024/D-027/D-029/D-035 history).
- **Value:** "did this wave help or just dilute?" in one click, staleness intact.

### M4 — Corpus Health + Golden tooling · effort L (independent)

- `GET /api/corpus` (utilization, dead-chunk list, per-source frequency — joining `chunks.jsonl` against pooled `top_chunks`; **lazy, on view-open**). Coverage heatmap (`coverage_report.json`; **timestamp the writer** so trend becomes possible). Golden inventory + live `check_targets.py` gate + promote-to-golden (writes valid `{source_type, match}` targets from `final_chunks`, ratified before append, D-015).
- **Files:** `server.py`, `dash.{js,css}`, `eval/coverage_report.py` (timestamp output).
- **Value:** the corpus lever made actionable.

### Risks & mitigations

| Risk | Mitigation |
|---|---|
| Tracing overhead on the live path | Write one pre-serialized line **after** the response, **outside `_generate_lock`**; all fields are already-computed values; dwarfed by the multi-second Sonnet call. |
| Trace-log growth | Daily-rotated, gitignored; `raw_output_text` capped (2KB+2KB); `/api/overview` mtime-memoized. |
| Breaking eval determinism | `validate_changes` keeps `(clean, problems)` byte-identical; clamps via an **optional `meta` out-param**; the dashboard reads artifacts, never re-runs eval. |
| Scope creep vs ethos | Every route stdlib `_send_json`; every view the vanilla trio; every dataset an existing file or `data/traces`; charts hand-rolled SVG/CSS; **no LangChain, no DB, no replay endpoint**. |
| Flattering-but-junk numbers (pre-QA 1.000 lesson) | Provisional/judge-artifact flagging is an M2 **deliverable**; D-029 staleness gets a `.tip`, never a bare red dot. |
| Two-fake-devices clash | `base.css` excludes `--face`/`--cream`/`--seg`/`.dial`/`.dispwin`; dashboard uses modern-surround only. |

### Non-goals

No multi-user/hosted/auth; no new datastore/ORM/telemetry (no SQLite unless the §6 trip-point is hit); no audio rendering/embeddings/perceptual metrics (v3, FP-1/D-021); no editing v1 golden targets to move the tripwire (D-015); no orchestration/scheduler to auto-run evals; no write-back to corpus/index; **no LangChain or any RAG framework**; **no live retrieval-replay**.

### Smallest first PR

**M0 minus the two return-arity changes** — the lowest-risk slice that touches no eval-affecting code:

- Add `src/ui/trace.py` (`emit()` → failure-isolated daily JSONL).
- One `emit(...)` at `generate_patch.py:165` carrying **only fields in scope there**: `query`, `final_chunks` (captured at `:152`), `patch.changes`/`resolved_nondefault`/`change_count`, `problems`, `source_distribution`, `grounding_mode`, `latency_ms`, `trace_id` (`{YYYYMMDD}-{HHMMSS}-{6hex}`), `ts` — plus the cheap derived flags `mixer_all_down` and `narrated_not_delivered`.
- Capture `stop_reason`/`usage_output_tokens`/`request_id` from `msg` at `:159-162` (read-only).
- `data/traces/` to `.gitignore`. **No UI, no route, no `search.py`/`validate_changes` signature changes** (those land in the second PR with caller updates and a deterministic-output regression check; `unmatched_citations` and the search.py-sourced pool/rerank/diversify fields land then too).

**Why this slice:** reversible (flag-off no-op), zero new deps, every eval script byte-identical, and on day one it answers the single highest-value question — *"why did this patch cite only general synthesis?"* — from `source_distribution` and (once the second PR lands `patch_injection_outcome`) the upstream cause, validating the whole observability premise before any pixel is drawn.
