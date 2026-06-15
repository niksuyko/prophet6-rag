"""Shared helpers for the processing stage: chunk schema, token estimate, synth tagging, cleaning."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CHUNKS_FILE = ROOT / "data" / "chunks" / "chunks.jsonl"

# Rough token estimate (no tokenizer dependency needed for sizing decisions).
def n_tokens(text: str) -> int:
    return int(len(text.split()) * 1.33)


SYNTH_PATTERNS = {
    "prophet-6": r"prophet[\s\-]?(6|six)\b|\bp[\s\-]?6\b",
    "prophet-5": r"prophet[\s\-]?(5|10|five)\b|\brev[\s\-]?4\b",
    "prophet-rev2": r"\brev[\s\-]?2\b|prophet[\s\-]?0?8\b",
    "ob-6": r"\bob[\s\-]?6\b",
    "oberheim": r"oberheim|\bob[\s\-]?x[a8]?\b|\bobx\b",
    "juno": r"juno[\s\-]?(6|60|106)?\b|\bhs[\s\-]?60\b",
    "jupiter": r"jupiter[\s\-]?[468]\b",
    "moog": r"mini\s?moog|\bmoog\b|model\s?d\b",
    "dx7": r"\bdx[\s\-]?7\b",
    "cs-80": r"\bcs[\s\-]?80\b",
    "solina": r"solina|string\s?machine|arp\s?omni",
}
_COMPILED = {name: re.compile(pat, re.I) for name, pat in SYNTH_PATTERNS.items()}


def synths_mentioned(text: str) -> list[str]:
    return [name for name, rx in _COMPILED.items() if rx.search(text)]


_MOJIBAKE = {"’": "'", "‘": "'", "“": '"', "”": '"',
             "–": "-", "—": "-", "�": "'", "\xa0": " ", "­": ""}


def clean_text(text: str) -> str:
    for bad, good in _MOJIBAKE.items():
        text = text.replace(bad, good)
    text = re.sub(r"&(amp|lt|gt|#x200B);", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_chunk(chunk_id: str, text: str, source_type: str, source_id: str,
               source_url: str, section: str | None, score: int | None = None,
               created: str | None = None) -> dict:
    text = clean_text(text)
    return {
        "chunk_id": chunk_id,
        "text": text,
        "source_type": source_type,   # manual | reddit | article | official_kb
        "source_id": source_id,       # thread id / article slug / manual doc id
        "source_url": source_url,
        "section": section,
        "synths_mentioned": synths_mentioned(text),
        "score": score,
        "created": created,
        "n_tokens": n_tokens(text),
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
