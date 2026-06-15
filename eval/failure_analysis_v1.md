# Failure analysis — v1 (per plan Phase 6, step 3)

**Drafted by the LLM assistant per D-019; classifications are proposals for the builder to
revise.** Every miss is classified by failure stage: acquisition / chunking / retrieval /
generation / judge.

## 1. Retrieval misses (2 of 41 queries, recall@5 = 0.951)

| Query | What happened | Stage |
|---|---|---|
| b2-q04 "warm pad with movement" | Two of three expected targets thinned out when QA cleanup removed OP-authored answers; the third (SoS PWM-strings article) ranks just below top-5 — generic "warm pad" phrasing matches calibration/oscillator chunks lexically. | **chunking↔acquisition interplay** (quality filter traded recall for cleanliness — accepted trade) |
| b4-q01 "velocity doesn't affect anything" | The manual's velocity switches live inside the Filters/Amp-Envelope sections whose chunks are dominated by other parameter text; "velocity" reddit mentions flood BM25. Diversity guarantee swaps in *a* manual chunk but not the right one. | **retrieval (ranking)** — candidate fix for v2: section-title boosting or finer manual sub-chunking |

## 2. Faithfulness failures (19 of 41 answers had ≥1 unsupported claim; 30 unsupported of 456 total claims → 93.4% claim-level support, 53.7% strict answer-level)

Classification of the 30 unsupported claims:

| Class | ~Count | Examples | Stage |
|---|---|---|---|
| True-but-ungrounded "glue" knowledge | ~20 | "the P6 has a knob-per-function layout"; "it's not a ladder filter"; "detuning osc 2 adds thickness" | **generation** — the model supplements chunks with correct general synth knowledge despite the only-from-context instruction. Mitigations: stricter prompt, or accept and report claim-level support |
| Extrapolation beyond the chunk | ~6 | "the built-in tuning slots are designed around 12-note MIDI mapping"; "17 custom scale slots" | **generation** (these are the risky ones — plausible, specific, unverified) |
| Arguably-inferable, judge counted strict | ~4 | "chord memory is not the same as the arp's hold function" (both described in adjacent chunks) | **judge strictness** — human spot-check (`eval/judge_spotcheck_v1.md`) should adjudicate |

Notably **zero contradicted claims** — failures are additions, not contradictions of sources.

## 3. Bake-off losses (18 of 41; RAG won 23, base 18, tie 0)

| Bucket | RAG/base | Read |
|---|---|---|
| B1 factual | **11/0** | Grounding wins everywhere hallucination risk is highest (e.g. base model invented "vintage mode ships on every unit out of the box"). |
| B2 recipes | 3/7 | **Corpus-depth gap (acquisition).** Golden threads answer one specific recipe; the base model writes complete generic patch walkthroughs that the judge prefers for usefulness. v2 fix: ingest synth-programming tutorial content (SoS series is already partially in corpus but thin on P6-specific routing). |
| B3 cross-synth | 4/6 | Same shape as B2 — the base model's broad emulation fluency beats narrow thread retrieval; also one judge verdict contained its own factual error ("the P6 actually does use a ladder-style filter" — it does not), flagged for the spot-check. |
| B4 troubleshooting | 5/5 | RAG wins where the official procedure matters (calibration steps, failed-OS recovery, switch fix); base wins on generic diagnostics. |

## Taxonomy totals

- acquisition gaps: the dominant cause of bake-off losses (B2/B3 corpus depth)
- chunking: 1 partial contributor (b2-q04)
- retrieval: 1 ranking miss (b4-q01)
- generation: ~26 ungrounded claims across 19 answers
- judge: ~4 over-strict claim verdicts + ≥1 factually wrong bake-off rationale → **spot-check before quoting headline numbers**
