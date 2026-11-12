import hashlib
import json
import sys
from pathlib import Path

from rag_shift.config import CORPUS_DIR, PROCESSED_DIR
from rag_shift.preprocessing import (
    HEADING_RE,
    chunk_section,
    extract_links,
    link_text,
    normalize,
    split_paragraphs,
    split_sections,
    strip_boilerplate,
)


def load_mail(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def links_aligned(mail: dict) -> bool:
    # os links só são atribuídos se o texto com urls tem os mesmos títulos do normalizado
    return len(HEADING_RE.findall(link_text(mail["body"]))) == len(
        HEADING_RE.findall(normalize(mail["body"]))
    )


def links_by_heading(mail: dict) -> dict[int | None, list[dict]]:
    """Links de cada título (índice do match de HEADING_RE); None = email sem títulos."""
    text = link_text(mail["body"])
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return {None: extract_links(text)}
    ends = [m.start() for m in matches[1:]] + [len(text)]
    return {i: extract_links(text[m.start():end]) for i, (m, end) in enumerate(zip(matches, ends))}


def process_mail(mail: dict) -> dict:
    sections = []
    links = links_by_heading(mail) if links_aligned(mail) else {}
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
                # não entram no hash; recalculados a cada build
                "links": links.get(section["heading"], []),
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


def build_processed() -> tuple[int, int]:
    """Grava a pasta processada. Devolve (emails, emails sem links por títulos divergentes)."""
    PROCESSED_DIR.mkdir(exist_ok=True)
    raw_paths = sorted(CORPUS_DIR.glob("*.json"))
    misaligned = 0
    for path in raw_paths:
        out_path = PROCESSED_DIR / path.name
        # preserva o enrichment (caro de gerar) das matérias cujo texto não mudou
        enrichments = {}
        if out_path.exists():
            old = load_mail(out_path)
            enrichments = {s["hash"]: s["enrichment"] for s in old["sections"]}
        mail = load_mail(path)
        misaligned += not links_aligned(mail)
        processed = process_mail(mail)
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
    return len(raw_paths), misaligned


def load_corpus() -> list[dict]:
    paths = sorted(PROCESSED_DIR.glob("*.json"))
    if not paths:
        sys.exit("Pasta processada vazia. Rode antes: uv run rag-shift-build")
    chunks = []
    for path in paths:
        chunks.extend(flatten(load_mail(path)))
    return chunks


def load_processed() -> dict[int, dict]:
    return {
        mail["mail_id"]: mail
        for mail in (load_mail(path) for path in sorted(PROCESSED_DIR.glob("*.json")))
    }


def find_links(doc: dict, processed: dict[int, dict]) -> list[dict]:
    """Links da matéria de um chunk (payload do índice), achada pelo texto do chunk."""
    mail = processed.get(doc["mail_id"])
    for section in mail["sections"] if mail else []:
        if doc["text"] in section["chunks"]:
            return section.get("links", [])
    return []
