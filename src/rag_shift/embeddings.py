import json
import os
import sys

import numpy as np
from sentence_transformers import SentenceTransformer

from rag_shift.config import CACHE_DIR
from rag_shift.corpus import load_corpus


def load_model() -> SentenceTransformer:
    return SentenceTransformer(os.environ["EMBEDDING_MODEL"])


def get_embeddings(model: SentenceTransformer) -> tuple[np.ndarray, list[dict]]:
    vectors_path = CACHE_DIR / "embeddings.npy"
    chunks_path = CACHE_DIR / "chunks.json"
    # reaproveita o cache para não reindexar o corpus a cada execução
    if vectors_path.exists() and chunks_path.exists():
        return np.load(vectors_path), json.loads(chunks_path.read_text(encoding="utf-8"))

    chunks = load_corpus()
    print(f"Indexando {len(chunks)} chunks (primeira execução)...", file=sys.stderr)
    vectors = model.encode(
        ["passage: " + c["text"] for c in chunks],
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    CACHE_DIR.mkdir(exist_ok=True)
    np.save(vectors_path, vectors)
    chunks_path.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    return vectors, chunks
