"""Shared helpers for acquisition scripts: polite HTTP session + raw-data manifest."""
import hashlib
import json
import time
from datetime import date
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
MANIFEST = RAW_DIR / "manifest.jsonl"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

_last_request = 0.0


def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = BROWSER_UA
    return s


def polite_get(sess: requests.Session, url: str, min_interval: float = 1.5, **kw) -> requests.Response:
    """GET with a global minimum interval between requests."""
    global _last_request
    wait = min_interval - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    resp = sess.get(url, timeout=60, **kw)
    _last_request = time.time()
    return resp


def record(rel_path: str, source_url: str, **extra) -> None:
    """Append a manifest entry: every raw file gets source URL + retrieval date."""
    path = RAW_DIR / rel_path
    entry = {
        "file": rel_path,
        "source_url": source_url,
        "retrieved": date.today().isoformat(),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
        **extra,
    }
    with MANIFEST.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
