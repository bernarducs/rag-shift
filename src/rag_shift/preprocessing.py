import os
import re

from nltk.tokenize import sent_tokenize


def clean_text(body: str) -> str:
    # corta o rodapé da newsletter
    for marker in ("RECEBA NOSSAS NEWSLETTERS", "Esta mensagem foi enviada para"):
        body = body.split(marker)[0]
    # remove urls (com ou sem parênteses)
    body = re.sub(r"\(\s*https?://[^\s)]*\s*\)", "", body)
    body = re.sub(r"https?://\S+", "", body)
    # normaliza escapes e espaços
    body = body.replace("\xa0", " ").replace("\r", "")
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\s*\n\s*", "\n", body)
    return body.strip()


def chunk_text(text: str) -> list[str]:
    chunk_size = int(os.environ["CHUNK_SIZE"])
    sentences = sent_tokenize(text, language="portuguese")
    chunks, current = [], []
    for sentence in sentences:
        if current and sum(len(s) for s in current) + len(sentence) > chunk_size:
            chunks.append(" ".join(current))
            # sobreposição de uma sentença
            current = [current[-1]]
        current.append(sentence)
    if current:
        chunks.append(" ".join(current))
    return chunks
