"""Extract structured recipe chunks from video transcripts (v2 plan, Phase D).

Transcript-only (audio stays out of scope). Chunks carry structured summaries — never
verbatim transcript republication — with timestamped source URLs. Extraction quality is
the spike's go/no-go: the per-video report (eval/video_extraction_report.md) is the
builder's spot-check artifact (provisional gate per D-021).

Usage: python -X utf8 src/acquire/extract_video_recipes.py
Requires ANTHROPIC_API_KEY.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "process"))
import load_env  # noqa: E402,F401
from common import PROCESSED_DIR, make_chunk, write_jsonl  # noqa: E402

VIDEO_DIR = ROOT / "data" / "raw" / "video"
MODEL = "claude-sonnet-4-6"

SYSTEM = """You extract synthesizer sound-design recipes from video transcripts (mostly
Prophet-6 tutorials). Output ONLY JSON:
{"video_quality": "<one sentence: how concretely does the presenter state settings?>",
 "recipes": [
   {"title": "<what sound is built>",
    "start_seconds": <int, where this recipe starts>,
    "summary": "<3-6 sentences IN YOUR OWN WORDS: the signal path and the why>",
    "settings": ["<each concrete setting the presenter states, e.g. 'filter cutoff
                  around 1 o'clock', 'osc 2 detuned slightly sharp', 'LFO triangle to
                  PW 1+2'>"],
    "confidence": "high|medium|low — high only when the presenter states settings
                   explicitly rather than you inferring them"}]}
Rules: never copy transcript sentences verbatim; only include settings actually stated;
if the video is not a sound-design tutorial, return {"video_quality": "...", "recipes": []}."""


def transcript_text(path: Path) -> list[tuple[int, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for ev in data.get("events", []):
        if "segs" not in ev:
            continue
        text = "".join(s.get("utf8", "") for s in ev["segs"]).strip()
        if text:
            out.append((int(ev.get("tStartMs", 0) / 1000), text))
    return out


def main() -> None:
    import anthropic
    client = anthropic.Anthropic()
    chunks, report = [], []
    files = sorted(VIDEO_DIR.glob("*.json3"))
    if not files:
        sys.exit("no caption files in data/raw/video")
    for f in files:
        vid = f.stem.split(".")[0]
        lines = transcript_text(f)
        if not lines:
            report.append(f"- {vid}: empty transcript, skipped")
            continue
        joined = "\n".join(f"[{t}s] {x}" for t, x in lines)
        joined = joined[:60000]
        msg = client.messages.create(
            model=MODEL, max_tokens=3000, temperature=0.2, system=SYSTEM,
            messages=[{"role": "user", "content":
                       f"Video id: {vid}\nTranscript (timestamped):\n\n{joined}"}])
        text = msg.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            report.append(f"- {vid}: extraction unparseable, skipped")
            continue
        n = 0
        for r in data.get("recipes", []):
            if r.get("confidence") == "low" or not r.get("settings"):
                continue
            url = f"https://www.youtube.com/watch?v={vid}&t={r.get('start_seconds', 0)}s"
            body = (f"Video recipe: {r['title']} (Prophet-6 tutorial, "
                    f"confidence {r['confidence']}).\n{r['summary']}\n"
                    "Stated settings:\n" + "\n".join(f"- {s}" for s in r["settings"]))
            chunks.append(make_chunk(
                chunk_id=f"video::{vid}::{r.get('start_seconds', 0)}", text=body,
                source_type="video", source_id=vid, source_url=url,
                section=r["title"]))
            n += 1
        report.append(f"- {vid}: {n} recipes kept "
                      f"(quality: {data.get('video_quality', '?')})")
        print(report[-1], flush=True)
    write_jsonl(PROCESSED_DIR / "chunks_video.jsonl", chunks)
    (ROOT / "eval" / "video_extraction_report.md").write_text(
        "# Video extraction report (Phase D spike)\n\n"
        "**[HUMAN GATE — provisional per D-021: builder should spot-check ~10 extracted "
        "recipes against the videos at the timestamped URLs.]**\n\n"
        + "\n".join(report) + "\n", encoding="utf-8")
    print(f"\nchunks_video.jsonl: {len(chunks)} recipe chunks from {len(files)} videos")


if __name__ == "__main__":
    main()
