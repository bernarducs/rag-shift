import argparse
import os
import sys

import rag_shift.config  # noqa: F401  (carrega o .env antes dos demais imports)
from rag_shift.config import PROCESSED_DIR
from rag_shift.corpus import build_processed
from rag_shift.preprocessing import ensure_tokenizer


def main() -> None:
    argparse.ArgumentParser(
        prog="rag-shift-build",
        description=(
            "Lê os emails brutos (the-shift-mails-outputs/), aplica o chunking estrutural "
            "e grava os JSONs em the-shift-mails-processed/, preservando o enrichment "
            "das matérias que não mudaram."
        ),
        epilog="Se o chunking mudou, apague .cache/ para reindexar os embeddings.",
    ).parse_args()

    if not os.environ.get("CHUNK_SIZE"):
        sys.exit("Variável ausente no .env: CHUNK_SIZE")

    ensure_tokenizer()
    total, misaligned = build_processed()
    print(f"{total} emails processados em {PROCESSED_DIR.name}/")
    if misaligned:
        print(f"{misaligned} emails ficaram sem links (títulos do texto com urls não batem).")
    print("Se o chunking mudou, apague .cache/ para reindexar os embeddings.")
