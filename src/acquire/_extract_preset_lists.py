import json
from pathlib import Path

import fitz  # pymupdf

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "patches"

for name in ("p6_factory_presets_list.pdf", "p6_omom_presets_list.pdf"):
    doc = fitz.open(RAW / name)
    print(f"=== {name}: {doc.page_count} pages")
    for page in doc:
        text = page.get_text()
        print(text[:1800])
        print("--- page break ---")
        if page.number >= 1:
            break
    doc.close()
