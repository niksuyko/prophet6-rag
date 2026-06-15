"""LLM query expansion for retrieval (decisions.md D-017).

Expansions are cached in data/index/rewrite_cache.json so eval runs are deterministic
and re-runs are free.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import load_env  # noqa: E402,F401

CACHE_FILE = ROOT / "data" / "index" / "rewrite_cache.json"
REWRITE_MODEL = "claude-haiku-4-5-20251001"

PROMPT = """Rewrite this Prophet-6 synthesizer question into 2-3 short search queries that
together cover what's being asked. For cross-synth questions ("X-style sound on the P6"),
decompose into: what characterizes that target sound, and which Prophet-6 features/settings
produce it. For terse or slangy questions, expand abbreviations and add synonyms.
Return JSON only: {"queries": ["...", "..."]}

Question: """


def _cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def expand_query(query: str) -> list[str]:
    cache = _cache()
    if query in cache:
        return cache[query]
    import anthropic
    msg = anthropic.Anthropic().messages.create(
        model=REWRITE_MODEL, max_tokens=300, temperature=0,
        messages=[{"role": "user", "content": PROMPT + query}])
    text = msg.content[0].text
    subs = json.loads(text[text.find("{"):text.rfind("}") + 1])["queries"][:3]
    cache[query] = subs
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    return subs
