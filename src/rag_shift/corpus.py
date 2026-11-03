import json

from rag_shift.config import CORPUS_DIR
from rag_shift.preprocessing import chunk_text, clean_text


def load_corpus() -> list[dict]:
    chunks = []
    for path in sorted(CORPUS_DIR.glob("*.json")):
        mail = json.loads(path.read_text(encoding="utf-8"))
        for text in chunk_text(clean_text(mail["body"])):
            chunks.append(
                {
                    "mail_id": mail["mail_id"],
                    "subject": mail["subject"],
                    "date": mail["date"],
                    "text": text,
                }
            )
    return chunks
