"""Reddit Q+A pair chunker (see decisions.md D-008).

One chunk per (question + qualifying answer). The question (title + selftext) is repeated
in every chunk of its thread so answers are retrievable by question-shaped queries.
Qualifying answer: >100 chars, not a bot, and score >= 3 when the score is trustworthy
(live old.reddit scrape); pullpush scores are ingest-time snapshots, so low/missing scores
qualify on length (>250 chars) instead.
"""
import json
from datetime import datetime, timezone

from common import PROCESSED_DIR, RAW_DIR, make_chunk, write_jsonl

REDDIT_DIR = RAW_DIR / "reddit"
LEN_MIN = 100
SCORE_MIN = 3
PULLPUSH_LEN_FALLBACK = 150  # was 250; tuned against eval 2026-06-11 (see D-008 amendment)
SELFTEXT_CAP = 1200  # chars of question body repeated into each chunk
BOT_MARKERS = ("i am a bot", "^(i am a bot)", "*i am a bot*")
BOT_AUTHORS = {"AutoModerator", "synthrecipes-ModTeam", "[deleted]"}
SKIP_BODIES = ("[removed]", "[deleted]")


def qualifies(comment: dict, method: str, op_author: str | None = None) -> bool:
    body = (comment.get("body") or "").strip()
    if len(body) <= LEN_MIN or body.lower() in SKIP_BODIES:
        return False
    if (comment.get("author") or "") in BOT_AUTHORS:
        return False
    if any(m in body.lower() for m in BOT_MARKERS):
        return False
    score = comment.get("score")
    # community-rejected answers (trolls, scams) — never qualify, length notwithstanding
    if score is not None and score < 0:
        return False
    # the question author's own comments are clarifications/promo, not answers
    if op_author and comment.get("author") == op_author:
        return False
    if method == "oldreddit_html":
        return score is None or score >= SCORE_MIN
    # pullpush: trust a good snapshot score, otherwise fall back to length
    return (score is not None and score >= SCORE_MIN) or len(body) > PULLPUSH_LEN_FALLBACK


def iso(created_utc) -> str | None:
    if created_utc in (None, ""):
        return None
    try:
        ts = float(created_utc)
        if ts > 1e12:  # old.reddit data-timestamp is milliseconds
            ts /= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except (ValueError, TypeError):
        return None


def main() -> None:
    chunks = []
    threads = skipped_threads = 0
    for path in sorted(REDDIT_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        sub = data["submission"]
        tid = data["id"]
        title = (sub.get("title") or data.get("title_hint") or "").strip()
        selftext = (sub.get("selftext") or "").strip()
        if selftext.lower() in SKIP_BODIES:
            selftext = ""
        subreddit = sub.get("subreddit") or ""
        permalink = sub.get("permalink") or f"/comments/{tid}/"
        url = f"https://www.reddit.com{permalink}"
        question = f"Reddit r/{subreddit} question: {title}"
        if selftext:
            question += f"\n{selftext[:SELFTEXT_CAP]}"

        good = [c for c in data.get("comments", [])
                if qualifies(c, data.get("method", ""), sub.get("author"))]
        if not good:
            skipped_threads += 1
            continue
        threads += 1
        for c in good:
            text = f"{question}\n\nAnswer: {c['body'].strip()}"
            chunks.append(make_chunk(
                chunk_id=f"reddit-{tid}-{c.get('id') or 'na'}",
                text=text, source_type="reddit", source_id=tid,
                source_url=url, section=None,
                score=c.get("score"), created=iso(sub.get("created_utc"))))
    write_jsonl(PROCESSED_DIR / "chunks_reddit.jsonl", chunks)
    print(f"{threads} threads -> {len(chunks)} Q+A chunks "
          f"({skipped_threads} threads had no qualifying answers)")


if __name__ == "__main__":
    main()
