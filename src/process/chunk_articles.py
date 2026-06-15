"""HTML chunker for Tier-3 articles and official support/KB pages (see decisions.md D-009).

Extraction: prefer <article>, fall back to <main>, then <body>; drop script/style/nav/
header/footer/aside/form. Split on h2/h3 headings, pack paragraphs to <= 800 tokens,
prepend "Article — <title> — <section>: " context into each chunk.
"""
import json
import re

from bs4 import BeautifulSoup
from common import PROCESSED_DIR, RAW_DIR, make_chunk, n_tokens, write_jsonl

MAX_TOKENS = 800
MIN_CHUNK_TOKENS = 40  # drop boilerplate crumbs
DROP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript",
             "iframe", "button", "figure"]

INPUTS = [
    # (dir, source_type, label_prefix)
    (RAW_DIR / "articles", "article", "Article"),
    (RAW_DIR / "official", "official_kb", "Sequential support"),
]


def manifest_urls() -> dict[str, str]:
    urls = {}
    for line in (RAW_DIR / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        urls[entry["file"]] = entry["source_url"]
    return urls


def extract_sections(html: str) -> tuple[str, list[tuple[str, list[str]]]]:
    """-> (page_title, [(section_heading, [paragraph texts])])"""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    title = re.split(r"\s*[|—–]\s*", title)[0].strip()  # drop " | Site Name" tails
    for tag in soup(DROP_TAGS):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    sections, current_head, current_paras = [], "", []
    for el in root.find_all(["h1", "h2", "h3", "p", "li", "pre", "td"]):
        text = el.get_text(" ", strip=True)
        if not text or (el.name != "h2" and el.name != "h3" and len(text) < 20):
            continue  # single-word crumbs: share buttons, tag lists
        if el.name == "td" and el.find(["p", "li"]):
            continue  # avoid double-extracting cells whose content we already walk
        low = text.lower()
        if "sign up" in low and ("inbox" in low or "newsletter" in low):
            continue  # mid-article newsletter boilerplate
        if el.name in ("h2", "h3"):
            if current_paras:
                sections.append((current_head, current_paras))
            current_head, current_paras = text, []
        elif el.name == "h1":
            continue
        else:
            current_paras.append(text)
    if current_paras:
        sections.append((current_head, current_paras))
    return title, sections


def main() -> None:
    urls = manifest_urls()
    chunks = []
    for in_dir, source_type, label in INPUTS:
        for path in sorted(in_dir.glob("*.html")):
            slug = path.stem
            html = path.read_text(encoding="utf-8", errors="replace")
            title, sections = extract_sections(html)
            url = urls.get(f"{in_dir.name}/{path.name}", "")
            n_before = len(chunks)
            for sec_head, paras in sections:
                sec_name = sec_head or title
                prefix = f"{label} - {title}" + (f" - {sec_head}: " if sec_head else ": ")
                buf, part = [], 0
                i = 0
                while i < len(paras):
                    buf.append(paras[i])
                    i += 1
                    full = prefix + "\n\n".join(buf)
                    if n_tokens(full) > MAX_TOKENS or i == len(paras):
                        if n_tokens(full) > MAX_TOKENS and len(buf) > 1:
                            buf.pop()
                            i -= 1
                            full = prefix + "\n\n".join(buf)
                        if n_tokens(full) >= MIN_CHUNK_TOKENS:
                            sec_slug = re.sub(r"[^a-z0-9]+", "-", sec_name.lower()).strip("-")[:40]
                            chunks.append(make_chunk(
                                chunk_id=f"{slug}-{sec_slug}-{part}",
                                text=full, source_type=source_type, source_id=slug,
                                source_url=url, section=sec_name))
                        part += 1
                        buf = []
            print(f"{slug}: {len(chunks) - n_before} chunks (title: {title[:50]!r})")
    write_jsonl(PROCESSED_DIR / "chunks_articles.jsonl", chunks)
    print(f"wrote {len(chunks)} chunks")


if __name__ == "__main__":
    main()
