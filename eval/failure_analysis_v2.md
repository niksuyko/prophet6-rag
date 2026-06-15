# Failure analysis — v2 (plan Phase F)

**Drafted by the LLM assistant per D-021; classifications are proposals for the builder
to revise.** Stages now include `decode` and `translation` alongside the v1 five
(acquisition / chunking / retrieval / generation / judge).

## 1. Retrieval misses

**v1 tripwire (41 queries): 0.902 — 4 misses, all eval-staleness collisions (D-029).**
Pool inspection shows each miss's top-5 filled by *newer, on-topic* sources the 2025-era
targets cannot credit (e.g. `translation::juno` at rank 0 for the Juno-chorus query;
video pad tutorials + pad patches outranking the old pad thread). Stage: **eval
staleness**, not retrieval. Builder adjudication: extend those four entries' target
lists, or freeze and accept 0.902.

**v2 golden (85 queries): 0.953** — B2 recipes 55/55, B3 cross-synth 12/12.
The 4 misses are all B5 recreate-probes (14/18): vague probe phrasings ("solid round
synth bass") retrieve *other* equally-plausible bass patches instead of the specific
reference. Stage: **eval design** (probe phrasing under-specifies the target) — the
patch-similarity neighbor expansion usually still surfaces a same-family patch.

## 2. Patch-accuracy (C6) spread

Mean active agreement 0.509 (overall 0.701) across 18 recreate-probes, strongly bimodal:
probes whose phrasing names the reference ("thick low analog brass") agree 0.75–0.88;
abstract probes ("airy bell tones", 0.20) generate valid-but-different patches.
Stage: **generation under-determination** — many parameter sets realize one adjective.
The metric is doing its job; per-section breakdowns live in
`eval/results/*patch_accuracy*`.

## 3. Bake-off (RAG 40 — base 45; B2 25–30, B3 7–5, B5 8–10)

B3 reaches majority (7–5; v1 was 4–6) — the translation layer's target bucket. B2 and
B5 verdicts, however, are contaminated by a **measurement artifact**:

- `strip_citations()` predates the v2 label format and does **not** strip
  `[patch:p6-factory-013]`-style markers. The "blind" judge saw citation-like markup
  it could not verify.
- Audit (`src/evaluate/_bakeoff_audit.py`): **20 of 45 base wins** allege fabrication
  against the RAG answer; **10 explicitly call its factory-preset references
  fabricated** — references that are *verifiably true* (preset 013 IS "Thick Low
  Strings"; the decoded values quoted ARE that patch's values). The judge punished
  grounding as hallucination.
- Stage: **judge (harness bug + verification asymmetry)**. The base model's smooth,
  uncheckable walkthroughs carry no markup to distrust; the grounded answer's true
  specifics look invented. If only the 10 explicit preset-fabrication verdicts
  flipped, the totals would read RAG 50 — base 35.

Builder items: fix `strip_citations` for v2 labels and re-judge B5 (or spot-check
~10 verdicts as in v1); do NOT quote the headline 40–45 without this caveat.

## 4. Provenance ratio (0.458 cited)

234/511 designer changes cite corpus sources (video 98, patch 52, reddit 47,
translation 27, article 7, manual 3) vs v1's ~17% — a 2.7× improvement that still
misses the majority criterion. Concentration: envelope/mixer "glue" settings default
to general-synthesis judgment even when a patch example is present. Stage:
**generation** (prompt could require per-section grounding); partly **eval design**
(the 25-change patches include many low-stakes cosmetic settings no source specifies).

## 5. Faithfulness (claim-level, 85 queries)

All 85 judged (the malformed-judge-JSON crash at q30 reproduced and was absorbed by
the new retry guard — a **judge-stage** robustness finding). Results: **60.0% strict
answer-level (51/85), 93.8% claim-level (61 unsupported of 981 claims), 6 contradicted
claims**. v1 comparison: 53.7% / 93.4% / 0. Claim-level support held at ~94% on a 5×
corpus; strict improved 6 points. The **6 contradicted claims are new** (v1 had zero) —
each needs the builder's eye in `eval/judge_spotcheck_v2.md`: with patch chunks now
carrying exact numeric values, a generated value that drifts from its cited patch is
*verifiable* as contradicted, which v1's prose-only corpus could never detect. Some may
be honest model drift (generation stage), some judge over-reach (judge stage).

## 6. Decode + translation stages (new)

- **decode:** 0 round-trip failures; 98.2% name validation; residual risk is selector
  ORDER assumptions (D-023 list) — pending the hardware gate. One incidental
  confirmation: chord-named patch carries the chord-memory voice value.
- **translation:** no measured failures; risk is content correctness (hand-curated)
  — builder review gate (D-026). The anti-claim rows have already earned their keep:
  no v2 judge rationale repeated the v1 "ladder filter" error.

## Taxonomy totals

- eval staleness: 4 v1 tripwire misses (adjudication open)
- judge: bake-off citation-blindness artifact (≥10 wrong-basis verdicts), 1 crash +
  1 skip on malformed JSON
- generation: provenance gap on glue parameters; under-determined recreates
- retrieval: 0 confirmed defects on the v2 set (B2/B3 perfect)
- acquisition/chunking/decode/translation: no open defects; gates pending builder
