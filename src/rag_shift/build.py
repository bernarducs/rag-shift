import os
import sys

import rag_shift.config  # noqa: F401  (carrega o .env antes dos demais imports)
from rag_shift.config import PROCESSED_DIR
from rag_shift.corpus import build_processed
from rag_shift.preprocessing import ensure_tokenizer


def main() -> None:
    if not os.environ.get("CHUNK_SIZE"):
        sys.exit("Variável ausente no .env: CHUNK_SIZE")

    ensure_tokenizer()
    total = build_processed()
    print(f"{total} emails processados em {PROCESSED_DIR.name}/")
    print("Se o chunking mudou, apague .cache/ para reindexar os embeddings.")
