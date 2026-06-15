"""Structure-aware chunker for the Prophet-6 manual + OS addenda PDFs (see decisions.md D-007).

Primary path: the manual's embedded TOC gives section boundaries; each heading is located on
its page and text is sliced between consecutive headings. Fallback path (PDFs without a TOC,
e.g. the addenda): font-based heading detection — bold lines noticeably larger than body text.
Target 300-800 tokens per chunk; oversized sections sub-split on paragraph (block) boundaries
with one block of overlap. Section context is prepended into the chunk text itself.
"""
import fitz

from common import PROCESSED_DIR, RAW_DIR, make_chunk, n_tokens, write_jsonl

OFFICIAL = RAW_DIR / "official"
DOCS = [
    # (file, source_id, source_url, doc_label)
    ("prophet6_operation_manual_2.1.pdf", "manual-2.1",
     "https://sequential.com/wp-content/uploads/2021/02/Prophet-6-Operation-Manual-2.1.pdf",
     "Prophet-6 Manual"),
    ("prophet6_addendum_os_1.6.7.pdf", "addendum-1.6.7",
     "https://sequential.com/wp-content/uploads/2022/02/Prophet-6-Manual-Addendum-OS-v1.6.7.pdf",
     "Prophet-6 OS 1.6.7 Addendum"),
    ("prophet6_addendum_os_1.3.1.pdf", "addendum-1.3.1",
     "https://www.davesmithinstruments.com/wp-content/uploads/2016/05/Prophet-6-OS-1.3.1-Addendum.pdf",
     "Prophet-6 OS 1.3.1 Addendum"),
]
SKIP_TOC_TITLES = {"Bookmark 1", "_GoBack", "A Few Words of Thanks"}
MAX_TOKENS = 800
MARGIN = 46  # pts; blocks fully inside top/bottom margins are header/footer candidates


def page_blocks(page) -> list[tuple[float, str]]:
    """(y0, text) per block, headers/footers stripped."""
    out = []
    h = page.rect.height
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        text = text.strip()
        if not text:
            continue
        if (y1 < MARGIN or y0 > h - MARGIN) and len(text) < 80:
            continue  # page number / running footer
        out.append((y0, text))
    return out


def _norm(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def heading_lines(doc) -> list[tuple[int, float, str]]:
    """All bold, short, body-size-or-larger lines in document order: candidate headings."""
    from collections import Counter
    sizes = Counter()
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    sizes[round(span["size"], 1)] += len(span["text"])
    body_size = sizes.most_common(1)[0][0]
    out = []
    for pno, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = " ".join(s["text"] for s in spans).strip()
                # Headings in this family of PDFs: either bold-flagged (level 2,
                # Arial-BoldMT 12pt) or a Black/Bold-named face without the flag
                # (level 1, Arial-Black 18pt). Inline parameter names are bold but
                # body-sized (10pt), so the size floor excludes them.
                if (len(text) < 70
                        and all(s["size"] >= body_size + 0.5 for s in spans)
                        and all(s["flags"] & 16 or "Black" in s["font"] or "Bold" in s["font"]
                                for s in spans)):
                    out.append((pno, line["bbox"][1], text))
    return out


def toc_boundaries(doc) -> list[tuple[int, float, str]]:
    """Section boundaries: TOC titles matched (in order) against bold heading lines found
    by font inspection. The embedded TOC's page numbers are off by one in this manual, so
    TOC supplies the expected section list/order; fonts supply the true locations."""
    candidates = heading_lines(doc)
    boundaries = []
    parent = None
    ci = 0
    for level, title, _page1 in doc.get_toc():
        title = title.strip()
        if title in SKIP_TOC_TITLES:
            continue
        full = title if level == 1 else (f"{parent} - {title}" if parent else title)
        nt = _norm(title)
        for j in range(ci, len(candidates)):
            nc = _norm(candidates[j][2])
            m = min(len(nt), len(nc), 20)
            # mutual-prefix match tolerates typos past char 20 and TOC/page
            # punctuation drift ("Udate"/"Update" both clear the prefix)
            if m >= 4 and nt[:m] == nc[:m]:
                pno, y, _ = candidates[j]
                boundaries.append((pno, y, full))
                ci = j + 1
                break
        else:
            print(f"  WARNING: TOC section not located on page, skipped: {title!r}")
        if level == 1:
            parent = title
    return boundaries


def font_boundaries(doc) -> list[tuple[int, float, str]]:
    """Fallback for PDFs without a TOC: headings = bold lines >= body size + 1.5pt."""
    from collections import Counter
    sizes = Counter()
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    sizes[round(span["size"], 1)] += len(span["text"])
    body_size = sizes.most_common(1)[0][0]
    boundaries = []
    for pno, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = " ".join(s["text"] for s in spans).strip()
                if (len(text) < 60 and not text[0].isdigit()
                        and all(s["size"] >= body_size + 1.5 for s in spans)
                        and all(s["flags"] & 16 for s in spans)):  # bold flag
                    boundaries.append((pno, line["bbox"][1], text))
    return boundaries


def section_texts(doc, boundaries) -> list[tuple[str, list[str]]]:
    """Slice block texts between consecutive boundaries -> (section_name, [paragraphs])."""
    sections = []
    for i, (pno, y, name) in enumerate(boundaries):
        end_pno, end_y = (boundaries[i + 1][0], boundaries[i + 1][1]) if i + 1 < len(boundaries) \
            else (doc.page_count - 1, float("inf"))
        paras = []
        for p in range(pno, end_pno + 1):
            for by, text in page_blocks(doc[p]):
                if p == pno and by < y - 1:
                    continue
                if p == end_pno and by >= end_y - 1:
                    continue
                paras.append(text)
        # The heading line goes into the chunk prefix, so remove it from the body —
        # but only the heading text itself, since heading and body can share a block.
        if paras:
            hname = name.split(" - ")[-1].strip()
            first = paras[0].strip()
            if first.lower().startswith(hname.lower()[: len(hname)]):
                remainder = first[len(hname):].strip()
                if remainder:
                    paras[0] = remainder
                else:
                    paras = paras[1:]
        if paras:
            sections.append((name, paras))
    return sections


def emit_chunks(source_id, source_url, doc_label, sections) -> list[dict]:
    chunks = []
    for name, paras in sections:
        prefix = f"{doc_label} - {name}: "
        # pack paragraphs into <= MAX_TOKENS chunks, 1-paragraph overlap between splits
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
                suffix = f"-{part}" if (part or i < len(paras)) else ""
                chunks.append(make_chunk(
                    chunk_id=f"{source_id}-{slug(name)}{suffix}", text=full,
                    source_type="manual", source_id=source_id,
                    source_url=source_url, section=name))
                part += 1
                buf = [paras[i - 1]] if i < len(paras) else []  # overlap
        # tiny sections fall through with a single chunk; that's intended
    return chunks


def slug(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]


def main() -> None:
    all_chunks = []
    for filename, source_id, url, label in DOCS:
        doc = fitz.open(OFFICIAL / filename)
        boundaries = toc_boundaries(doc) if doc.get_toc() else font_boundaries(doc)
        method = "toc" if doc.get_toc() else "font"
        sections = section_texts(doc, boundaries)
        chunks = emit_chunks(source_id, url, label, sections)
        print(f"{source_id}: {len(sections)} sections -> {len(chunks)} chunks ({method} boundaries)")
        all_chunks.extend(chunks)
    write_jsonl(PROCESSED_DIR / "chunks_manual.jsonl", all_chunks)
    print(f"wrote {len(all_chunks)} chunks")


if __name__ == "__main__":
    main()
