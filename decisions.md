# Decision Log — Prophet-6 RAG Knowledge Engine

Decisions are written *before* implementation. Each entry: the decision, alternatives rejected, and why.
Entries drafted by the LLM assistant are marked **[DRAFT — needs human ratification]** until the builder signs off at a phase gate.

---

## D-001 — Project root layout (Phase 0)

**Status:** Approved
**Decision:** Use the existing `prophet-rag/` directory as the project root with the pipeline-as-stages layout from the plan (`data/raw → data/processed → data/chunks`, one `src/` package per stage). Each stage reads only the previous stage's files and writes its own.
**Alternatives rejected:** A monolithic notebook (no re-runnability, no stage contracts); an orchestration framework like Airflow/Prefect (absurd overkill for a single-machine, file-based pipeline).
**Why:** File contracts between stages mean nothing re-runs unnecessarily and any stage can be debugged in isolation by inspecting its input files.

## D-002 — Golden dataset before pipeline (Phase 0)

**Status:** Approved
**Decision:** Build a 40-query golden set (~10 per bucket) before any acquisition/chunking code exists. Query phrasings sourced from real Reddit threads (r/synthrecipes, r/synthesizers, r/sequential) wherever possible; invented queries only to fill bucket gaps, marked `"phrasing": "invented"` in the entry.
**Alternatives rejected:** Writing the eval set after seeing the corpus (leaks corpus contents into query design — the eval would test what we happened to collect, not what users ask); fully synthetic LLM-generated queries (too clean; real queries are messy, underspecified, and use community slang like "P6" and "slop").
**Why:** The eval defines "working" before the system exists, so every later technique gets an honest before/after number.

## D-003 — Metrics (Phase 0)

**Status:** Approved
**Decision:** Three metrics, defined in README before implementation:
1. **Retrieval recall@5** — expected source/section appears in top-5 retrieved chunks. Matching rule: chunk-level metadata match (source_url for reddit/article, section name substring for manual), not text overlap.
2. **Answer faithfulness** — % of generated answers in which every claim is supported by a retrieved chunk (LLM-as-judge, validated by human spot-check of ~15 verdicts).
3. **Bake-off win rate** — blind LLM-judge comparison of base-model answer vs. RAG answer per golden query, reported per bucket.
**Alternatives rejected:** MRR/nDCG (more granular but harder to explain and the golden set has one expected target per query, so recall@k is the natural fit); ROUGE/BLEU vs. reference answers (we have no gold answers, and string overlap is meaningless for sound-design advice).
**Why:** Each metric maps to one failure mode: recall = retrieval misses, faithfulness = hallucination despite retrieval, bake-off = "did grounding actually help?"

## D-004 — Reddit acquisition without API credentials (Phase 1)

**Status:** Approved, will look into API for Phase 2
**Decision:** Acquire Reddit threads via two unauthenticated paths, no PRAW: (1) **pullpush.io** (Pushshift-successor JSON API) for submission search and full comment retrieval — clean JSON, covers ~2015→mid-2025; (2) **old.reddit.com HTML scraping** from this machine (verified to return 200 with a browser User-Agent) as fallback for threads pullpush misses and for post-mid-2025 posts. Seed list: 85+ thread permalinks already identified by targeted search, plus programmatic search with query variants (`"prophet 6"`, `"prophet-6"`, `prophet6`, `P6`). One raw JSON file per thread: title, selftext, score, permalink, created_utc, full comment tree with scores. Polite rate limiting (≥1.5s between requests).
**Alternatives rejected:** PRAW/OAuth (works, but requires registering an app — credentials add friction and the plan's purpose for the API, recency, is covered by old.reddit scraping); Academic Torrents bulk dumps (most complete, but requires a torrent client and multi-GB downloads to extract a few hundred threads — deferred unless eval shows coverage gaps); reddit.com `.json` endpoints (verified 403 unauthenticated from this machine).
**Why:** Zero-credential paths verified working from this environment; the dump option remains available for v2 if recall analysis shows acquisition gaps. Note: r/sequential is not publicly accessible (banned/empty) — corpus draws from r/synthesizers and r/synthrecipes; the official Sequential forum is a v2 candidate if troubleshooting coverage is thin.

## D-005 — Golden set construction order (Phase 0/1 sequencing)

**Status:** Approved
**Decision:** Download the official manual (Phase 1, step 1) *before* finalizing the golden set, so Bucket-1 entries can reference real manual section names as `expected_section`. Bucket 2–4 entries reference real Reddit thread permalinks found by search. Golden-set queries are paraphrased from verbatim thread titles/selftext (messy phrasing preserved); threads used as eval targets are force-included in the acquisition seed list so the eval never fails for trivial absence-from-corpus reasons.
**Alternatives rejected:** Inventing section names from memory (eval would silently mis-score on naming mismatches); excluding eval-target threads from the corpus (would measure acquisition luck, not retrieval quality — the plan's recall metric presumes the answer exists in the corpus).
**Why:** recall@5 is only meaningful if the expected target is actually indexable; matching rules need exact metadata, not guesses.

## D-006 — Golden-set schema: multi-target matching (Phase 0)

**Status:** Approved
**Decision:** Each golden entry carries `expected_targets`: a *list* of acceptable targets, each `{source_type, match}`. recall@5 counts a hit if **any** target matches a top-5 chunk. Matching rules: `manual` → case-insensitive substring of the chunk's `section`; `reddit` → thread id equals the chunk's `source_id`; `article`/`official_kb` → slug equals `source_id`. Entries also carry `phrasing: real|paraphrased|invented` so we can later check whether messy real queries score differently from clean invented ones.
**Alternatives rejected:** Single expected target (plan's literal schema) — many questions are legitimately answered in both the manual and a thread, and penalizing the retriever for finding the *other* correct source measures naming luck, not retrieval; answer-text overlap matching (fragile, rewards verbosity).
**Why:** The metric should measure "did we surface a passage that answers the question", not "did we surface the one passage I happened to write down".

## D-007 — Manual chunker anchors on the embedded PDF TOC (Phase 2)

**Status:** Approved
**Decision:** The Prophet-6 manual PDF carries an embedded TOC (78 entries, inspected and sane). The chunker uses it as the section map: locate each heading on its page via text search, slice text between consecutive headings, one chunk per (sub)section, target 300–800 tokens (≈ words × 1.33), sub-split oversized sections on paragraph boundaries with 1-paragraph overlap. Context is prepended into chunk text: `"Prophet-6 Manual — <Section>: …"` (subsections get `"<Parent> — <Sub>"`). Page headers/footers stripped by position + pattern. Font-size heading detection (plan's original approach) is kept as the *fallback path* for PDFs without embedded TOCs — the OS addenda exercise it. A hand-checked YAML map of section → page range serves as a regression test for the chunker.
**Alternatives rejected:** Pure font-size heuristics as primary (strictly less reliable than the publisher's own TOC when one exists); fixed-size sliding window (destroys section semantics, the whole point of structure-aware chunking); page-granularity slicing (sections share pages).
**Why:** Use ground truth when the document provides it; keep the heuristic path because the scaling story (synth #2) needs it.

## D-008 — Reddit chunker: Q+A pairs with quality filter (Phase 2)

**Status:** Approved
**Decision:** One chunk per (question + qualifying answer) pair; question title + selftext repeated in every chunk of its thread. Qualifying answer: length > 100 chars, not a bot, and score ≥ 3 **when a trustworthy score exists** — pullpush scores are ingest-time snapshots and often undercount, so a missing/low pullpush score with substantial length (> 250 chars) still qualifies. Starting values; tuned against eval later. Synth mentions tagged via a regex dictionary over question+answer text ("P6" resolves to prophet-6 — within these subreddits the ambiguity is negligible). `chunk_id = reddit-<thread>-<comment>`.
**Alternatives rejected:** Whole-thread chunks (too long, mixes contradictory answers); answer-only chunks (orphaned answers are semantically unretrievable — queries match questions); strict score ≥ 3 everywhere (would silently drop most pullpush-sourced answers due to snapshot scores).
**Why:** Queries are questions; embedding question text with each answer is what makes them findable.

## D-009 — Article/KB chunker + merge & dedupe (Phase 2)

**Status:** Approved
**Decision:** HTML sources (Tier-3 articles + official Zendesk KB/OS-update pages) are extracted with BeautifulSoup (`<article>`/main-content first, boilerplate tags dropped), split on `h2/h3` headings, merged to 300–800-token chunks, context-prefixed with article title + section. Official support pages get `source_type: "official_kb"`. Each chunker writes `data/processed/chunks_<source>.jsonl`; a merge step cleans (mojibake, markdown artifacts, `[deleted]`), dedupes (exact normalized-hash + 8-gram shingle Jaccard > 0.85, keeping the higher-scored chunk), and writes the single contract file `data/chunks/chunks.jsonl`.
**Alternatives rejected:** Readability/trafilatura libraries (fine tools, but two selector rules cover our 18 pages and stay debuggable); skipping dedupe (the narly-sound thread alone is triple-posted).
**Why:** Keeps the chunks.jsonl contract single and clean while intermediate per-source files stay inspectable.

## D-010 — Embedding model + vector store (Phase 3)

**Status:** Approved
**Decision:** `BAAI/bge-base-en-v1.5` (768-dim) via sentence-transformers, run locally on CPU; queries get BGE's recommended retrieval prefix ("Represent this sentence for searching relevant passages: "), passages embedded bare, vectors L2-normalized. Vector store = a NumPy matrix + dot-product cosine search, persisted as `embeddings.npy` + row-aligned chunk metadata; model name/dim recorded in `index_meta.json`. Index rebuilds from `chunks.jsonl` in one command.
**Alternatives rejected:** Hosted embedding APIs (per-call cost discourages the many re-embeddings that chunker iteration requires; architecture is identical if we swap later); larger local models (CPU-only machine, corpus is ~2k chunks — retrieval quality bottleneck here is chunking/hybrid search, not embedding size); ChromaDB/LanceDB now (metadata filtering can come later; first implementation of search should be transparent enough to debug by printing the matrix); newest leaderboard models requiring remote code (avoid the dependency risk for marginal gains at this scale).
**Why:** Free re-embedding is the property that matters in the iteration loop, and a hand-rolled cosine search over a few thousand vectors is exact, fast, and fully explainable.

## D-011 — Hybrid search: BM25 + vector with reciprocal rank fusion (Phase 4, technique 1)

**Status:** Approved
**Decision:** Add BM25 (rank_bm25, `\w+` lowercase tokens) over chunk texts alongside vector search. Fuse with reciprocal rank fusion: each candidate scores `Σ 1/(60 + rank)` across the two rankers (top-50 from each), take top-k. RRF constant 60 = the standard default; not tuned unless eval demands it.
**Alternatives rejected:** Weighted score interpolation (cosine and BM25 scores live on incomparable scales; rank fusion sidesteps calibration entirely); replacing vector with BM25 (loses paraphrase matching that buckets 2–3 need).
**Why:** P6 jargon is lexically exact — "Slop", "Poly Mod", "OS 1.6.7", "vintage mode" — and embedding models blur exactly these. Measured before/after on recall@5; kept only if it moves the number.

## D-012 — Generation layer: thin, citation-forced, refusal-capable (Phase 5)

**Status:** Approved
**Decision:** Single Claude API call (`claude-sonnet-4-6` default, flag-overridable). The system prompt: answer ONLY from the provided chunks; cite inline using the bracket label each chunk is tagged with (`[Manual - Slop]`, `[reddit:1id23zb]`, `[article:musicradar_minimoog_bass]`); if the chunks don't contain the answer, say "My corpus doesn't cover this" + what IS nearby — never improvise from general knowledge. Top-k=5 chunks passed with metadata headers. Interface: `python src/generate/ask.py "question"` CLI.
**Alternatives rejected:** Bigger model by default (the system's quality lives in retrieval; generation is deliberately thin); agentic multi-step generation (overkill, harder to evaluate faithfulness); web UI (deferred to v2 per scope discipline).
**Why:** A system that knows what it doesn't know demos well and makes the faithfulness metric meaningful.

## D-013 — Faithfulness judge design (Phase 6)

**Status:** Approved
**Decision:** LLM-as-judge per answer: judge receives the question, the retrieved chunks, and the generated answer; extracts each factual claim; labels each claim supported / unsupported / contradicted by the chunks; answer is "faithful" iff zero unsupported+contradicted claims (refusals with no claims count as faithful). Judge = same model family, temperature 0, JSON output. Human validation: ~15 randomly sampled verdicts exported to a spot-check file for manual review before the number is reported.
**Alternatives rejected:** Answer-level single yes/no judgment (hides which claim failed; claim-level output feeds failure analysis); embedding-similarity faithfulness proxies (measure topicality, not support).
**Why:** Claim-level verdicts make the metric auditable — the human spot-check validates the judge itself, per the plan.
**Outcome (2026-06-11):** strict answer-level 53.7%, claim-level support 93.4% (30 unsupported /
456 claims), zero contradictions. Unsupported claims are dominated by true-but-ungrounded glue
knowledge (see `eval/failure_analysis_v1.md`); ~4 verdicts look judge-over-strict — spot-check
file generated for builder review.

## D-014 — Bake-off design: blind pairwise, position-randomized (Phase 6)

**Status:** Approved
**Decision:** For every golden query: answer (a) base model, no retrieval, same model+temperature, prompted to answer as a knowledgeable synth expert; (b) full RAG pipeline. Judge sees query + two answers labeled A/B with assignment randomized per query (seeded); judges correctness and usefulness for a Prophet-6 owner; verdict ∈ {A, B, tie}. Citations are stripped from the RAG answer before judging so the judge scores content, not formatting. Report RAG win/tie/loss per bucket. The builder (P6 owner) additionally hand-reviews verdicts where the judge and their own domain knowledge disagree.
**Alternatives rejected:** Grading each answer 1–10 independently (LLM judges are miscalibrated absolute graders; pairwise is the standard fix); judging with citations visible (judges reward citation formatting regardless of truth).
**Why:** Position bias and format bias are the two classic pairwise-judge failure modes; randomization and citation-stripping address both cheaply.
**Outcome (2026-06-11):** RAG 23 / base 18 / tie 0. Per bucket: B1 11-0 (clean sweep — grounding
wins where hallucination risk concentrates), B2 3-7 and B3 4-6 (base-model generic fluency beats
narrow thread retrieval — an acquisition-depth finding, not a retrieval failure), B4 5-5. At
least one judge rationale contained its own factual error (claimed the P6 has a ladder filter) —
flagged in the failure analysis for the builder's spot-check.

## D-015 — Golden-set repair after acquisition reality check (Phase 3 finding)

**Status:** Approved
**Decision:** The first full-corpus eval revealed that 7 golden queries were unreachable *by construction*: their target threads were deleted from reddit AND their comments were never archived by pullpush (verified live: "[deleted by user]" pages, 0 archived comments, both `link_id` formats). Repairs, each recorded in the entry's `notes`: (1) b2-q05 retargeted to the manual's Distortion section, which directly answers it; (2) b2-q01/b2-q07/b2-q09/b3-q07/b3-q08 replaced with real queries whose source threads exist in the corpus with substantive answers; (3) `PULLPUSH_LEN_FALLBACK` tuned 250→150 chars — the canonical answer to b4-q07 (MIDI clock loop, 222 chars) and similar concise troubleshooting answers were being dropped; troubleshooting answers are legitimately short. A standing `check_targets.py` integrity script now fails the build if any golden entry loses all reachable targets. Also: the acquisition fallback was fixed to scrape old.reddit whenever pullpush returns zero comments (17 threads re-fetched).
**Alternatives rejected:** Keeping unreachable entries as a permanent recall ceiling (would pollute the *retrieval* metric with *acquisition* losses — the failure taxonomy keeps these stages separate); Academic Torrents dumps to recover the deleted threads (multi-GB torrent for 5 threads; remains the v2 path if more gaps appear).
**Why:** recall@5 must measure retrieval against an answerable corpus; deleted-content losses are an acquisition-stage finding (now documented) rather than a retrieval penalty.

## D-016 — Source-diversity guarantee in top-k (Phase 4, technique 2: metadata)

**Status:** [DRAFT — needs human ratification]
**Decision:** After hybrid fusion, enforce source-type diversity: if the top-k contains no
manual/official chunk but one exists in the top-25 pool, swap it in for the lowest-ranked
result (and symmetrically for reddit). Rationale: the one hybrid regression (b4-q01) is a
troubleshooting query where BM25 keyword-flooding filled all 5 slots with reddit chunks while
the authoritative manual section sat just outside. A guaranteed source mix hedges every query
type without query classification.
**Alternatives rejected:** Per-bucket query classifiers routing to source filters (more
machinery, needs labeled queries, and the golden set is too small to train/validate it);
boosting manual chunks globally in RRF weights (overfits the one observed regression and
penalizes buckets 2–3 where community answers are the right source).
**Why:** Cheapest intervention that addresses the observed failure mode; measured before/after.
**Outcome (2026-06-11):** recall@5 0.976 → **1.000** (recovered b4-q01, no regressions). KEPT — production mode is `hybrid+div`.
**Post-QA amendment:** after the chunk-QA cleanup removed ~180 junk chunks (and an id-dedupe
bug fix), the final-corpus ladder is vector 0.902 → hybrid 0.927 → hybrid+div **0.951**.
Two pre-QA hits (b2-q04, b4-q01) had been riding on junk chunks; the cleaner corpus scores
lower and is the honest number. Technique ordering unchanged.

## D-017 — LLM query rewriting (Phase 4, technique 3)

**Status:** [DRAFT — needs human ratification]
**Decision:** Expand each query into 2–3 sub-queries with claude-haiku-4-5 (cheap, fast):
decompose cross-synth questions into (a) what characterizes the target sound and (b) which
P6 features produce it; expand terse queries with synonyms. Retrieve per sub-query (hybrid),
merge via RRF across sub-query result lists. Cached to disk per query to keep eval runs
deterministic and free on re-run.
**Alternatives rejected:** HyDE (generate a hypothetical answer and embed it — more tokens,
similar effect, harder to explain); rewriting with the large model (cost without measured need).
**Why:** The plan expected this to be the Bucket-3 headline fix; with Bucket 3 already at
1.00 under hybrid, this is now a *falsification test* — if it doesn't move any bucket, the
negative result gets documented and the technique removed per the Phase-4 rule.
**Outcome (2026-06-11):** recall@5 **0.902** vs hybrid's 0.976 — sub-queries dilute the RRF
pool with tangentially-related chunks. REMOVED from the production path (kept as a `rewrite`
mode for comparison). The plan's predicted headline technique was unnecessary once hybrid
search closed the lexical gap — the corpus is small and domain-tight enough that decomposition
mostly adds noise.

## D-018 — Cross-encoder reranking (Phase 4, technique 4, optional)

**Status:** [DRAFT — needs human ratification]
**Decision:** Rerank the hybrid top-25 with `cross-encoder/ms-marco-MiniLM-L6-v2` (22M params,
CPU-fast, no remote code) and take the top-5. Measured on recall@5 like every other technique.
**Alternatives rejected:** Large rerankers (bge-reranker-v2 etc.) — CPU latency for marginal
gain at 1.4k-chunk scale; LLM-as-reranker (cost + latency, unfalsifiable prompt sensitivity).
**Why:** Reranking is the standard precision lever; at 25→5 it can also recover recall lost
to fusion ordering. If it doesn't move recall@5, it may still matter for generation quality —
but that claim would need the Phase-6 evals, so v1 keeps it only if recall moves.
**Outcome (2026-06-11):** recall@5 **0.951** vs hybrid+div's 1.000 — the MiniLM cross-encoder
reorders worse than the fused ranking on this corpus. REMOVED from the production path
(kept as a `rerank` mode for comparison).

## D-019 — Human gates waived for v1 completion (process note)

**Status:** Directed by builder 2026-06-11
**Decision:** The builder directed completion without further human intervention; manual
revision happens on the final product. Consequences: (1) the Phase-2 stranger-test QA was
performed by the LLM assistant instead of the builder — verdicts in `eval/chunk_qa_sample_1.md`,
marked as assistant-judged; (2) Phase-6 judge spot-check and failure classification are
*drafted* by the assistant and explicitly marked for builder revision; (3) the plan's
"explain-back rule" remains the builder's post-hoc responsibility during revision.
**Why:** Builder's explicit instruction; all assistant-judged artifacts are flagged inline so
nothing drafted is mistaken for human-validated.

## D-020 — Visual patch designer (post-v1 feature, builder-requested)

**Status:** [DRAFT — needs human ratification]
**Decision:** Text-to-patch web UI (`src/ui/`): a sound description is retrieved against the
corpus (production `hybrid+div` mode, k=8), then the LLM emits a JSON patch constrained to a
front-panel schema (`patch_schema.py`, 82 params/17 sections, every param grounded in the
manual chunks — names, ranges, switch positions). The browser panel starts at INIT and
animates each adjusted control into place, leaving it highlighted, with a per-change
explanation + source sidebar. Server is stdlib `http.server` (same no-extra-infrastructure
reasoning as the NumPy store, D-009); values are validated/clamped server-side.
**Grounding contract (deliberately looser than ask.py):** patch design is creative, so the
model may use general subtractive-synthesis practice — but every change must declare its
source: a chunk label when a retrieved chunk motivated it, or the literal `general synthesis`
otherwise. The UI renders these as distinct badges (manual/reddit/general) so corpus-grounded
moves are visually separable from model judgment. Faking citations is prohibited by prompt;
unverifiable labels remain a known risk inherited from the faithfulness findings (D-014).
**Alternatives rejected:** strict only-from-corpus generation (the corpus holds few complete
recipes — Phase-6 B2 finding — so patches would be mostly refusals); MIDI/NRPN output to real
hardware (v2 — the NRPN map is already in the corpus); React/heavier frontend (a static
HTML/CSS/JS page suffices and keeps the repo dependency-free).
**Why:** Converts the system's weakest measured bucket (B2 recipes) into an interactive
artifact where provenance is explicit per parameter, instead of prose where grounded and
ungrounded claims blur together.
**Verification (2026-06-12):** end-to-end smoke test ("warm Juno-style chorus pad") produced
29 schema-valid changes citing the Juno-corpus articles for the PWM routing and BBD chorus;
headless-browser screenshot of a second patch in `docs/patch_panel_demo.png`.
**Layout amendment (2026-06-12, builder-requested):** panel rebuilt as a fixed grid matching
the builder's reference photo (`prophet6.jpg`, desktop module): four control bands; Mixer
spans rows 2-3; HPF above LPF; FILTER destinations as LP/HP LED pairs; keyboard tracking as
Half/Full LEDs; oscillator Shape as knobs; BPM / effect type / glide mode / key mode / unison
voices as red 7-seg displays using the manual's display codes (bbd/ddL/CHO/PH1…, FR/FrA/Ft/FtA,
LO/Hi/LAS/LOr/Hir/LAr); bottom switch row (Transpose, Hold, Glide, Unison, Bank/Tens/digits,
Write/Globals/Preset). Non-patch hardware (Tap Tempo, Sequencer, Master/Prgm Vol, program
buttons) rendered as inert decorations. One knowing deviation: Effects renders A and B
sub-groups side-by-side (hardware edits one at a time via the A/B select), so a generated
patch can show both effects at once. Schema/API unchanged — presentational only.

## D-021 — v2 execution kickoff: gate handling, audio descope, licensing register

**Status:** [DRAFT — needs human ratification]
**Decision:** Execute `prophet6_rag_v2_plan.md` (Phases A–F) autonomously per builder
instruction ("take our newly documented plan and execute"). Three process rules for the run:
(1) **Gates are produced, flagged, and passed provisionally** — each [HUMAN GATE] artifact
(coverage matrix, per-source QA samples, extraction spot-checks, translation-table review)
is drafted and clearly marked `[provisional — pending builder review]`; work continues
rather than blocking, mirroring v1's D-019. The **hardware patch spot-check is the
exception**: it physically requires the builder's unit, so decoded patches enter the index
with round-trip validation only, and the hardware check is an open item at completion.
(2) **Audio is out of scope** (builder: "we can skip raw audio for now") — no rendering,
no audio embeddings, no perceptual eval; patch-level parameter accuracy is the text-domain
proxy, per the plan.
(3) **Licensing register lives here in decisions.md** — every v2 source gets a register
line (`public / private-corpus-only / excluded`) in its phase's decision entry before
ingestion; commercial content (Welsh cookbook, paid sound sets, paywalled Attack articles)
is excluded unless the builder supplies a licensed copy, in which case private-corpus-only.
**Why:** the builder directed autonomous execution of a plan whose gates assume their
availability; provisional-pass-with-flag preserves both momentum and the post-hoc revision
workflow the builder used for v1.
**Completion definition for this run:** Phase F milestone — all four success criteria from
the plan header measured and scored pass/fail in README (B2 majority-RAG & B3 ≥ parity;
provenance majority corpus-cited; v1 recall@5 ≥ 0.95 tripwire held across every wave;
coverage ≥ 90% of cells with ≥ 3 sources), failure analysis v2 by stage (incl. decode /
translation), negatives pruned, gate artifacts listed for builder review.

## D-022 — Phase A: eval expansion design (v2)

**Status:** [DRAFT — needs human ratification]
**Decision:** (1) **Coverage matrix** (`eval/coverage_matrix.yaml`): 10 instrument families ×
8 character traits, with musically-incoherent cells excluded; counts *independent sources*
per cell (multiple chunks from one thread/article/patch-bank count once). (2) **Golden set
v2** (`eval/golden_set_v2.jsonl`): ~80 new entries built from verbatim r/synthrecipes titles
(engagement-filtered: ≥3 comments, ≥3 score, descriptive title), spread greedily across
matrix cells; cross-synth asks → bucket 3; thread itself = expected target. Patch-accuracy
probe entries (param_targets) are added in Phase B once patch ids exist. (3) **Patch
parameter accuracy** (`eval/patch_accuracy.py`): defined before any Phase-B code — active
agreement (params the reference moved off INIT) is primary; tolerance ±10-of-127 scaled per
range for knobs, exact for switches; best-of-N references; per-section breakdown.
(4) **Guards**: check_targets.py covers both golden files + param_targets; recall.py takes
a golden-file argument; the v1 41-query run is the standing tripwire (≥ 0.95).
**Sequencing deviation from the plan text:** golden-v2 entries necessarily target content
that lands in Phases B/C (synthrecipes threads, patches), so check_targets passes per-wave:
v1 entries green at all times; v2 entries green as their phase's wave merges; full green is
a Phase-F exit condition, not a Phase-A one.
**Licensing register additions:** Sequential factory/OMOM program banks + preset-list PDFs —
official, freely distributed downloads; **private-corpus-only** for decoded parameter data
(sound-design IP caution), preset-name lists public. r/synthrecipes via pullpush — same
basis as v1 reddit acquisition (public API archive), public.
**Why:** measurement before content (house rule); real phrasings beat invented ones (v1
D-004 lesson); active agreement avoids rewarding do-nothing patches; the per-wave guard
keeps the D-015 lesson enforceable while the corpus is mid-growth.

## D-023 — Phase B: sysex decode + internal-layout reverse engineering

**Status:** [DRAFT — needs human ratification; selector orders need the hardware gate]
**Decision:** Decode the official factory (500) + OMOM (270) banks with a hand-written
decoder (`src/patches/decode_sysex.py`). Message framing and MS-bit packing come from the
manual's Appendix C. The 1024-byte internal layout is **not** NRPN-numbered (the appendix
maps MIDI parameters only; the dump is a different order) — it was reverse-engineered from
three independent evidence lines: (1) per-offset value ranges across all 770 programs
matched to the NRPN table's known ranges; (2) INIT "Basic Program" anchor bytes from the
eclewlow/Prophet6SoundLibrarian open-source constant (which also fixes name@107, len 20);
(3) name-implied settings (15/15 sync-named patches have the sync byte set; "FM Bass" =
full osc2→freq1 Poly Mod; S&H-named = LFO shape 4; square-named = both shapes 254;
bend-range histogram = the classic 2/7/12; slop offset mostly-0-max-25).
**Validation:** round-trip pack(unpack(x)) byte-identical for 770/770; decoded names match
the official preset-list PDFs 756/770 = 98.2% (all 14 misses are 20-char truncation /
embedded-author-initials artifacts, verified same-patch by eye). Offsets 28, 55-57, 60,
88, 93-105 are stored raw-only (sequencer settings, per-FX sync divides, unknowns).
**Flagged for the hardware spot-check gate (builder):** selector ORDER assumptions —
glide modes (FR/FRA/FT/FTA), LFO shapes (tri/saw/rev/squ/random; random=4 confirmed),
arp modes, key modes, clock divides, LFO/AT/PolyMod destination orders (pmod freq1
confirmed via FM Bass), shape↔PW osc pairing, FX A/B sync bits, unison voice-count
semantics (6="chord"?), offset 14=pan-spread (medium confidence).
**Alternatives rejected:** trusting NRPN numbers as offsets (disproven: name at 107 not
236); waiting for hardware dumps (builder unavailable mid-run; statistical validation +
name check substitute, hardware confirms later).
**Licensing:** banks are official freely-distributed downloads; decoded parameter data is
**private-corpus-only** (D-021/D-022 register).

## D-024 — Phase B: patch retrieval integration + the tripwire firing

**Status:** [DRAFT — needs human ratification]
**Decision:** (1) `patch` chunks (770 prose renderings of decoded programs, every adjective
parameter-derived) join chunks.jsonl → 1,958 chunks. (2) D-016's diversity guarantee gains
a third group — top-k must include a patch chunk when the query is recipe-shaped (keyword
heuristic) — and missing groups now fill distinct slots (fixes a latent v1 bug where two
swaps fought over top[-1]). (3) Patch designer gains `grounding="adapt"`: retrieved patch
chunks contribute their full structured params (+1 parameter-space neighbor via
src/patches/similar.py, NumPy weighted-param vectors) and the model adapts real patches,
citing `patch:<id>`; `"pure"` preserved for the A/B.
**The tripwire fired, as designed:** after ingestion, hybrid+div recall@5 fell 0.951 →
0.902. Diagnosis (eval/results diff): (a) BM25 IDF drift — 770 new documents sharing
recipe vocabulary reordered results near the top-5 boundary (b1-q08, b3-q08 lost, no
patches involved); (b) the P5-recreation bank flooded the one P5-emulation query (b3-q05);
(c) the same drift *fixed* b4-q01, the failure-analysis ranking miss.
**Mitigation (measured):** source-stratified BM25 — one BM25 ranking per source_type,
RRF-fused with the vector ranking (`strat+div`), so one source's vocabulary growth cannot
deflate another's IDF and no source floods the pool. Result: **0.951 restored** (B1 1.0,
B2 1.0, B3 0.8, B4 1.0); per_source 15 vs 10 identical, kept 10. PROMOTED to production
mode (ask.py + generate_patch defaults). Remaining B3 misses (Juno-chorus, retro-sci-fi)
are corpus-depth items addressed by Phases C/E.
**Note for the builder:** b3-q05 now surfaces P5-recreation factory patches instead of the
v1 article targets — arguably *better* answers that the v1 golden targets don't credit;
flagged as an eval-staleness candidate rather than forced back.

## D-025 — Phase C: recipe-literature acquisition + licensing register

**Status:** [DRAFT — needs human ratification]
**Decision:** Wave C1: the complete Synth Secrets series (64 articles incl. the index
piece), slugs enumerated from SoS's own series index, fetched politely from the publisher
like every v1 article (64/64, zero failures). Wave C2: full r/synthrecipes submission
archive via pullpush + per-thread ingestion through the v1 reddit pipeline. Each wave gets
the tripwire before merge counts.
**Licensing register:** SoS articles — publicly served by the publisher, raw HTML private,
chunked excerpts with URL provenance (same basis as v1's 8 SoS articles): private-corpus.
r/synthrecipes — public archive API, same basis as v1 reddit: public. **Welsh's
Synthesizer Cookbook — EXCLUDED** (commercial book; no licensed copy available to this
run; builder may supply one later → private-corpus-only). **Attack Magazine — EXCLUDED
this run** (paywall/ToS unverified; revisit with builder). **Gearspace — deferred:** the
scrape needs ToS review; documented rather than attempted. Vintage patch-book PDFs —
EXCLUDED (provenance of circulating scans unverifiable).
**Why:** depth-over-count (the failure-analysis conclusion); the excluded sources are
recorded as v3 candidates rather than silently skipped.
**Wave C2 amendments (2026-06-12):** (1) the first submission sweep died at 29k rows held
in memory — rewritten to stream every batch to disk with resume; final archive **36,113
submissions, complete to Nov 2016** (subreddit origin). (2) Thread ingestion scoped to the
**top 600 by engagement + all 71 golden-targeted threads** (~640 unique): measured fetch
pace was ~25s/thread (pullpush timeouts + old.reddit fallbacks), making the planned 1,500
a ~10-hour fetch for long-tail threads with marginal recipe value; fetched via 3 parallel
resumable shards instead. Long tail = v3 backlog item, not silently dropped.

## D-026 — Phase E: cross-synth translation table

**Status:** [DRAFT — needs human ratification; table content is a NAMED human gate]
**Decision:** `data/knowledge/synth_map.yaml` — 15 hand-curated source synths (Juno,
Prophet-5, Minimoog, Oberheim, DX7, CS-80, SH-101, TB-303, string machines, Jupiter-8,
Polysix, MS-20, Mellotron, ARP Odyssey, supersaw), each with: character summary, concrete
P6 parameter realizations, **caveat anti-claim rows** (e.g. "the P6 low-pass is NOT a
ladder filter" — the bake-off judge's v1 error becomes corpus-contradicted), and corpus
citations (manual sections, articles, factory patches incl. the P5-recreation bank and
FM Bass). Rendered to `translation` chunks (chunk_translation.py); the stratified-BM25
retriever gives the new source_type its own ranking lane, so cross-synth queries surface
them without bespoke routing. LLM-expansion of more synths deferred until the builder
reviews the hand-curated core (wrong mappings are worse than missing ones).
**Why:** B3 losses were translation-by-prose; structure + citations + anti-claims make
the translation layer auditable and the judge's known failure mode impossible to repeat
uncontradicted.

## D-027 — Per-source-document dedupe in top-k (Phase C wave-1 tripwire response)

**Status:** [DRAFT — needs human ratification]
**Decision:** After the Synth Secrets wave, the tripwire fired again (0.951 → 0.927):
a *second chunk of the same article* occupied a top-5 slot, displacing a distinct-source
target (b3-q03). Mitigation: at most one chunk per (source_type, source_id) in the
ranked list before the diversity pass; same-document overflow drops to the back of the
pool. Classic result diversification — a 5-slot answer rarely needs two chunks of one
document, and distinct sources serve both recall and grounded generation.
**Measured:** recall@5 0.927 → **0.976** — recovers b3-q03 AND b3-q01 (the Juno-chorus
miss standing since the patch wave). Best score of the project; v1 baseline was 0.951.
Only b3-q08 (retro-sci-fi broad ask) remains. KEPT — production.
**Why this and not target edits:** the displaced chunks were arguably-relevant content,
but fixing the eval by editing targets is the one move that's never allowed mid-run
(D-015 discipline); the technique is general and independently motivated.

## D-028 — Phase D: video transcript mining (spike → scale)

**Status:** [DRAFT — needs human ratification; extraction spot-check is a NAMED gate]
**Decision:** Transcript-only mining via yt-dlp captions (no audio downloaded, per scope).
Spike (8 videos): extraction yields real recipes where presenters state settings; the
extractor's per-video honesty is the key property — demonstration-only videos correctly
yield zero recipes, and every recipe carries a confidence tag with low-confidence ones
dropped. GO. Scale: 4 search rounds enumerated the discoverable captioned P6-tutorial
population — official Sequential Synth Tips, Soundology pad/bass/strings builds, song
recreations (Blade Runner 2049, Blinding Lights, Radiohead), J3PO brass, FM/Buchla
tutorials. **Final: 52 recipe chunks from 31 videos** (data/processed/chunks_video.jsonl;
2 candidates had no captions). Chunks are structured summaries in the extractor's own
words — never verbatim transcript — each linking the timestamped source URL.
**Deviation from plan:** milestone said "≥ 50 videos extracted"; the available
P6-specific population with usable captions is 31. Padding to 50 with generic-synth
videos would re-import the D-017 dilution risk for a count's sake; 52 recipes from 31
on-topic videos is the honest delivery. Builder may extend the allowlist in revision.
**HUMAN GATE (open):** builder spot-checks ~10 extracted recipes against the videos at
their timestamped URLs (eval/video_extraction_report.md lists per-video quality).
**Licensing:** captions fetched from YouTube's public caption tracks; only structured
summaries are stored; source links preserved. Private-corpus.

## D-029 — Wave C2 retrieval response + the tripwire's honest final state

**Status:** [DRAFT — needs human ratification; contains an eval-staleness adjudication
the builder must make]
**Context:** merging 3,720 synthrecipes Q+A chunks (plus 52 video + 15 translation)
dropped the v1 tripwire 0.976 → 0.878. Three measured iterations followed:
1. **Reddit lane split** (KEPT): the BM25/vector "reddit" lane now splits into
   `reddit` (P6 subreddit) and `reddit-recipes` (r/synthrecipes) — recipe vocabulary
   must not deflate the P6 lane's IDF. 0.878 → 0.902, recovered b3-q03.
2. **Per-lane vector rankings** (KEPT): vector candidates per lane alongside global
   top-50, completing the stratification symmetrically. No recall change at k=5 but
   guarantees pool presence for every lane (pool-inspection evidence) — retained for
   robustness, not score.
3. **Evict-lane-redundant diversity slots** (REJECTED, measured): evicting a lane's
   second chunk instead of bottom slots removed *targets* that were second-in-lane
   (b3-q03 lost again, b3-q09 not saved): 0.878. Reverted to bottom-slot eviction.
**Final state: v1 tripwire = 0.902 (below the 0.95 criterion) — reported as FAIL with
cause analysis, not excused.** Pool inspection (src/retrieve/_debug_pool.py) shows the
four misses are *eval-staleness collisions*, not retrieval defects: for b3-q01
("Juno-style chorus pad"), `translation::juno` ranks #0 — a chunk purpose-built to
answer exactly that query, which the 2025-era v1 targets cannot credit; b3-q09's
string-machine targets lose top-5 slots to the translation table's string-machine entry
and an on-topic patch; b2-q04's pad targets lose to video pad tutorials and pad patches.
The v1 golden set predates four content lanes that now answer its B2/B3 queries better.
**Builder adjudication requested:** either (a) ratify multi-target additions to the four
stale v1 entries (crediting translation/video/patch equivalents), restoring the tripwire's
meaning as a *dilution* alarm, or (b) keep the entries frozen and accept 0.902 as the
standing number. Per D-015 discipline the assistant does not edit v1 targets mid-run.
**Meanwhile the v2 golden set — built for this corpus — measures 0.953 overall: B2
recipes 55/55 = 1.00, B3 cross-synth 12/12 = 1.00, B5 recreate 14/18 = 0.778**
(eval/results/*v2_final*), the strongest direct evidence that the recipe mission's
retrieval works.

## D-030 — Phase G: MIDI-out (Mode 1, bulk edit-buffer load)

**Status:** [DRAFT — needs human ratification; hardware confirmation is the gate]
**Decision:** The visual panel can push a generated patch to a physical Prophet-6 as a
single sysex **edit-buffer dump** (`F0 01 2D 03 <1171 packed> F7`). Pieces:
1. **Encoder** (`src/patches/encode_sysex.py`): inverse of decode's `LAYOUT` — starts from
   an INIT "Basic Program" carrier (`data/patches/init_template.json`, the ~944 bytes we
   don't model: name region, sequencer, reserved/constant), overwrites the ~80 mapped
   offsets from the resolved panel state, writes `patch_name` into the name region (shows
   on the P6 display), then `pack()` + frame. Shape selects encode to per-band
   representative raw values, so `decode(encode(x)) == x` *exactly* at the schema level.
2. **Transport: Web MIDI API**, browser-native (`navigator.requestMIDIAccess({sysex:true})`)
   — no server round-trip, no new Python deps, consistent with the stdlib-only rule.
   Localhost is a secure context, so sysex access works in Chromium/Edge (the panel's
   target; Firefox/Safari unsupported → toggle disabled).
3. **Server** includes `"sysex": [int,…]` in every `/api/patch` response (deterministic,
   cheap); the client decides whether to transmit.
4. **UI**: header `MIDI OFF/ON` toggle + output-port dropdown + status line; choice
   persisted in localStorage. On Generate with MIDI ON, the full dump is sent **once,
   up-front**, then the existing animation plays purely as visual effect (builder's
   explicit choice — no per-knob streaming; sound is fully loaded before the animation
   finishes).
**Safety properties:** edit-buffer (0x03) loads into the current edit buffer and plays
immediately but **never overwrites a saved program** (user hits Write on the hardware if
they want to keep it); default OFF; sysex sent only on explicit Generate with MIDI ON.
**Alternatives rejected:** program-dump (0x02) — would overwrite a user slot; per-knob
NRPN streaming (Mode 2) — deferred, it's the animated-hardware version and needs the
parameter→NRPN map + value calibration; building sysex in JS — would duplicate the
proven Python `pack()` and risk drift.
**Convergence with D-023:** this feature *exercises* the open hardware gate — loading a
patch and hearing whether "filter cutoff" actually moves the filter confirms (or refutes)
the reverse-engineered selector orders. Mode 1 turns the manual spot-check into a working
feature; until the builder runs it on the unit, the selector-order assumptions remain
provisional.
**Completion definition:** (a) encoder self-consistency `decode(encode(p)) == p` for all
770 factory/OMOM patches + INIT; (b) framing 1176 bytes, `F0 01 2D 03 … F7`; (c) server
emits `sysex`; (d) toggle + port select + send-on-generate + decoupled animation; (e)
graceful with no Web MIDI / no device; (f) full generate-path smoke test. Hardware audio
confirmation stays a builder gate.
**Lossy note:** 5 named shapes ↔ continuous 0-254 — encode picks a representative; only
affects in-between shapes of hand-decoded factory patches, not generated patches (which
use the 5 names).

## D-031 — MIDI capture (receive direction): read a patch from the P6 into the panel

**Status:** [DRAFT — needs human ratification; hardware confirmation pending]
**Decision:** Add a **Capture** button (Web MIDI *input*) that reads the P6's current edit
buffer into the panel and decodes it server-side. Flow: browser sends the documented
request **`F0 01 2D 06 F7`** (Request Program Edit Buffer Transmit, Appendix C) on the
MIDI out, listens on the matching MIDI input, buffers the reply sysex (`F0…F7`), POSTs the
bytes to a new **`POST /api/decode`** endpoint → server runs the existing
`decode_sysex.decode_message` → returns `{name, params}`, applies them to the panel, and
writes `data/patches/captured_dump.json` for follow-up use. Manual Pgm-Dump from the P6
also works (the listener catches any incoming P6 sysex), so the request is a convenience,
not a requirement.
**Primary purpose:** ground ISSUE-1 — the builder INITs the P6, captures, and the decoded
params become the authoritative `INIT_PATCH` (fixes the hand-authored amp-envelope
defaults). Also the **first test of the decoder in the receive direction** (it has only
ever decoded files until now).
**Reuses:** the decoder is the same code that round-tripped 770 factory patches + the
encoder self-test; no new decode logic. Web MIDI input needs no new permission (we already
request `{sysex:true}`).
**Smoke test (no hardware):** POST a locally-encoded INIT dump to `/api/decode` and confirm
it decodes back to INIT — exercises the full HTTP decode path; the MIDI-input capture
itself needs the unit (builder gate).
**Caveat:** requires MIDI Sysex enabled + correct port on the P6 (same global as D-030);
sysex request/response is device-ID addressed, so MIDI channel is irrelevant.
**Outcome (2026-06-12):** builder captured the real "Basic Program" — decoded cleanly
(receive direction confirmed working) and was **byte-identical to the librarian INIT
reference**, validating both the capture and that reference. Resolved ISSUE-1: `INIT_PATCH`
reset to the captured values for 15 sound-defining params (amp env was the bug: real
default is A0 **D127 S0 R40**, not our hand-authored S127/D40/R0). Per builder choice
(option B) 3 quirks kept neutral for a clean design canvas: pan_spread 0 (was 70, audible),
fxb.type off (was flanger, bypassed), lfo.dest_freq1 off (was on, 0 amount). Verified INIT
matches hardware except exactly those 3; encoder self-test 771/771. The carrier
`init_template.json` needed no change (its mapped bytes are always overwritten by
INIT_PATCH; its unmapped bytes were already the authentic Basic Program).

## D-032 — Post-hardware-capture correctness fixes (envelope order + FX-A reverbs)

**Status:** [DRAFT — needs human ratification]
**Two bugs surfaced by the builder testing on real hardware after the D-031 capture:**

1. **Envelope decay/sustain were swapped.** Builder observed amp Sustain full on a real
   INIT while our decode said 0. Root cause: the dump stores envelopes **A-S-D-R**, not the
   A-D-S-R order the NRPN *numbering* implies. Evidence beyond the INIT: across 770 patches
   the byte we'd called "decay" is at full in 47.9% (sustain-level behavior) vs 7.8% for the
   one we'd called "sustain" (decay-time behavior). Fix: swapped offsets 36↔37 (filter) and
   40↔41 (amp) in `decode_sysex.LAYOUT`; corrected `INIT_PATCH` (amp now A0 S127 D0 R40);
   re-decoded all 770 patch JSONs. Consequence the swap had been hiding: the LLM designer's
   "high sustain for a pad" was writing to the decay byte — now corrected. Encoder
   self-test still 771/771 (it's self-consistent either way; the capture is what proved the
   labels). Patch *chunk text* regenerates at the next reindex (post ≥1-comment fetch).

2. **A reverb on Effect A crashed the whole sysex dump → "HALL not transmitted."** The
   schema offered reverbs on `fxa.type`, but FX A (FX1) has none, and the encoder's FX-A
   list excludes them, so `fxa.type=hall-reverb` → `list.index` ValueError → `_sysex_for`
   returned None → nothing sent. Fix: restricted `fxa.type` options to the reverb-free FX-A
   set (off/bbd/ddl/chorus/ph1/ph2/ph3/ring-mod); validate_changes now drops a reverb-on-A;
   and `encode_sysex._encode_value` falls back to option 0 ("off") on any unknown select
   instead of crashing the dump (defense-in-depth). FX B decode/encode for reverbs was
   already correct (hall=byte 6, validated against 210 factory hall patches).
**Deferred (builder's call):** the `fx.on` offset-54 suspicion (ISSUE-3, needs a capture)
and the Unison "Voices" display fidelity (ISSUE-4). Both left as documented open items.

## D-033 — Reference-free patch-quality eval (the mission shifted to patch creation)

**Status:** [DRAFT — needs human ratification; the rubric harvest and the judge both inherit
named human gates]
**Context:** the project's center of gravity has moved from P6 Q&A to **natural-language
patch creation**. recall@5 measures *retrieval* (did a relevant chunk surface), not whether
the generated **patch** realizes the request — and the two diverge badly. Demonstrated on
"Synth similar to Nangs by Tame Impala": recall@5 scores a HIT (thread `cesf59` is in the
top-5) while the served chunks are a whippet joke, a "thank you", a forced-in troubleshooting
KB page, and the *wrong* translation entry (string-machine, not Juno) — nothing that builds
the sound. The metric says success; the patch path gets noise.
**Decision:** add `eval/patch_quality.py` — a patch-aligned eval with **zero hand-authored
reference patches** (authoring a gold patch per query doesn't scale and bakes in one builder's
opinion). Three layers, each auto-derived or reference-free:
1. **Rubric (A)** — auto-harvested from the curated cross-synth table (`synth_map.yaml`): each
   synth's `p6_realization` lines are regex-mined for explicit schema param ids into checkable
   assertions (`fxa.type=chorus`, `(lfo.dest_pw12)`, `mixer.sub_octave high`), scored as
   partial credit. Covers Juno/Minimoog-class queries; returns None for queries no entry names
   (e.g. Nangs) — an honest miss, not a fabricated score.
2. **Judge (B)** — reference-free LLM judge: "does this patch plausibly achieve the
   description?" (1-5 + named missing moves). Works on ANY query incl. famous-song asks.
3. **Round-trip (C)** — render the generated patch to prose deterministically (reuses
   `chunk_patches.render`, no API, query-blind), embed vs the query, report cosine. Free
   tripwire.
**Validation (built in, `--selftest`):** a metric earns its place only if it SEPARATES a
matched patch from a mismatched one. Scoring each of 3 probe queries against all 3 generated
patches, matched-vs-mismatched separation was: **judge +2.33** (diag 3.67 vs 1.33), **rubric
+0.67**, **round-trip +0.07** — all positive, so all three discriminate; the judge is the
strong signal, round-trip a weak gross-failure tripwire (its bass row is nearly flat).
**Caveats (carried forward honestly):** the judge **cannot hear** — it reasons over parameters
and needs the same human spot-check every judge got (D-013); round-trip proves **consistency,
not correctness** (the Part III lesson); the auto-harvested rubric is **provisional**, same
ratification status as the table it reads (D-026) — e.g. the Minimoog entry yields 0 asserts
because its lines are prose without param ids.
**Incidental finding (generation stage):** across probes the judge repeatedly flagged the same
two defects — LFO rate set too fast and osc2 detuned too wide — i.e. a **systematic designer
bias**, the kind of generation-stage issue the failure taxonomy exists to surface. Logged for a
prompt/calibration follow-up, not fixed here.
**Incidental fix (production path, D-032's "fail safe not silent-and-total" applied):**
`generate_patch` truncated mid-JSON at `max_tokens=3000` on verbose (20+ change) patches and
`_extract_json` crashed on the cut-off string. Raised the ceiling to 4096 and added
`_salvage_truncated`, which recovers the patch name and every COMPLETE change object and drops
the truncated tail. This bug would also have hit the live UI.
**Alternatives rejected:** hand-authoring gold patches per query (the thing the user explicitly
ruled out — doesn't scale, encodes one opinion); forcing recall@5 to carry patch quality (wrong
layer — kept as a retrieval-health check instead); audio rendering + perceptual eval (the real
oracle, still deferred to v3 per D-021).
**Why:** gives the patch-creation mission a measurable quality signal — covering held *and*
open-ended/famous-song requests — reusing existing assets (translation table, patch renderer,
bge model, judge infra) with no new corpus authoring.

## D-034 — Patch-tuned retrieval: rank by sound-design actionability (`patch+div`)

**Status:** [DRAFT — needs human ratification]
**Context:** the patch designer used `strat+div`, the Q&A-tuned retrieval. For patch creation
that surfaces the wrong chunks: on "Synth similar to Nangs by Tame Impala" the strat+div top-5
was a ReverbMachine pointer, a "thank you so much" reply, a forced-in troubleshooting KB page
(the D-016 official-chunk guarantee firing with nothing relevant), a music-recs thread, and the
*wrong* translation entry (string-machine) — none of which carry settings. The genuinely useful
chunks (the cesf59 "multiple filters / filter modulation in Hz" answer; a reddit "cutoff LFO on
low amount" description of the exact Nangs mechanism; a P6 video recipe; an adaptable factory
patch) sat outside the top-5 or were absent. Q&A retrieval ranks by topical relevance; patch
creation also needs **actionability** — does the chunk contain real sound-design SETTINGS.
**Decision:** add a `patch+div` retrieval mode (search.py) used ONLY by `generate_patch`:
1. take the stratified relevance pool (k=25);
2. score each chunk's **actionability** (`_actionability`): density of parameter vocabulary
   (cutoff/resonance/LFO/detune/chorus/…), imperative sound-design verbs (set/route/dial/…),
   and numeric settings, minus a penalty for chatter markers (thank you/lol/whippet/…);
3. re-rank the pool by RRF-fusing the relevance rank with the actionability rank;
4. dedupe by source (D-027), then a **relevance-guarded** diversity pass that injects an
   official/reddit/patch chunk only if it clears an actionability floor, picking the MOST
   actionable qualifying candidate — so a "thank you" or an off-topic page can no longer take
   a slot (fixes the D-016 noise-injection failure for patch queries).
**Scoping:** `strat+div` is unchanged, so the v1 recall@5 tripwire is untouched — verified
**0.902** (B1 1.0 / B2 0.9 / B3 0.7 / B4 1.0), identical to D-029's number. ask.py (Q&A) also
unaffected. Only the designer's retrieval changed; `generate_patch` default mode flipped to
`patch+div`.
**Measured (3-sample averages, claude-sonnet-4-6 judge + provenance, A/B same query both modes):**
| query | judge strat→patch | provenance strat→patch |
|---|---|---|
| Nangs | 3.00 → 3.00 | 0.40 → **0.52** |
| warm Juno pad | 4.00 → 4.00 | 0.72 → **0.95** |
| thick low brass | 3.67 → **4.00** | 0.85 → 0.88 |
Provenance (corpus-cited changes) rose in all three — the direct evidence retrieval now serves
citable, patch-relevant content and the model uses it. Brass judge improved (3.67→4.00) and was
stabilized (the earlier single-sample 4→3 was temperature noise). **No regressions.**
**Honest limits:** (1) the Nangs *judge* score held at 3 despite far better retrieval — the
residual defects are GENERATION-stage (the LFO-too-fast / osc2-over-detune systematic bias
logged in D-033), not retrieval; the patch-quality ceiling for Nangs is now the generation
prompt, a separate fix. The failure taxonomy working: retrieval fixed (provenance proves it),
generation bias remains. (2) Actionability can't distinguish a troubleshooting page from a
recipe — both mention parameters — so a calibration KB page still reached #6 (down from #3) via
the official-chunk guarantee; a topic-relevance guard on injection is a follow-up. (3) Weights/
floor are lightly tuned and validated on held queries + the unchanged recall tripwire, not
fit to Nangs alone.
**Alternatives rejected:** changing `strat+div` globally (would move the recall tripwire and
hurt Q&A — wrong layer); a cross-encoder relevance rerank (removed in D-018 as no-gain on this
corpus, and it scores topical match, not actionability); an explicit song/artist→synth bridge
(higher-curation, doesn't scale — deferred; actionability got most of the win generally).
**Why:** the designer's retrieval now matches what a patch needs — real settings over chatter —
measurably lifting grounding with no Q&A/recall cost.

## D-035 — The ≥1-comment expansion: measured, rejected, reverted (negative result)

**Status:** [DRAFT — needs human ratification]
**Hypothesis (builder-requested experiment):** lowering the synthrecipes thread bar from
"≥3 comments" to "≥1 comment" (~3× the candidate set) might broaden recipe coverage.
**Acquisition:** full ≥1-comment sweep, 6 resumable shards, 17,196 threads on disk.
**Yield audit (free, pre-merge):** poor — ~51% of new threads failed to fetch
(deleted/never-archived long tail), 40% of fetched threads yielded zero qualifying chunks,
and of the surviving synthrecipes chunks **65% scored below the trust threshold** (passed
only on the length fallback). A full merge would make reddit **94%** of the corpus, burying
the structured patches/articles/translation/video.
**Option B tested (the surgical version):** keep only score-qualified (≥3) synthrecipes
chunks — 8,070, dropping 15,030 — via `filter_recipe_quality.py`. Merged corpus 10,552,
reddit 85%. Reindexed and measured.
**Result — decisive FAIL:** v1 tripwire 0.902→**0.829**, v2 golden 0.953→**0.659**
(B2 recipes 1.00→0.64, B3 1.00→0.67). Two confirmed mechanisms: (a) **dilution** — doubling
the recipe lane crowded targets out of top-5 (the v1 tripwire, which targets no synthrecipes
thread, fell purely from crowding); (b) the **score gate removed eval targets** — several v2
golden threads have sub-3 comment scores, so their chunks were dropped → automatic misses.
**The upside never existed:** recipe recall (B2/B3) was already maxed at 1.00 pre-expansion,
so more chunks could only hold or hurt — there was no headroom to gain.
**Verdict: REVERTED** to the pre-expansion corpus (top-600 synthrecipes + v1 P6 threads)
via `_revert_expansion.py`, reconstructed from the backed-up full chunk set (no refetch).
Restoration: B2 **1.00**, B3 **1.00** (fully recovered); v2 overall 0.941, v1 0.878 — the
~0.01–0.02 residual below the prior 0.953/0.902 is from the **D-032 envelope-label
re-render** changing patch-chunk embeddings, NOT the expansion (verified: recipe buckets are
perfect). All 126 golden targets reachable.
**Nothing lost:** the 17,196 raw threads and the full 24,084-chunk set
(`chunks_reddit.full.jsonl`) remain on disk for a future, fundamentally different retrieval
approach (e.g. a recipe-only sub-index, or per-thread summarization before chunking).
**Lesson (the v1 D-017 rule, re-confirmed at scale):** "more data" is a hypothesis, not an
improvement. Measured before trusting; it diluted a domain-tight corpus exactly as the
stratified-retrieval work (D-024/D-029) predicted, and the eval caught it cleanly.

---

*(Subsequent entries added per phase, before the code they govern is written.)*
