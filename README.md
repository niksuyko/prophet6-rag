# Prophet-6 Patch Designer

*Describe a sound in plain English — "warm Juno-style chorus pad with slow movement" — and get a
real, playable Sequential Prophet-6 patch: every knob and switch set on a faithful on-screen front
panel, each move traced to the source that justified it, ready to send to the hardware over MIDI.*

Under the hood it's a retrieval-augmented generation (RAG) system for one synthesizer, built on a
single principle: **generation is grounded in a curated corpus and measured against an ungrounded
baseline at every step.**

## Thesis

Base LLMs answer fluently but unreliably on hardware-specific synth knowledge — parameter behavior,
menu paths, community-discovered fixes, patch recipes. This system grounds every patch and answer in
a curated Prophet-6 corpus (the official manual, community threads, decoded factory patches, tutorial
transcripts) and treats **evaluation as a first-class deliverable**: nothing ships on vibes; each
change is kept or rejected on a measured number.

## What it does

**Patch creation — the main capability.** Open the Studio, type a sound, and the system designs a
complete patch and animates it onto a hardware-accurate panel, knob by knob.

![Generated patch on the visual panel](docs/patch_panel_demo.png)

- **Grounded, and honest about it.** A sidebar explains every change and badges its provenance — a
  **manual** / **reddit** / **patch** corpus citation, or an honest `general synthesis` tag when the
  move came from the model's own knowledge rather than the corpus. You can see exactly how much of a
  patch is backed by real Prophet-6 facts.
- **A faithful front panel.** 86 parameters across 17 sections, laid out to match the real desktop
  module — the control bands, HPF above LPF, LED destination pairs, red 7-segment displays using the
  manual's actual codes (`bbd`, `CHO`, `FR`…). Every value is validated and clamped server-side; an
  out-of-range or unknown parameter never reaches the panel.
- **Send it to hardware.** A MIDI toggle pushes the patch to a connected Prophet-6 as an edit-buffer
  dump — loads instantly, never overwrites a saved program. The sysex encoder is the exact inverse of
  the decoder (`decode(encode(p)) == p` across all 771 patches), and the FX byte mappings were
  confirmed against real hardware captures (see `docs/KNOWN_ISSUES.md`).
- **Save & load presets.** Name and store patches you like, then reload them — or push them straight
  to the hardware — later.

**Grounded Q&A (secondary).** `python src/generate/ask.py "what does slop do?"` answers Prophet-6
questions with inline citations, and says *"my corpus doesn't cover this"* rather than inventing specs.

## How it works — the pipeline

```
acquire  →  chunk  →  embed + index  →  retrieve  →  ground  →  generate  →  validate
raw sources  chunks.jsonl  BGE vectors    hybrid       real        schema-      clamp to
(manual,     (the          + BM25         search +     factory     constrained  the panel's
 reddit,      contract)                   diversity    patches as  JSON         real ranges
 patches…)                                             exemplars
```

Each stage reads what the previous one wrote; `data/chunks/chunks.jsonl` is the contract between
processing and indexing. The patch path specifically:

1. **Retrieve** the most relevant chunks for the sound, fusing meaning-based (BGE embeddings) and
   keyword (BM25) search, with a diversity guarantee so the model sees the manual *and* community
   *and* a real patch — not three near-duplicates.
2. **Ground** — load the full settings of any retrieved factory patches so the model *adapts a
   known-good patch* instead of guessing from scratch (decisions.md D-024).
3. **Generate** — the LLM (Claude) writes a JSON patch constrained to the panel schema, citing a
   source for each change.
4. **Validate** — clamp/coerce every value to the synth's legal ranges before it reaches the panel.

The parameter schema (`src/ui/patch_schema.py`) does triple duty — it's the LLM's contract, the
server-side validator, *and* the panel layout — so the three can never drift apart.

**Corpus** (rebuildable, not bundled — see below): **25,544 chunks** — 24,000 reddit Q&A +
r/synthrecipes, 766 decoded factory/OMOM patches, 607 articles (incl. the complete Synth Secrets
series), 92 manual/addenda, 52 video transcripts, 15 cross-synth translations, 12 official-KB.

## Measured

The evaluation harness (`eval/`) was defined *before* the pipeline was built, and every retrieval
change was kept or removed on a number — including the negative results:

- **Retrieval recall@5: 0.90 → 0.95.** Hybrid BM25+vector fusion closed lexical gaps on jargon-heavy
  queries; a source-diversity guarantee recovered keyword-flooding regressions. Two textbook
  techniques were **measured and removed** for hurting this small, domain-tight corpus: LLM query
  decomposition (diluted the fused pool) and cross-encoder reranking (no gain over fusion).
- **Grounded beats ungrounded.** In a blind, position-randomized, citation-stripped judge comparison,
  RAG wins where hallucination concentrates — **11/11 factual queries**. (The base model insisted
  vintage mode "comes with every unit right out of the box"; it actually shipped years later in OS
  1.6.7.)
- **Faithfulness ~93% at the claim level**, with contradictions rare — failures are overwhelmingly
  *true-but-ungrounded* glue facts, not inventions.
- **The patch designer adapts real, named factory patches** instead of inventing values; corpus-cited
  provenance rose ~2.7× over the prose-only Q&A baseline.

Per-bucket tables and honest post-mortems live in `eval/results/*.json` and
`eval/failure_analysis_*.md`. (One example of the measurement ethos: a pre-cleanup corpus scored a
flattering 1.000 recall; removing ~180 junk chunks dropped it to 0.95 — two "hits" had been riding on
troll answers. The cleanup cost points and was correct anyway.)

## Observability dashboard

A local dashboard at `/dash.html` for debugging and improving patch accuracy: **replay any generation
stage-by-stage** (retrieval pool → grounding → LLM output → validation → provenance), **diff eval
runs** to catch regressions before they ship, and inspect **corpus coverage gaps**. Built for
developers new to RAG — every metric carries a plain-English hover explainer. Same stdlib server, no
new dependencies. Design: `docs/OBSERVABILITY_PLAN.md`.

## Run it

```bash
pip install -r requirements.txt          # numpy, sentence-transformers, anthropic, …
cp .env.example .env                     # set ANTHROPIC_API_KEY  (Windows: copy)

python src/ui/server.py                  # then open:
#   http://127.0.0.1:8765/studio.html    — the patch designer
#   http://127.0.0.1:8765/dash.html      — the observability dashboard
```

Patch generation and Q&A need `ANTHROPIC_API_KEY` + internet; the dashboard, MIDI capture, and presets
work offline. The first generation loads the embedding model (~30 s); after that it's retrieval + one
LLM call.

**Rebuild the corpus from scratch** (re-fetches public sources, records URL + date provenance):

```bash
python src/acquire/fetch_official.py     # manual + knowledge base
python src/acquire/fetch_reddit.py       # community threads
python src/acquire/fetch_articles.py     # recipe literature
python src/process/build_chunks.py       # → data/chunks/chunks.jsonl
python src/index/build_index.py          # → BGE embeddings + index
python src/evaluate/recall.py production 5 strat+div   # measure
```

## Data, licensing & reproducibility

**The corpus is reproducible, not bundled.** The ~1.3 GB of raw sources, chunks, and embeddings under
`data/` are **not committed — by policy, not omission:**

- **Licensing.** A register in `decisions.md` (D-021/D-023/D-025) marks several sources
  *private-corpus-only* (decoded patch data, article HTML, video captions) and excludes others outright
  (a commercial cookbook, paywalled magazines). The manual PDF and reddit content aren't ours to
  redistribute.
- **Size & signal.** The corpus is the project's *input*; the engineering and measurement are the
  deliverable.

What's in the repo: all pipeline code (`src/`), the full decision log, the eval harness, the golden
query sets (`eval/golden_set*.jsonl`), and the results (`eval/results/*.json`). The acquisition scripts
rebuild the corpus from the original public sources.

## Further reading

- **[decisions.md](decisions.md)** — the engineering log: every decision, the alternatives rejected,
  and the measured outcome.
- **[docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)** — open and resolved bugs, including the
  hardware-confirmed FX byte-map fixes.
- **[docs/OBSERVABILITY_PLAN.md](docs/OBSERVABILITY_PLAN.md)** — the dashboard design and metric catalog.
- **[prophet6_rag_v2_plan.md](prophet6_rag_v2_plan.md)** — the recipe-knowledge-base expansion plan.
