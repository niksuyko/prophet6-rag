# Prophet-6 RAG Knowledge Engine — Implementation Plan

A step-by-step build plan for a retrieval-augmented generation (RAG) service answering Prophet-6 questions from official documentation and community knowledge. Written for a first-time RAG builder; contains enough implementation detail that an LLM assistant can help execute any step when given this document as context.

**Project thesis:** Base LLMs answer fluently but unreliably on hardware-specific synth knowledge (parameter behavior, menu paths, community-discovered fixes, patch recipes). This system grounds answers in a curated corpus and *measures* that it outperforms the ungrounded baseline. Evaluation is a first-class deliverable, not an afterthought.

**Core principle for the builder:** Code is LLM-generated; decisions are human-owned. Before any resume-relevant component is generated (chunking strategy, retrieval techniques, eval design, quality thresholds), the builder writes the decision first — what approach, what alternatives were rejected, why — in `decisions.md`, then directs the LLM to implement that decision. After generation, the builder must be able to walk through the resulting code and explain every non-trivial line; anything that can't be explained gets re-prompted or rewritten until it can be. Eval results are interpreted by the human, never summarized by the LLM unseen.

---

## Phase 0 — Project Setup & Golden Dataset (build the eval first)

**Goal:** A repo skeleton and a golden evaluation dataset that defines what "working" means before any pipeline exists.

1. **Repo structure.** Create a pipeline-as-stages layout where each stage reads files written by the previous stage and writes its own. Nothing re-runs unnecessarily.
   ```
   p6-rag/
   ├── data/
   │   ├── raw/          # untouched downloads (PDFs, reddit JSON)
   │   ├── processed/    # cleaned text, one file per source doc
   │   └── chunks/       # chunks.jsonl — the contract between processing and embedding
   ├── eval/
   │   ├── golden_set.jsonl
   │   └── results/      # timestamped eval run outputs
   ├── src/
   │   ├── acquire/      # one script per source (manual, reddit)
   │   ├── process/      # chunkers, cleaners
   │   ├── index/        # embedding + vector store build
   │   ├── retrieve/     # search logic
   │   ├── generate/     # answer generation w/ citations
   │   └── evaluate/     # eval harness
   ├── decisions.md      # the decision log
   └── README.md
   ```
2. **Build the golden dataset (30–50 queries).** Each entry: `{query, bucket, expected_source, expected_section_or_thread, notes}`. Use the four query buckets:
   - **Bucket 1 — Factual/manual lookup** (e.g., "What does the Slop parameter do?")
   - **Bucket 2 — Sound-design recipes** (e.g., "Warm pad with movement — settings?")
   - **Bucket 3 — Emulative/cross-synth** (e.g., "Juno-style chorus pad on the P6?")
   - **Bucket 4 — Troubleshooting/workflow** (e.g., "Velocity doesn't affect anything — why?")
   Source real phrasings from r/synthrecipes and r/synthesizers where possible (messy real queries > clean invented ones). Aim for ~10–12 per bucket.
3. **Define metrics now:**
   - **Retrieval recall@k** (k=5): does the expected source/section appear in the top-k retrieved chunks?
   - **Answer faithfulness:** is every claim in the generated answer supported by a retrieved chunk? (LLM-as-judge, later phase.)
   - **Baseline comparison:** answer quality of base LLM with no retrieval vs. the RAG system, judged per-bucket.
4. **Milestone check:** golden_set.jsonl exists with ≥30 entries; metrics defined in README; decision log started.

---

## Phase 1 — Data Acquisition

**Goal:** Raw corpus on disk in `data/raw/`, untouched and re-processable forever.

1. **Prophet-6 Operation Manual.** Download the official PDF from Sequential's website. Also grab the published OS release notes / addenda (used for troubleshooting + "what changed" queries).
2. **Reddit (primary community source).** Two complementary methods:
   - **Bulk dumps (preferred for completeness):** Download the historical subreddit dumps for r/synthrecipes (small subreddit) from Academic Torrents ("subreddit data dumps", Pushshift-lineage, zstd-compressed NDJSON). Filter locally for Prophet-6 mentions. No rate limits, no missed posts.
   - **Reddit API via PRAW (for recent posts):** Register a script app at reddit.com/prefs/apps. Search r/synthrecipes, r/synthesizers, r/sequential with multiple query variants (`"prophet 6"`, `"prophet-6"`, `prophet6`, `P6` — cast wide, disambiguate later). For each hit, expand all comments (`submission.comments.replace_more(limit=None)`) and save one raw JSON file per thread: title, selftext, score, permalink, created_utc, full comment tree with scores.
3. **Tier-3 emulation-target content.** Collect a modest set of documents about the *sounds* the P6 is asked to imitate (Juno chorus pads, OB brass, Moog bass): Sound on Sound "Synth Secrets" articles, relevant Reddit threads about those classic sounds. Needed for Bucket-3 queries.
4. **Deliberately deferred to v2:** Gearspace owners thread (manual save-and-parse if eval later shows troubleshooting gaps), YouTube tutorial transcripts via yt-dlp.
5. **Rules:** Save everything raw. No cleaning or filtering at this stage. Record source URL + retrieval date for every file.
6. **Milestone check:** manual PDF + release notes + ≥100 candidate Reddit threads + a handful of Tier-3 docs sitting in `data/raw/`.

---

## Phase 2 — Processing & Chunking

**Goal:** A single `chunks.jsonl` file — one chunk per line with text + metadata. This file is the contract consumed by the indexing stage.

1. **Define the chunk schema** (every chunk, regardless of source):
   ```json
   {
     "chunk_id": "stable unique id",
     "text": "self-contained passage, context prepended",
     "source_type": "manual | reddit | article",
     "source_url": "...",
     "section": "manual section name or null",
     "synths_mentioned": ["prophet-6", "juno-106"],
     "score": 12,
     "created": "ISO date or null"
   }
   ```
2. **Manual chunker (structure-aware).** Extract with `pymupdf` (`fitz`). Detect section headings via font size/bold flags (inspect a few pages to learn the manual's body vs. heading sizes; write rules from that). One chunk per section, target 300–800 tokens; sub-split oversized sections on paragraph boundaries with small overlap. **Prepend context into the chunk text itself:** `"Prophet-6 Manual — Arpeggiator: <text>"` so pronouns and bare parameter names embed meaningfully.
   - *Validation trick:* also hand-write a small YAML table-of-contents map (section → page range) for the P6 manual; use it as a correctness test for the automated chunker. (For one 60-page manual the hand map alone is viable; build the automated path anyway for the scaling story and to onboard synth #2 later.)
3. **Reddit chunker (Q+A pairing).** One chunk per (question + qualifying answer) pair. Repeat the question text in every chunk (queries match questions semantically; orphaned answers are unretrievable). Starting quality filter: comment score ≥ 3 and length > 100 chars — tune later against eval. Detect and tag synth mentions for metadata (handle the "P6"/"Prophet" ambiguity here, not at acquisition).
4. **Cleaning pass:** strip page headers/footers and boilerplate from PDF text, markdown artifacts and bot comments from Reddit, dedupe near-identical chunks.
5. **Human QA loop (mandatory):** sample 30 random chunks from the output. Test for each: *would this passage make sense to a stranger with zero context?* Fix the chunker, regenerate, re-sample. Expect 2–3 loops.
6. **Note on libraries:** write both chunkers by hand (~50 lines each). Generic splitters like `RecursiveCharacterTextSplitter` are acceptable only as the oversized-section fallback. The two main strategies here are document-specific by design — that's the point.
7. **Milestone check:** `chunks.jsonl` exists; sampled chunks pass the stranger test; chunk counts per source logged.

---

## Phase 3 — Embedding & Indexing

**Goal:** A queryable vector index built from `chunks.jsonl`.

1. **Embedding model:** start with a strong open-source sentence embedding model run locally (e.g., a current top performer on the MTEB retrieval leaderboard in the small/medium size class — check the leaderboard at build time) via `sentence-transformers`. Local = free re-embedding, which matters because chunking will change repeatedly. Record model name + dimension in the index metadata. A hosted embedding API is an acceptable alternative; the architecture is identical.
2. **Vector store:** keep it simple. Options in ascending complexity: NumPy matrix + cosine similarity (fully transparent, fine for a few thousand chunks — recommended first so you've implemented search yourself), then ChromaDB or LanceDB (embedded, no server) for metadata filtering convenience. A client-server vector DB is unnecessary at this scale; choosing *not* to use one is a defensible decision-log entry.
3. **Build script:** reads `chunks.jsonl` → embeds `text` field (batch) → writes vectors + metadata keyed by `chunk_id`. Re-runnable from scratch in one command.
4. **First measurement (recall baseline):** run the golden set through pure vector search. Record recall@5 overall and per-bucket in `eval/results/`. This number is the project's "before" picture — expect Bucket 1 to score high and Bucket 3 to score poorly. That gap is the roadmap for Phase 4.
5. **Milestone check:** index builds in one command; baseline recall@5 recorded per bucket.

---

## Phase 4 — Retrieval Layer

**Goal:** A `retrieve(query) -> list[Chunk]` function that measurably beats the Phase-3 baseline.

Implement and measure incrementally — one technique at a time, eval after each:

1. **Hybrid search.** Add BM25 keyword search (`rank_bm25` or similar) alongside vector search; merge with reciprocal rank fusion. Rationale: exact terms like "Slop", "Poly Mod", "OS 1.x" need lexical matching; concepts need semantic. Measure recall delta.
2. **Metadata filtering.** Use chunk metadata to constrain or boost: e.g., manual-source chunks for Bucket-1-style queries, `synths_mentioned` filters for cross-synth queries. Start with simple heuristics; an LLM-based query classifier is an optional upgrade.
3. **Query rewriting (targets Bucket 3).** Before retrieval, expand/decompose the query with an LLM: "Juno-style chorus pad on P6" → sub-queries about (a) what characterizes a Juno chorus pad, (b) P6 effects/ensemble options. Retrieve per sub-query, merge. Measure Bucket-3 recall before/after — this is expected to be the headline improvement for the hardest bucket.
4. **Reranking (optional, high-value).** Retrieve top ~25 with hybrid search, rerank to top 5 with a cross-encoder reranker model. Measure precision improvement.
5. **Rule:** every technique gets a before/after eval run saved to `eval/results/` and a decision-log entry. Anything that doesn't move the numbers gets removed — negative results are interview gold.
6. **Milestone check:** recall@5 meaningfully above Phase-3 baseline overall; Bucket-3 specifically improved; results table in README.

---

## Phase 5 — Generation with Citations

**Goal:** Grounded answers with inline source citations.

1. **Prompt construction:** system prompt instructs the model to answer *only* from provided chunks, cite chunk sources inline (e.g., `[Manual — Arpeggiator]`, `[reddit permalink]`), and explicitly say when retrieved context is insufficient rather than improvising. Pass top-k chunks with their metadata.
2. **Model:** any capable chat model via API (e.g., Claude API — already in your stack). Keep the generation layer thin; the system's quality lives in retrieval.
3. **Insufficient-context behavior:** define and test the refusal path ("my corpus doesn't cover this") with deliberately out-of-corpus queries. A system that knows what it doesn't know demos extremely well.
4. **Interface:** a CLI (`python ask.py "what does slop do?"`) is fully sufficient for v1. A minimal web UI is optional polish, last.
5. **Milestone check:** end-to-end answers with citations; out-of-corpus queries correctly declined.

---

## Phase 6 — End-to-End Evaluation & Baseline Comparison

**Goal:** The headline numbers.

1. **Faithfulness eval (LLM-as-judge):** for each golden query, generate an answer, then have a judge model verify each claim against the retrieved chunks. Score = % of answers fully supported. Spot-check ~15 judge verdicts by hand to validate the judge itself.
2. **RAG vs. base-model bake-off:** answer every golden query two ways — base model with no retrieval vs. the full system. Blind-judge for correctness/usefulness (LLM judge + your own domain knowledge as P6 owner). Report per-bucket: expect the largest wins on Buckets 3–4 and model-specific facts.
3. **Failure analysis:** for every miss, classify the failure stage (acquisition gap / chunking / retrieval / generation). This taxonomy directly feeds the write-up and interview stories.
4. **Milestone check:** results table — recall@5, faithfulness %, bake-off win rate, all per-bucket — committed to README.

---

## Phase 7 — Write-Up & Resume Translation

**Goal:** Make the work legible to hiring managers and interviewers.

1. **README as case study:** problem framing (why this domain genuinely needs RAG), architecture diagram, the metrics table, 2–3 before/after examples (including one where base LLM confidently hallucinates and the system answers correctly with citations), and a "what didn't work" section drawn from the decision log.
2. **Resume bullets — lead with measurement,** e.g.: *"Built a retrieval evaluation framework (golden dataset across 4 query types); improved recall@5 from X% to Y% via structure-aware chunking, hybrid BM25+vector search, and query decomposition"* and *"Demonstrated grounded answers outperforming an ungrounded LLM baseline on N% of domain queries via blind LLM-judged evaluation."*
3. **Interview prep from artifacts:** rehearse from the decision log — every entry is a "tell me about a tradeoff" answer; every negative result is a "what didn't work" answer. Run the blank-page test: re-draw the full pipeline and justify each component from memory.

---

## Suggested Stack Summary

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python | Ecosystem fit |
| PDF extraction | pymupdf (fitz) | Font metadata access for heading detection |
| Reddit | PRAW + Academic Torrents dumps | API for recent, dumps for completeness |
| Chunking | Hand-written (structure-aware + Q&A pairing) | Document-specific by design |
| Embeddings | Local sentence-transformers model (check MTEB leaderboard) | Free re-embedding during iteration |
| Vector search | NumPy cosine first → ChromaDB/LanceDB | Transparency first, convenience second |
| Keyword search | BM25 (rank_bm25) | Exact-term matching for jargon |
| Generation | Claude API | Thin layer; already in builder's stack |
| Eval | Custom harness + LLM-as-judge | The differentiating deliverable |

## Guardrails for the Builder

- Build the eval before the pipeline; measure after every change.
- **Decision-first generation:** write the decision-log entry *before* prompting the LLM to implement it. The prompt should encode your chosen approach, not ask the LLM to choose.
- **Explain-back rule:** for core components (chunkers, retrieval, eval harness), read the generated code and explain it back — to yourself, a friend, or an LLM playing skeptical interviewer. Re-prompt anything you can't defend.
- **Keep manual:** the chunk QA sampling loop (Phase 2, step 5), interpretation of every eval results table, and the failure-analysis classification (Phase 6, step 3). These are where understanding is actually built and cannot be delegated.
- Acquisition stays raw; processing stays rerunnable; chunks.jsonl is the contract.
- Every design choice → decision log. Every technique → before/after numbers. Every failure → classified.
- Scope discipline: one synth (Prophet-6), CLI interface, defer Gearspace/YouTube/web-UI to v2.
