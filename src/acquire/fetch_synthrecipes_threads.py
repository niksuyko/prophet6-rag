"""Fetch selected r/synthrecipes threads into data/raw/reddit/ (v2 plan, Phase C wave 2).

Selection: every thread targeted by golden_set_v2 entries, plus the top-N submissions by
engagement (score + 2*comments, >=3 comments). Reuses the v1 thread pipeline (pullpush +
old.reddit fallback, same envelope JSON) so chunk_reddit.py ingests them unchanged.

Usage: python -X utf8 src/acquire/fetch_synthrecipes_threads.py [top_n] [shard] [n_shards] [min_comments]
(shard/n_shards allow parallel workers over interleaved slices; resumable via skip-exists.
min_comments default 3 = the documented quality floor; lower it for measured experiments.)
"""
import json
import sys
from pathlib import Path

from fetch_reddit import OUT_DIR, fetch_thread_oldreddit, fetch_thread_pullpush, save_thread
from util import RAW_DIR, session

ROOT = Path(__file__).resolve().parents[2]
SUBS = RAW_DIR / "synthrecipes" / "submissions.jsonl"
GOLDEN_V2 = ROOT / "eval" / "golden_set_v2.jsonl"


def main() -> None:
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    shard = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    n_shards = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    min_comments = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    subs = [json.loads(l) for l in SUBS.read_text(encoding="utf-8").splitlines()]
    by_id = {s["id"]: s for s in subs}

    must = set()
    if GOLDEN_V2.exists():
        for line in GOLDEN_V2.read_text(encoding="utf-8").splitlines():
            g = json.loads(line)
            for t in g.get("expected_targets", []):
                if t["source_type"] == "reddit" and t["match"] in by_id:
                    must.add(t["match"])

    ranked = sorted((s for s in subs if (s.get("num_comments") or 0) >= min_comments),
                    key=lambda s: -((s.get("score") or 0) + 2 * (s.get("num_comments") or 0)))
    selected = list(dict.fromkeys(list(must) + [s["id"] for s in ranked[:top_n]]))
    selected = selected[shard::n_shards]
    print(f"{len(selected)} threads in shard {shard}/{n_shards} "
          f"(min_comments={min_comments}, {len(must)} golden-targeted overall)", flush=True)

    sess = session()
    ok = skip = fail = 0
    for i, tid in enumerate(selected, 1):
        if (OUT_DIR / f"{tid}.json").exists():
            skip += 1
            continue
        try:
            data = fetch_thread_pullpush(sess, tid)
            method = "pullpush"
        except Exception:
            data = None
        if data is None or not data["comments"]:
            try:
                data = fetch_thread_oldreddit(sess, tid)
                method = "oldreddit"
            except Exception:
                data = None
        if data is None or not data.get("comments"):
            fail += 1
            if fail <= 20:
                print(f"FAIL {tid} ({by_id[tid]['title'][:50]!r})", flush=True)
            continue
        save_thread(tid, data, method, "recipe", by_id[tid]["title"])
        ok += 1
        if i % 50 == 0:
            print(f"{i}/{len(selected)} (ok {ok}, skip {skip}, fail {fail})", flush=True)
    print(f"done: ok {ok}, skip {skip}, fail {fail} of {len(selected)}")


if __name__ == "__main__":
    main()
