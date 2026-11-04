import hashlib
import json
import sys
from pathlib import Path

from rag_shift.config import CORPUS_DIR, PROCESSED_DIR
from rag_shift.preprocessing import (
    chunk_section,
    normalize,
    split_paragraphs,
    split_sections,
    strip_boilerplate,
)


def load_mail(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def process_mail(mail: dict) -> dict:
    sections = []
    for section in split_sections(normalize(mail["body"]), mail["subject"]):
        paragraphs = split_paragraphs(strip_boilerplate(section["body"]))
        chunks = chunk_section(paragraphs)
        if not chunks:
            continue
        sections.append(
            {
                "edition": section["edition"],
                "section": section["section"],
                "title": section["title"],
                # hash do texto da matéria: não muda com CHUNK_SIZE
                "hash": hashlib.sha1("\n\n".join(paragraphs).encode("utf-8")).hexdigest(),
                "chunks": chunks,
                "enrichment": {},
            }
        )
    return {
        "mail_id": mail["mail_id"],
        "subject": mail["subject"],
        "date": mail["date"],
        "sections": sections,
    }


def flatten(processed: dict) -> list[dict]:
    return [
        {
            "mail_id": processed["mail_id"],
            "subject": processed["subject"],
            "date": processed["date"],
            "edition": section["edition"],
            "section": section["section"],
            "title": section["title"],
            "text": text,
        }
        for section in processed["sections"]
        for text in section["chunks"]
    ]


def chunk_mail(mail: dict) -> list[dict]:
    return flatten(process_mail(mail))


def build_processed() -> int:
    PROCESSED_DIR.mkdir(exist_ok=True)
    raw_paths = sorted(CORPUS_DIR.glob("*.json"))
    for path in raw_paths:
        out_path = PROCESSED_DIR / path.name
        # preserva o enrichment (caro de gerar) das matérias cujo texto não mudou
        enrichments = {}
        if out_path.exists():
            old = load_mail(out_path)
            enrichments = {s["hash"]: s["enrichment"] for s in old["sections"]}
        processed = process_mail(load_mail(path))
        for section in processed["sections"]:
            section["enrichment"] = enrichments.get(section["hash"], {})
        out_path.write_text(
            json.dumps(processed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    # remove processados sem email bruto correspondente
    raw_names = {path.name for path in raw_paths}
    for out_path in PROCESSED_DIR.glob("*.json"):
        if out_path.name not in raw_names:
            out_path.unlink()
    return len(raw_paths)


def load_corpus() -> list[dict]:
    paths = sorted(PROCESSED_DIR.glob("*.json"))
    if not paths:
        sys.exit("Pasta processada vazia. Rode antes: uv run rag-shift-build")
    chunks = []
    for path in paths:
        chunks.extend(flatten(load_mail(path)))
    return chunks
