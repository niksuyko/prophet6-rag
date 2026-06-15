# Prophet-6 RAG v2 — High-Accuracy Synth-Recipe Corpus Plan

A phased build plan for expanding the v1 knowledge engine into a comprehensive, *measured*
synth-recipe corpus. Written in the same style as `prophet6_rag_plan.md` (v1): eval first,
one measured change at a time, decision-log entries before code, human gates restored
(the v1 waiver in decisions.md D-019 was explicitly "for now").

**v2 thesis:** v1 proved grounding wins where hallucination risk concentrates (bake-off
B1 factual: 11–0) and loses where the corpus holds one narrow answer per recipe topic
(B2 recipes: 3–7, B3 cross-synth: 4–6 — classified as acquisition-depth gaps in
`eval/failure_analysis_v1.md`). The patch designer (D-020) made the gap visible per
parameter: ~5 of 29 changes in the Juno-pad test carried corpus citations; the rest were
honest "general synthesis" badges. v2 closes that gap by converting prose into structure:
real patches as corpus objects, recipe literature at depth, and a cross-synth translation
layer — with an eval that can tell the difference.

**Scope exclusions (explicit):**
- **Raw audio is deferred** — no audio rendering, no audio embeddings (CLAP-style), no
  perceptual/audio-similarity eval, no hardware-in-the-loop rendering. The text-domain
  proxy is patch-level parameter accuracy (Phase A, step 3). Audio grounding remains the
  documented v3 candidate.
- Commissioned third-party sound designers (the builder is the human expert for gap-filling).
- Web UI changes beyond what patch-grounded generation requires.
- Second synth (still v-next, unchanged from v1).

**Success criteria (stated before any acquisition, per the v1 guardrail):**
1. B2 recipes bake-off flips from 3–7 to majority-RAG; B3 reaches ≥ parity.
2. Patch-designer provenance: majority of generated changes cite corpus sources
   (manual/reddit/article/patch badges) instead of "general synthesis".
3. No regression: the v1 41-query recall@5 stays ≥ 0.95 after every ingestion wave.
4. Coverage matrix (Phase A) ≥ 90% of cells backed by ≥ 3 independent recipe sources.

---

## Phase A — Eval Expansion (before any acquisition)

**Goal:** the measurement exists before the content does. Content you can't measure is
content you don't have.

1. **Coverage matrix.** Instrument families (bass, pad, brass, strings, keys, lead,
   percussion, FX/drone) × character adjectives (warm, aggressive, vintage, glassy,
   evolving, …). Stored as `eval/coverage_matrix.yaml`. This is simultaneously the
   acquisition shopping list, the eval taxonomy, and the final coverage report's rubric.
   **[HUMAN GATE: builder ratifies the matrix — it defines "comprehensive".]**
2. **Golden set v2: 41 → ~120+ queries**, weighted toward B2/B3 (the measured loss
   buckets). Source phrasings from r/synthrecipes titles and recipe-tutorial comment
   sections, same messy-real-queries rule as v1 Phase 0.
3. **New eval type: patch-level parameter accuracy.** Once recipes are structured
   (Phase B), a golden entry's expected target can be a *parameter set*, not just a chunk.
   Metric: per-parameter agreement between the generated patch and reference patch(es),
   reported by panel section (oscillators / mixer / filters / envelopes / mod / fx),
   with tolerance bands for continuous knobs (e.g., ±10 of 127) and exact match for
   switches/selects. This is the text-domain stand-in for the deferred audio eval.
4. **Integrity guards extended.** `check_targets.py` grows to cover new target types
   (patch ids, new source slugs) so every golden entry stays reachable on every rebuild —
   the D-015 lesson, institutionalized.
5. **Regression tripwire.** The v1 41-query recall@5 (0.951 production baseline) is re-run
   after *every* ingestion wave. Dilution is the known failure mode of growing a
   small, domain-tight corpus (D-017's lesson); this is the alarm that fires early.
6. **Milestone check:** coverage matrix ratified; golden_set v2 ≥ 120 entries passing
   `check_targets.py`; patch-accuracy metric defined in README before Phase B code exists.

---

## Phase B — Structured Patches as First-Class Corpus Objects (highest impact)

**Goal:** real, complete, machine-readable recipes in the corpus — the patch designer
stops inventing values and starts adapting patches known to be good.

1. **Sysex decoder.** P6 sysex → JSON parameter dict aligned to the 82-param ids in
   `src/ui/patch_schema.py`. The packed-data format and NRPN map are *already in the
   corpus* (manual Appendix C chunks) — the decoder is implemented from our own retrieval
   output, which is a nice dogfooding story. Round-trip test: decode → re-encode →
   byte-identical.
2. **Factory banks first** (500 presets): canonical, categorized, licensing-safe for
   private use. Then freely-shared community banks (Sequential forum, etc.) with full
   provenance in `data/raw/manifest.jsonl`, same immutability rule as v1.
   **[LICENSING: standing per-source review — commercial sound sets are excluded from
   anything published; the register lives in decisions.md entries.]**
3. **New chunk type `patch`** in `chunks.jsonl`: `{name, category, params{...}}` as
   metadata plus a *generated textual rendering* ("Brass patch: both oscs saw, detuned
   +7 cents, LPF cutoff 70, env amount +35, …") as the `text` field so existing BM25 +
   vector retrieval works unchanged over patches.
4. **Retrieval integration.** The source-diversity guarantee (D-016) gains a third group:
   top-k must include a patch chunk when the query is recipe-shaped and patches exist in
   the pool. Additionally: parameter-space nearest-neighbor search over decoded patches
   (cosine/L2 over normalized param vectors) as a second retrieval mode for the designer.
5. **Patch designer upgrade.** Generation prompt receives the nearest real patches and
   adapts them toward the request instead of inventing from INIT; new `patch:` provenance
   badge in the UI alongside manual/reddit/general.
6. **Hardware spot-check.** Load a sample of decoded patches on the builder's unit and
   confirm panel values match the decoded JSON.
   **[HUMAN GATE: builder verifies ~10 patches against hardware before `patch` chunks
   enter the production index.]**
7. **Measured A/B:** blind bake-off of patch-grounded vs. v1 pure-LLM patch generation on
   the recipe golden queries. Keep whichever wins (expectation: grounded), per the
   Phase-4 keep/remove rule.
8. **Milestone check:** decoder round-trips; ≥ 500 patches in corpus with provenance;
   hardware spot-check passed; A/B result recorded in `eval/results/` + decisions.md.

---

## Phase C — Recipe Literature, Complete

**Goal:** tutorial-depth text — the v1 failure analysis said "tutorial-depth content,
not more threads", and the few recipe citations v1 *did* produce came from general
(non-P6) tutorial articles.

Priority order by recipe density:

1. **Synth Secrets, all 63 parts** (Sound on Sound; partially ingested in v1 — the
   existing article chunker handles SoS HTML). The canonical theory-to-recipe corpus.
2. **Welsh's Synthesizer Cookbook** — tabular instrument-family recipes. Needs a
   table-aware chunker; the `td`-extraction work from the Anwander article chunker is the
   starting point. Commercial book: private-corpus only, flagged in the licensing register.
3. **Vintage factory patch books** (Prophet-5, Juno charts — structured recipes on paper).
   Transcribe to the Phase-B patch format with `source_synth` metadata so the Phase-E
   translation layer can route them. Transcription QA-sampled like any chunker output.
4. **Attack Magazine patch tutorials; r/synthrecipes full archive; Gearspace recipe
   threads.** The existing reddit/article pipelines mostly cover these (pullpush +
   old.reddit browser-UA tricks still apply; Gearspace was a v1 exclusion now in scope).
5. **Every source gets the v1 treatment:** quality filter, dedupe, manifest entry, and a
   30-chunk stranger-test QA sample per new source type.
   **[HUMAN GATE: builder QA-samples each new source type before it merges into
   `chunks.jsonl` — restoring the v1 Phase-2 gate.]**
6. **Milestone check:** all four source groups ingested with manifest entries; QA samples
   passed; v1 41-query recall@5 re-run ≥ 0.95 (tripwire); v2 golden recall recorded.

---

## Phase D — Video Mining (transcripts only — audio itself stays out of scope)

**Goal:** convert the largest untapped recipe medium (patch-from-scratch videos) into
structured recipe chunks, using transcripts only.

1. **Curated channel allowlist** (Espen Kraft, Starsky Carr, Anthony Marinelli, Doctor
   Mix, and similar patch-from-scratch channels), recorded in decisions.md with rationale.
2. **Transcripts** via published captions where available, ASR fallback otherwise.
   Transcripts are summarized/structured, never republished verbatim; every chunk links
   the timestamped source URL.
3. **LLM extraction pass:** transcript → structured recipe chunks (settings spoken aloud
   are surprisingly complete in this genre), emitting the Phase-B patch format where the
   video yields enough parameters, prose recipe chunks otherwise. Extraction is spot-checked
   against the video by the builder for a sample (~10 videos).
   **[HUMAN GATE: extraction spot-check before merge.]**
4. **Vision frame-reading of knob positions is the deferred stretch goal** — only pursued
   if a measured check shows transcript-only extraction leaves a parameter-completeness gap
   that patches (Phase B) don't already cover. Decision recorded either way.
5. **Milestone check:** allowlist ratified; ≥ 50 videos extracted; spot-check passed;
   recall tripwire re-run.

---

## Phase E — Cross-Synth Translation Table

**Goal:** B3 stops being a translation problem solved implicitly by prose and becomes
structured data.

1. **Curated-then-expanded mapping:** source-synth feature → P6 realization, e.g.
   Juno chorus → LFO→PW 1+2 + CHO effect; Minimoog ladder character → what the P6 filter
   can and can't do (caveat rows are first-class — the bake-off judge once invented a
   ladder filter; the table is where that error becomes impossible). Hand-curate the top
   ~15 synths, LLM-expand with builder review.
2. **Stored as its own chunk type** (`translation`), retrieved when `synths_mentioned`
   metadata or query phrasing is cross-synth-shaped; injected into the patch-designer
   prompt so non-P6 recipes (Phase C patch books, Phase D videos about other synths) are
   *adapted*, not copied.
3. **Each row cites sources** (corpus chunks or literature) — the table inherits the
   citation discipline, it doesn't bypass it.
   **[HUMAN GATE: builder reviews the expanded table; wrong mappings are worse than
   missing ones.]**
4. **Milestone check:** table covers the synths appearing in golden B3 queries; B3
   bake-off re-run recorded.

---

## Phase F — Measure, Prune, Conclude

**Goal:** the headline numbers, v2 edition — and removal of anything that didn't earn
its place.

1. **Full ladder re-run:** recall@5 (v1 41 + v2 golden set), faithfulness, B2/B3 bake-off,
   patch-level parameter accuracy, provenance ratio (corpus-cited vs. general-synthesis
   badges across a fixed query sample).
2. **Score against the success criteria at the top of this plan.** Each criterion gets a
   pass/fail line in README — no narrative substitutes for the table.
3. **Prune:** any ingestion wave or technique that regressed retrieval or didn't move its
   target metric gets the D-017 treatment — documented as a negative result and removed.
4. **Coverage report:** the Phase-A matrix rendered with per-cell source counts; gaps
   become the explicit v3 backlog (alongside deferred audio grounding).
5. **Write-up:** README case study updated; `docs/RAG_DECISIONS_EXPLAINED.md` gains a v2
   chapter (structured-vs-prose corpora, eval-as-tripwire, translation layers).
6. **Milestone check:** results tables in README; failure analysis v2 classified by stage
   (now including `decode` and `translation` as stages); decisions ratified.

---

## Sequencing

```
A ──► B ──► C ──┬──► D ──┐
                └──► E ──┴──► F
```

A → B → C run serially (eval first, biggest lever second). D and E parallelize after C.
The recall tripwire runs at the end of *every* ingestion wave, not just at phase ends.

## Stack Additions (v1 stack unchanged otherwise)

| Layer | Choice | Rationale |
|---|---|---|
| Sysex decode | Hand-written from manual Appendix C | Format spec already in corpus; round-trip testable |
| Patch similarity | NumPy over normalized param vectors | Same transparency rule as the v1 vector store |
| Table-aware chunking | Extend existing BeautifulSoup chunker | Welsh cookbook + patch charts are tabular |
| Video transcripts | Captions / ASR + LLM extraction | Transcript-only; no audio pipeline |
| Translation table | YAML, builder-reviewed | Structured, citable, prompt-injectable |

## Guardrails (v1 guardrails apply; v2 additions)

- **Structure over prose:** when a source can yield a parameter set, ingest the parameter
  set; the textual rendering exists for retrieval, not as the ground truth.
- **Tripwire discipline:** no ingestion wave merges without the v1 recall re-run.
- **Provenance is a metric:** the general-synthesis badge ratio is tracked per release,
  not just observed anecdotally.
- **Human gates restored:** coverage-matrix ratification, hardware patch spot-check,
  per-source QA samples, video-extraction spot-check, translation-table review. D-019's
  waiver does not carry forward.
- **Licensing register:** every source's terms reviewed and recorded before ingestion;
  commercial content never leaves the private corpus.
- **Audio stays out:** any temptation to "just render one patch" goes to the v3 backlog —
  scope discipline is the v1 habit that made v1 finish.
