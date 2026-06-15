# Gate 1 — Human review checklist

Everything below is blocking: per the project plan, these steps are yours and cannot be
delegated. Work through them in order; notes on how to record each verdict are inline.

## 1. Ratify (or veto) the drafted decisions — `decisions.md`

Entries D-001 through D-015 are marked **[DRAFT — needs human ratification]**. Read each;
if you agree, change the status line to `Ratified <date>`; if not, write what to change and
I'll re-implement. The ones with real judgment calls in them:

- **D-006** — multi-target recall matching (deviates from the plan's literal single-target schema)
- **D-008** — reddit quality filter, including the 250→150 length-fallback tune
- **D-010** — embedding model (bge-base) + NumPy store choice
- **D-015** — the golden-set repair after discovering 7 targets were deleted from reddit
  (5 queries replaced, 1 retargeted to the manual — check you're comfortable with each
  replacement; they're marked `REPLACED 2026-06-11` in `eval/golden_set.jsonl`)

## 2. Review the golden set — `eval/golden_set.jsonl`

41 queries, 4 buckets. You own this eval. Check: do the queries sound like things you (or
r/synthrecipes posters) would actually ask? Are the expected targets the right answers?
Edit/add/remove entries freely — then re-run:

```powershell
python -X utf8 src/evaluate/check_targets.py
python -X utf8 src/evaluate/recall.py baseline-v3 5 vector
python -X utf8 src/evaluate/recall.py hybrid-v3 5 hybrid
```

## 3. Stranger-test 30 chunks — `eval/chunk_qa_sample_1.md`  (the mandatory Phase-2 QA loop)

For each chunk: *would this passage make sense to a stranger with zero context?*
Mark PASS/FAIL in the file with a failure note. Expect to find problems — the plan
budgets 2–3 fix-regenerate-resample loops. When you're done, tell me and I'll fix the
chunkers per your notes, regenerate, and cut `chunk_qa_sample_2.md` with a fresh seed.

## 4. Interpret the first results table (your read, not mine)

| Run | Overall | B1 | B2 | B3 | B4 |
|---|---|---|---|---|---|
| vector baseline | 0.927 | 1.00 | 0.80 | 0.90 | 1.00 |
| hybrid BM25+RRF | 0.976 | 1.00 | 1.00 | 1.00 | 0.90 |

Raw per-query results: `eval/results/*_recall_baseline-v2.json` / `*_hybrid-rrf-v2.json`.
Questions for you to take a position on (they steer Phase 4):

- Keep hybrid given the b4-q01 regression, or require recovering it first?
- At 97.6%, is recall saturated enough that Phase 4 should pivot from recall-chasing to
  precision (reranking) and the API-dependent techniques — or do you want headroom probed
  with a harder golden set (e.g., more invented/messy phrasings)?

## 5. Provide an ANTHROPIC_API_KEY (needed for Phases 4–6)

Query rewriting, generation (`ask.py`), faithfulness judging, and the bake-off all call the
Claude API. Set it for this machine, e.g.:

```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
```

(restart the session afterwards so it's inherited).

---

When 1–5 are done, say the word and I proceed: chunker fixes from your QA notes → re-index
→ re-eval → Phase 4 remaining techniques → Phase 5 CLI → Phase 6 judged evals (which end in
your judge spot-check + failure classification) → Phase 7 write-up.
