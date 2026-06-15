"""One-off: dump line-level font details around the Slop/Mixer pages to learn
exactly how level-1 vs level-2 headings are styled in this manual."""
from pathlib import Path

import fitz

PDF = Path(__file__).resolve().parents[2] / "data" / "raw" / "official" / "prophet6_operation_manual_2.1.pdf"
doc = fitz.open(PDF)

for pno in (47, 48, 49, 50):
    print(f"\n===== page index {pno} =====")
    for block in doc[pno].get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = " ".join(s["text"] for s in spans).strip()
            if len(text) < 70 and spans[0]["size"] >= 11.5:
                s = spans[0]
                print(f"  size={s['size']:.1f} flags={s['flags']} font={s['font']!r}: {text[:60]}")
