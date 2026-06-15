"""Retrieval entry point: retrieve(query, k) -> list of chunk dicts (with similarity).

Phase 3: pure vector search (NumPy cosine over normalized embeddings).
Phase 4 techniques (hybrid BM25, metadata, query rewriting, reranking) extend this module —
each behind its own function so eval runs can compare them.
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = ROOT / "data" / "index"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # BGE retrieval prefix


@lru_cache(maxsize=1)
def _index():
    vecs = np.load(INDEX_DIR / "embeddings.npy")
    chunks = [json.loads(l) for l in
              (INDEX_DIR / "chunks.meta.jsonl").read_text(encoding="utf-8").splitlines()]
    meta = json.loads((INDEX_DIR / "index_meta.json").read_text())
    return vecs, chunks, meta


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(_index()[2]["model"])


def embed_query(query: str) -> np.ndarray:
    return _model().encode([QUERY_PREFIX + query], normalize_embeddings=True)[0]


def vector_search(query: str, k: int = 5) -> list[dict]:
    vecs, chunks, _ = _index()
    sims = vecs @ embed_query(query)
    top = np.argsort(-sims)[:k]
    return [{**chunks[i], "similarity": float(sims[i])} for i in top]


@lru_cache(maxsize=1)
def _bm25():
    from rank_bm25 import BM25Okapi
    _, chunks, _ = _index()
    return BM25Okapi([_tokenize(c["text"]) for c in chunks])


def _tokenize(text: str) -> list[str]:
    import re
    return re.findall(r"\w+", text.lower())


def hybrid_search(query: str, k: int = 5, pool: int = 50, rrf_k: int = 60) -> list[dict]:
    """BM25 + vector fused with reciprocal rank fusion (decisions.md D-011)."""
    vecs, chunks, _ = _index()
    sims = vecs @ embed_query(query)
    vec_rank = np.argsort(-sims)[:pool]
    bm_scores = _bm25().get_scores(_tokenize(query))
    bm_rank = np.argsort(-bm_scores)[:pool]
    fused: dict[int, float] = {}
    for ranking in (vec_rank, bm_rank):
        for rank, idx in enumerate(ranking):
            fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (rrf_k + rank + 1)
    top = sorted(fused, key=fused.get, reverse=True)[:k]
    return [{**chunks[i], "similarity": float(sims[i]), "rrf": fused[i]} for i in top]


@lru_cache(maxsize=1)
def _synthrecipes_ids() -> frozenset:
    import json as _json
    path = Path(__file__).resolve().parents[2] / "data" / "raw" / "synthrecipes" / "submissions.jsonl"
    if not path.exists():
        return frozenset()
    return frozenset(_json.loads(l)["id"] for l in
                     path.read_text(encoding="utf-8").splitlines() if l.strip())


def _lane(c: dict) -> str:
    """Retrieval lane (D-024/D-029): source_type, with reddit split by community —
    r/synthrecipes' recipe vocabulary must not deflate the P6-subreddit lane's IDF."""
    if c["source_type"] == "reddit" and c["source_id"] in _synthrecipes_ids():
        return "reddit-recipes"
    return c["source_type"]


@lru_cache(maxsize=1)
def _bm25_by_source():
    """Per-lane BM25 indexes (D-024): a lane's vocabulary growth cannot deflate
    another lane's IDF, and no single lane can flood the fused pool."""
    from rank_bm25 import BM25Okapi
    _, chunks, _ = _index()
    groups: dict[str, list[int]] = {}
    for i, c in enumerate(chunks):
        groups.setdefault(_lane(c), []).append(i)
    return {st: (BM25Okapi([_tokenize(chunks[i]["text"]) for i in idxs]), idxs)
            for st, idxs in groups.items()}


@lru_cache(maxsize=1)
def _lane_indices() -> dict:
    _, chunks, _ = _index()
    groups: dict[str, list[int]] = {}
    for i, c in enumerate(chunks):
        groups.setdefault(_lane(c), []).append(i)
    return {st: np.array(idxs) for st, idxs in groups.items()}


def stratified_hybrid_search(query: str, k: int = 5, per_source: int = 10,
                             per_lane_vec: int = 8, rrf_k: int = 60) -> list[dict]:
    """Fully stratified hybrid (D-024 + D-029): global vector ranking PLUS per-lane
    vector and per-lane BM25 rankings, RRF-fused. Per-lane rankings guarantee every
    lane's best content reaches the pool regardless of sibling-lane growth."""
    vecs, chunks, _ = _index()
    sims = vecs @ embed_query(query)
    rankings = [list(np.argsort(-sims)[:50])]
    for st, idxs in _lane_indices().items():
        order = np.argsort(-sims[idxs])[:per_lane_vec]
        rankings.append([int(idxs[i]) for i in order])
    toks = _tokenize(query)
    for st, (bm, idxs) in _bm25_by_source().items():
        scores = bm.get_scores(toks)
        order = np.argsort(-scores)[:per_source]
        rankings.append([idxs[i] for i in order])
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (rrf_k + rank + 1)
    top = sorted(fused, key=fused.get, reverse=True)[:k]
    return [{**chunks[i], "similarity": float(sims[i]), "rrf": fused[i]} for i in top]


def dedupe_by_source(pool: list[dict]) -> list[dict]:
    """At most one chunk per source document (D-027): a second chunk of the same
    article/thread/patch adds little to a 5-slot answer and crowds out distinct
    sources. Overflow chunks drop to the back of the pool (still diversify-eligible)."""
    seen, first, overflow = set(), [], []
    for c in pool:
        key = (c["source_type"], c["source_id"])
        (overflow if key in seen else first).append(c)
        seen.add(key)
    return first + overflow


def stratified_diverse_search(query: str, k: int = 5) -> list[dict]:
    pool = stratified_hybrid_search(query, k=25)
    return diversify(dedupe_by_source(pool), pool, k, query=query)


# --- Patch-tuned retrieval (decisions.md D-034) -------------------------------------
# The patch DESIGNER wants chunks that carry actual sound-design SETTINGS, not social
# chatter ("thank you", jokes) or off-topic pages. recall@5 (which tests strat+div) is
# left untouched; this path is used only by generate_patch, so the v1 tripwire can't move.
_PARAM_TERMS = (
    "cutoff", "resonance", "filter", "lpf", "hpf", "high-pass", "low-pass", "envelope",
    "attack", "decay", "sustain", "release", "lfo", "oscillator", "osc ", "detune",
    "chorus", "reverb", "delay", "phaser", "flanger", "pulse width", "pwm", "sub osc",
    "sub-osc", "sub octave", "noise", "feedback", "depth", " rate", "sync", "glide",
    "portamento", "unison", "semitone", "octave", "waveform", "sawtooth", "saw ", "square",
    "triangle", "sine", "pulse", "modulation", "mod wheel", "aftertouch", "distortion",
    "overdrive", "drive", "wet", "dry", "voices", "poly mod", "slop", "velocity",
    "keyboard tracking", "pitch bend", "tune", "frequency", "amount", "mix")
_IMPERATIVE = (
    "set ", "turn ", "route ", "increase", "decrease", "dial", "crank", "lower", "raise",
    "bump", "boost", "roll off", "roll-off", "open up", "close", "add a", "put a",
    "adjust", "tweak", "modulate")
_CHATTER = (
    "thank you", "thanks", "lol", "haha", "aussie slang", "whippet", "this is amazing",
    "great article", "subscribe", "hope to", "awesome", "cheers", "god bless", "underrated")

ACTION_WEIGHT = 1.0   # weight of the actionability ranking when fused with relevance
ACTION_FLOOR = 1.0    # a diversity-injected chunk must clear this (blocks chatter/off-topic)


def _actionability(text: str) -> float:
    """How much real sound-design SETTING content a chunk carries (D-034). Patch/manual/
    translation chunks score high; recipe answers with settings score moderate; jokes,
    'thank you', and bare links score ~0 or negative."""
    import re
    t = text.lower()
    terms = sum(1 for w in _PARAM_TERMS if w in t)
    imps = sum(1 for w in _IMPERATIVE if w in t)
    nums = len(re.findall(r"\b\d{1,3}\b|o.?clock|%", t))
    chat = sum(1 for w in _CHATTER if w in t)
    return terms + 1.5 * imps + 0.5 * min(nums, 6) - 2.0 * chat


def patch_diverse_search(query: str, k: int = 8) -> list[dict]:
    """Patch-designer retrieval: re-rank the relevance pool by fusing retrieval rank with
    patch-actionability (RRF), then guarantee source diversity using only chunks that clear
    the actionability floor — so a 'thank you' or an off-topic troubleshooting page can no
    longer take a slot. Always treats the query as recipe-shaped (the designer always wants
    a patch exemplar)."""
    pool = stratified_hybrid_search(query, k=25)
    act = {c["chunk_id"]: _actionability(c["text"]) for c in pool}
    fused = {c["chunk_id"]: 1.0 / (60 + r + 1) for r, c in enumerate(pool)}
    for r, c in enumerate(sorted(pool, key=lambda c: -act[c["chunk_id"]])):
        fused[c["chunk_id"]] += ACTION_WEIGHT / (60 + r + 1)
    reranked = dedupe_by_source(sorted(pool, key=lambda c: -fused[c["chunk_id"]]))
    return _diversify_actionable(reranked, k, act)


def _diversify_actionable(results: list[dict], k: int, act: dict) -> list[dict]:
    top = results[:k]
    rest = [c for c in results if c["chunk_id"] not in {t["chunk_id"] for t in top}]
    groups = [lambda c: c["source_type"] in ("manual", "official_kb"),
              lambda c: c["source_type"] == "reddit",
              lambda c: c["source_type"] == "patch"]
    slot = k - 1
    for is_member in groups:
        if any(is_member(c) for c in top):
            continue
        cands = [c for c in rest if is_member(c) and act.get(c["chunk_id"], 0) >= ACTION_FLOOR]
        if cands:  # inject the MOST ACTIONABLE qualifying member, not just the first
            swap_in = max(cands, key=lambda c: act[c["chunk_id"]])
            top[slot] = swap_in
            rest = [c for c in rest if c["chunk_id"] != swap_in["chunk_id"]]
            slot -= 1
    return top


_RECIPE_SHAPED = None


def _recipe_shaped(query: str) -> bool:
    """Heuristic: is this a make-me-a-sound ask (vs a factual/troubleshooting one)?"""
    import re
    global _RECIPE_SHAPED
    if _RECIPE_SHAPED is None:
        _RECIPE_SHAPED = re.compile(
            r"\b(make|create|recreate|get|achieve|design|program|patch|recipe|emulate|"
            r"sound like|sounds like|how (do|would|to))\b.*\b(sound|patch|tone|bass|lead|"
            r"pad|strings?|brass|keys?|pluck|arp|drone|chord|stab|drums?|kick|snare)\b"
            r"|\b(warm|fat|lush|aggressive|vintage|huge|thick)\b", re.I)
    return bool(_RECIPE_SHAPED.search(query))


def diversify(results: list[dict], pool: list[dict], k: int, query: str = "") -> list[dict]:
    """Source-diversity guarantee (decisions.md D-016, extended D-024): top-k should
    contain at least one official (manual/official_kb) chunk and one reddit chunk when
    the pool has them — plus one patch chunk when the query is recipe-shaped. Each
    missing group fills a distinct slot from the bottom of the ranking."""
    top = results[:k]
    rest = [c for c in pool if c["chunk_id"] not in {t["chunk_id"] for t in top}]
    groups = [lambda c: c["source_type"] in ("manual", "official_kb"),
              lambda c: c["source_type"] == "reddit"]
    if _recipe_shaped(query):
        groups.append(lambda c: c["source_type"] == "patch")
    # eviction policy: bottom slots (measured better than evict-lane-redundant,
    # which removed targets that were second-in-lane — see D-029)
    slot = k - 1
    for is_member in groups:
        if not any(is_member(c) for c in top):
            swap_in = next((c for c in rest if is_member(c)), None)
            if swap_in is not None:
                top[slot] = swap_in
                rest = [c for c in rest if c["chunk_id"] != swap_in["chunk_id"]]
                slot -= 1
    return top


def hybrid_diverse_search(query: str, k: int = 5) -> list[dict]:
    pool = hybrid_search(query, k=25)
    return diversify(pool, pool, k, query=query)


def rewrite_search(query: str, k: int = 5) -> list[dict]:
    """LLM query expansion (decisions.md D-017): RRF-merge hybrid results across sub-queries."""
    from rewrite import expand_query
    sub_queries = [query] + expand_query(query)
    fused: dict[str, float] = {}
    chunk_by_id: dict[str, dict] = {}
    for sq in sub_queries:
        for rank, c in enumerate(hybrid_search(sq, k=25)):
            fused[c["chunk_id"]] = fused.get(c["chunk_id"], 0.0) + 1.0 / (60 + rank + 1)
            chunk_by_id[c["chunk_id"]] = c
    top = sorted(fused, key=fused.get, reverse=True)[:k]
    return [chunk_by_id[cid] for cid in top]


@lru_cache(maxsize=1)
def _reranker():
    from sentence_transformers import CrossEncoder
    return CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")


def rerank_search(query: str, k: int = 5) -> list[dict]:
    """Cross-encoder rerank of the hybrid top-25 (decisions.md D-018)."""
    pool = hybrid_search(query, k=25)
    scores = _reranker().predict([(query, c["text"]) for c in pool])
    order = np.argsort(-scores)[:k]
    return [{**pool[i], "rerank_score": float(scores[i])} for i in order]


MODES = {
    "vector": vector_search,
    "hybrid": hybrid_search,
    "hybrid+div": hybrid_diverse_search,
    "strat+div": stratified_diverse_search,
    "patch+div": patch_diverse_search,
    "rewrite": rewrite_search,
    "rerank": rerank_search,
}


def retrieve(query: str, k: int = 5, mode: str = "vector") -> list[dict]:
    """Retrieval entry point; modes map to Phase 3/4 techniques (see decisions.md)."""
    return MODES[mode](query, k)


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What does the Slop parameter do?"
    for r in retrieve(q):
        print(f"{r['similarity']:.3f} [{r['source_type']}] {r['chunk_id']}: {r['text'][:90]!r}")
