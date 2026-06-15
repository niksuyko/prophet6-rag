"""Sweep all r/synthrecipes submissions via pullpush (v2 plan, Phases A+C).

v2 of this script: STREAMS each batch to disk and RESUMES from the oldest saved row
(the first version held rows in memory and lost a 29k-row sweep to a late API failure).
On persistent API failure it saves and exits 0 — data is never lost again.

Usage: python -X utf8 src/acquire/fetch_synthrecipes.py
"""
import json
import time

from util import RAW_DIR, polite_get, record, session

API = "https://api.pullpush.io/reddit/search/submission/"
SUB = "synthrecipes"
FLOOR = 1480550400  # 2016-12-01: pre-creation era, nothing below this

KEEP = ("id", "title", "selftext", "score", "num_comments",
        "created_utc", "author", "link_flair_text", "permalink")


def main() -> None:
    out_dir = RAW_DIR / "synthrecipes"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "submissions.jsonl"
    seen: set[str] = set()
    before = None
    if dest.exists():  # resume
        for line in dest.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            seen.add(row["id"])
            ts = int(row["created_utc"])
            before = ts if before is None else min(before, ts)
        print(f"resuming: {len(seen)} rows on disk, before={before}", flush=True)

    sess = session()
    exhausted = False
    with dest.open("a", encoding="utf-8") as f:
        while not exhausted:
            params = {"subreddit": SUB, "size": 100, "sort": "desc",
                      "sort_type": "created_utc"}
            if before:
                params["before"] = before
            batch = None
            for attempt in range(6):
                try:
                    resp = polite_get(sess, API, min_interval=2.5, params=params)
                    if resp.status_code == 200:
                        batch = resp.json().get("data", [])
                        break
                    print(f"retry {attempt + 1}: HTTP {resp.status_code}", flush=True)
                except Exception as e:
                    print(f"retry {attempt + 1}: {type(e).__name__}", flush=True)
                time.sleep(min(20 * (attempt + 1), 120))
            if batch is None:
                print("API persistently failing — saved progress retained; rerun to resume.",
                      flush=True)
                break
            fresh = [d for d in batch if d.get("id") not in seen]
            if not fresh:
                exhausted = True
                break
            for d in fresh:
                seen.add(d["id"])
                f.write(json.dumps({k: d.get(k) for k in KEEP}) + "\n")
            f.flush()
            before = int(min(d["created_utc"] for d in fresh))
            print(f"{len(seen)} submissions (back to "
                  f"{time.strftime('%Y-%m', time.gmtime(before))})", flush=True)
            if before < FLOOR:
                exhausted = True
    if exhausted:
        record("synthrecipes/submissions.jsonl", f"{API}?subreddit={SUB}",
               note=f"full submission sweep, {len(seen)} posts (streamed/resumable)")
        print(f"COMPLETE: {len(seen)} submissions -> {dest}")
    else:
        print(f"PARTIAL: {len(seen)} submissions saved; rerun to resume")


if __name__ == "__main__":
    main()
