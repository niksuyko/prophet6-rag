"""One-off inspection: dump the manual's embedded TOC (if any) and font-size stats,
to design the structure-aware chunker and the golden set's expected_section names."""
from collections import Counter
from pathlib import Path

import fitz

PDF = Path(__file__).resolve().parents[2] / "data" / "raw" / "official" / "prophet6_operation_manual_2.1.pdf"

doc = fitz.open(PDF)
print(f"pages: {doc.page_count}")
toc = doc.get_toc()
if toc:
    print(f"embedded TOC ({len(toc)} entries):")
    for lvl, title, page in toc:
        print(f"{'  ' * (lvl - 1)}{title}  [p{page}]")
else:
    print("NO embedded TOC")

print("\nfont sizes across sample pages (size, bold) -> count:")
sizes = Counter()
for pno in range(0, doc.page_count, 3):
    for block in doc[pno].get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                bold = bool(span["flags"] & 2 ** 4)
                sizes[(round(span["size"], 1), bold)] += len(span["text"])
for (size, bold), n in sizes.most_common(12):
    print(f"  size={size} bold={bold}: {n} chars")
