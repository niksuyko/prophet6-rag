"""Acquire Prophet-6 reddit threads into data/raw/reddit/ — one JSON file per thread.

Two unauthenticated paths (see decisions.md D-004):
  1. pullpush.io JSON API (Pushshift successor): submissions + full comments, coverage ~2015-mid 2025.
  2. old.reddit.com HTML scrape (works from a residential IP with a browser UA): fallback for
     threads pullpush misses, and search for recent posts.

Thread sources: seed_threads.json (hand-curated by targeted search) + pullpush search with
query variants + old.reddit search (sort=new) for recency. Cast wide, disambiguate at chunking.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup
from util import RAW_DIR, polite_get, record, session

PULLPUSH = "https://api.pullpush.io/reddit"
SEARCH_SUBS = ["synthesizers", "synthrecipes"]
# NB: pullpush parses "prophet-6" as (prophet NOT 6); quoted phrase + bare word cover variants.
PULLPUSH_QUERIES = ['"prophet 6"', "prophet6"]
OLDREDDIT_QUERIES = ['"prophet 6"', "prophet6"]
MAX_EXTRA_THREADS = 80  # cap on non-seed threads fetched in full

OUT_DIR = RAW_DIR / "reddit"


def pullpush_search(sess) -> dict[str, dict]:
    """Search pullpush for candidate submissions. Returns {id: submission_raw}."""
    found = {}
    for sub in SEARCH_SUBS:
        for q in PULLPUSH_QUERIES:
            url = f"{PULLPUSH}/search/submission/?q={q}&subreddit={sub}&size=100"
            try:
                resp = polite_get(sess, url, min_interval=2.0)
                data = resp.json().get("data", [])
            except Exception as e:  # noqa: BLE001
                print(f"  search failed ({sub}, {q}): {e}")
                continue
            for s in data:
                found[s["id"]] = s
            print(f"  pullpush search {sub} {q}: {len(data)} hits")
    return found


def oldreddit_search(sess) -> dict[str, str]:
    """Search old.reddit (sort=new) for recent threads pullpush may miss. Returns {id: title}."""
    found = {}
    for sub in SEARCH_SUBS:
        for q in OLDREDDIT_QUERIES:
            url = (f"https://old.reddit.com/r/{sub}/search/?q={q}"
                   f"&restrict_sr=on&sort=new&t=all")
            try:
                resp = polite_get(sess, url, min_interval=3.0)
                resp.raise_for_status()
            except Exception as e:  # noqa: BLE001
                print(f"  old.reddit search failed ({sub}, {q}): {e}")
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            hits = 0
            for a in soup.select("a.search-title"):
                m = re.search(r"/comments/([a-z0-9]+)/", a.get("href", ""))
                if m:
                    found[m.group(1)] = a.get_text(strip=True)
                    hits += 1
            print(f"  old.reddit search {sub} {q}: {hits} hits")
    return found


def fetch_thread_pullpush(sess, tid: str) -> dict | None:
    """Fetch submission + comments from pullpush. None if submission not indexed."""
    sub_resp = polite_get(sess, f"{PULLPUSH}/search/submission/?ids={tid}", min_interval=2.0)
    subs = sub_resp.json().get("data", [])
    if not subs:
        return None
    com_resp = polite_get(sess, f"{PULLPUSH}/search/comment/?link_id={tid}&size=100", min_interval=2.0)
    comments = com_resp.json().get("data", [])
    return {"submission": subs[0], "comments": comments,
            "comments_possibly_truncated": len(comments) == 100}


def fetch_thread_oldreddit(sess, tid: str) -> dict | None:
    """Scrape an old.reddit thread page; parse title/selftext/score and flat comment list."""
    url = f"https://old.reddit.com/comments/{tid}/"
    resp = polite_get(sess, url, min_interval=3.0)
    if resp.status_code != 200:
        return None
    (OUT_DIR / f"{tid}.html").write_text(resp.text, encoding="utf-8")  # keep true raw
    soup = BeautifulSoup(resp.text, "html.parser")
    post = soup.select_one("div.thing.link")
    if post is None:
        return None

    def md_text(node):
        return node.get_text("\n", strip=True) if node else ""

    title_el = post.select_one("a.title")
    selftext_el = post.select_one("div.expando div.usertext-body")
    score_el = post.select_one("div.score.unvoted")
    submission = {
        "id": tid,
        "title": md_text(title_el),
        "selftext": md_text(selftext_el),
        "score": (score_el.get("title") if score_el else None),
        "subreddit": (post.get("data-subreddit") or ""),
        "permalink": post.get("data-permalink") or f"/comments/{tid}/",
        "created_utc": post.get("data-timestamp"),
    }
    comments = []
    for c in soup.select("div.commentarea div.thing.comment"):
        body = c.select_one("div.usertext-body")
        score_span = c.select_one("span.score.unvoted")
        score = None
        if score_span:
            m = re.search(r"(-?\d+)", score_span.get_text())
            score = int(m.group(1)) if m else None
        comments.append({
            "id": (c.get("data-fullname") or "").replace("t1_", ""),
            "parent_id": None,  # nesting not reconstructed; depth via CSS class below
            "depth": len(c.find_parents("div", class_="comment")),
            "body": md_text(body),
            "score": score,
            "author": c.get("data-author"),
        })
    return {"submission": submission, "comments": comments, "comments_possibly_truncated": False}


def save_thread(tid: str, data: dict, method: str, bucket_hint, title_hint: str) -> None:
    envelope = {
        "id": tid,
        "retrieved": date.today().isoformat(),
        "method": method,
        "bucket_hint": bucket_hint,
        "title_hint": title_hint,
        **data,
    }
    path = OUT_DIR / f"{tid}.json"
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=1), encoding="utf-8")
    perma = envelope["submission"].get("permalink", f"/comments/{tid}/")
    record(f"reddit/{tid}.json", f"https://www.reddit.com{perma}",
           method=method, n_comments=len(envelope["comments"]))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sess = session()
    seeds = json.loads((Path(__file__).parent / "seed_threads.json").read_text(encoding="utf-8"))["threads"]
    seed_map = {t["id"]: t for t in seeds}

    print("== searching for additional candidates ==")
    pp_found = pullpush_search(sess)
    or_found = oldreddit_search(sess)
    extra_ids = [i for i in {**dict.fromkeys(pp_found), **dict.fromkeys(or_found)} if i not in seed_map]
    extra_ids = extra_ids[:MAX_EXTRA_THREADS]
    print(f"seeds: {len(seed_map)}, extra candidates: {len(extra_ids)}")

    todo = [(tid, t["bucket_hint"], t["title"]) for tid, t in seed_map.items()]
    todo += [(tid, None, pp_found.get(tid, {}).get("title") or or_found.get(tid, ""))
             for tid in extra_ids]

    ok = fail = skip = 0
    for tid, bucket_hint, title_hint in todo:
        if (OUT_DIR / f"{tid}.json").exists():
            skip += 1
            continue
        try:
            data = fetch_thread_pullpush(sess, tid)
            method = "pullpush"
            # pullpush sometimes indexes a submission but none of its comments —
            # a Q&A thread with zero answers is worthless, so scrape live instead
            if data is None or not data["comments"]:
                html_data = fetch_thread_oldreddit(sess, tid)
                if html_data is not None:
                    data, method = html_data, "oldreddit_html"
            if data is None:
                raise RuntimeError("not found via pullpush or old.reddit")
            save_thread(tid, data, method, bucket_hint, title_hint)
            ok += 1
            print(f"saved {tid} [{method}] ({len(data['comments'])} comments) {title_hint[:60]}")
        except Exception as e:  # noqa: BLE001
            fail += 1
            print(f"FAILED {tid}: {e}")

    print(f"\ndone: {ok} saved, {skip} already present, {fail} failed")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
