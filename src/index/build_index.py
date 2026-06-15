"""Build the vector index from data/chunks/chunks.jsonl (see decisions.md D-010).

One command, rebuilds from scratch:  python src/index/build_index.py
Writes data/index/: embeddings.npy (row-aligned with chunks.meta.jsonl) + index_meta.json.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "process"))
from common import CHUNKS_FILE, read_jsonl  # noqa: E402

INDEX_DIR = ROOT / "data" / "index"
MODEL_NAME = "BAAI/bge-base-en-v1.5"
BATCH = 32


def main() -> None:
    from sentence_transformers import SentenceTransformer

    chunks = read_jsonl(CHUNKS_FILE)
    print(f"embedding {len(chunks)} chunks with {MODEL_NAME} (CPU)...")
    t0 = time.time()
    model = SentenceTransformer(MODEL_NAME)
    vecs = model.encode([c["text"] for c in chunks], batch_size=BATCH,
                        normalize_embeddings=True, show_progress_bar=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(INDEX_DIR / "embeddings.npy", vecs.astype(np.float32))
    (INDEX_DIR / "chunks.meta.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding="utf-8")
    (INDEX_DIR / "index_meta.json").write_text(json.dumps({
        "model": MODEL_NAME, "dim": int(vecs.shape[1]), "n_chunks": len(chunks),
        "normalized": True, "built_seconds": round(time.time() - t0, 1),
    }, indent=2))
    print(f"index built: {vecs.shape} in {time.time() - t0:.0f}s -> {INDEX_DIR}")


if __name__ == "__main__":
    main()
