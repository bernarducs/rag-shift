"""Inspeciona o chunking sem gerar embeddings.

Uso:
    uv run python scripts/inspect_chunks.py            # sorteia 3 emails
    uv run python scripts/inspect_chunks.py a.json b.json
    uv run python scripts/inspect_chunks.py --stats    # estatísticas do corpus todo
"""

import random
import statistics
import sys
from pathlib import Path

from rag_shift.config import CORPUS_DIR
from rag_shift.corpus import chunk_mail, load_mail
from rag_shift.preprocessing import ensure_tokenizer, heading_path


def show(path: Path) -> None:
    mail = load_mail(path)
    chunks = chunk_mail(mail)
    print(f"\n===== {mail['date'][:10]} | {mail['subject']} | {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        print(f"\n--- [{i}] {heading_path(chunk)} ({len(chunk['text'])} chars)")
        print(chunk["text"])


def stats() -> None:
    sizes, per_mail, fallback = [], [], []
    for path in sorted(CORPUS_DIR.glob("*.json")):
        chunks = chunk_mail(load_mail(path))
        sizes.extend(len(c["text"]) for c in chunks)
        per_mail.append(len(chunks))
        if all(not c["edition"] for c in chunks):
            fallback.append(path.name)
    print(f"emails: {len(per_mail)} | chunks: {len(sizes)}")
    print(f"chunks por email: média {statistics.mean(per_mail):.1f}, máx {max(per_mail)}")
    print(
        f"tamanho (chars): média {statistics.mean(sizes):.0f}, "
        f"mediana {statistics.median(sizes):.0f}, máx {max(sizes)}, "
        f"< 100: {sum(s < 100 for s in sizes)}, > 2000: {sum(s > 2000 for s in sizes)}"
    )
    print(f"emails no fallback (sem títulos): {len(fallback)}")
    for name in fallback:
        print("  ", name)


def main() -> None:
    ensure_tokenizer()
    args = sys.argv[1:]
    if args == ["--stats"]:
        stats()
        return
    paths = [Path(a) for a in args] or random.sample(sorted(CORPUS_DIR.glob("*.json")), 3)
    for path in paths:
        show(path)


if __name__ == "__main__":
    main()
