import os
import re

import nltk
from nltk.tokenize import sent_tokenize

FOOTER_MARKERS = ("RECEBA NOSSAS NEWSLETTERS", "Esta mensagem foi enviada para")
# título de matéria: "** Título" seguido de uma linha de traços
HEADING_RE = re.compile(r"^\*\* (.+)\n-{20,}[ \t]*$", re.MULTILINE)
# linhas de boilerplate da abertura da edição
BOILERPLATE_RE = re.compile(
    r"^(.*,\s*bom dia!"
    r"|\*?\s*Recebeu essa newsletter.*"
    r"|Boa leitura\."
    r"|COMPARTILHE NO WHATSAPP.*"
    r"|[\s*=\-]*)$"
)


def ensure_tokenizer() -> None:
    # baixa o tokenizer apenas se ainda não existir localmente
    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab", quiet=True)


def normalize(body: str) -> str:
    # corta o rodapé da newsletter
    for marker in FOOTER_MARKERS:
        body = body.split(marker)[0]
    # padroniza quebras e caracteres invisíveis, preservando a estrutura de \n
    body = body.replace("\r\n", "\n").replace("\r", "")
    body = body.replace("\xa0", " ")
    body = re.sub(r"[​‌‍﻿]", "", body)
    # remove urls (com ou sem parênteses)
    body = re.sub(r"\(\s*https?://[^\s)]*\s*\)", "", body)
    body = re.sub(r"https?://\S+", "", body)
    # espaços sobrando, inclusive antes de pontuação deixados pelas urls
    body = re.sub(r"[ \t]+([.,;:])", r"\1", body)
    body = re.sub(r"[ \t]{2,}", " ", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    return body.strip()


def is_upper_title(title: str) -> bool:
    return any(c.isalpha() for c in title) and title == title.upper()


def strip_boilerplate(body: str) -> str:
    lines, skip_bullets = [], False
    for line in body.split("\n"):
        line = line.strip()
        if BOILERPLATE_RE.match(line) and line:
            continue
        # "Veja ainda:" é seguido de manchetes que duplicam as matérias do email
        if line.endswith("Veja ainda:"):
            line = line.removesuffix("Veja ainda:").strip()
            skip_bullets = True
        elif skip_bullets and line.startswith("* "):
            continue
        else:
            skip_bullets = False
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def split_paragraphs(body: str) -> list[str]:
    paragraphs = []
    for block in re.split(r"\n{2,}", body):
        items: list[str] = []
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            # junta quebras de linha dentro do parágrafo, mas mantém cada bullet separado
            if items and not line.startswith("* ") and not items[-1].startswith("* "):
                items[-1] += " " + line
            else:
                items.append(line)
        if items:
            paragraphs.append("\n".join(items))
    return paragraphs


def split_sections(text: str, subject: str) -> list[dict]:
    matches = list(HEADING_RE.finditer(text))
    # sem títulos (convites, webinars): o email inteiro vira uma seção
    if not matches:
        return [{"edition": "", "section": "", "title": subject, "body": text}]

    sections, edition, section = [], "", ""
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = match.group(1).strip()
        body = text[match.end():end]
        if i == 0:
            # o primeiro título é o nome da edição; o lead da abertura usa o subject
            edition, title = title, subject
        elif is_upper_title(title) and not split_paragraphs(strip_boilerplate(body)):
            # título em maiúsculas sem corpo agrupa as matérias seguintes
            section = title
            continue
        sections.append(
            {"edition": edition, "section": section, "title": title, "body": body}
        )
    return sections


def heading_path(chunk: dict) -> str:
    parts = []
    for part in (chunk["edition"], chunk["section"], chunk["title"]):
        if part and (not parts or parts[-1] != part):
            parts.append(part)
    return " > ".join(parts)


def pack(units: list[str], limit: int, separator: str) -> list[str]:
    # agrupa unidades em ordem até o limite de caracteres
    chunks, current = [], ""
    for unit in units:
        if current and len(current) + len(separator) + len(unit) > limit:
            chunks.append(current)
            current = ""
        current = current + separator + unit if current else unit
    if current:
        chunks.append(current)
    return chunks


def expand(paragraph: str, limit: int) -> list[str]:
    # parágrafo maior que o limite: quebra por linha (bullets) e depois por sentença
    units = []
    for line in paragraph.split("\n"):
        if len(line) <= limit:
            units.append(line)
        else:
            units.extend(pack(sent_tokenize(line, language="portuguese"), limit, " "))
    return units


def chunk_section(paragraphs: list[str]) -> list[str]:
    limit = int(os.environ["CHUNK_SIZE"])
    units = []
    for paragraph in paragraphs:
        units.extend([paragraph] if len(paragraph) <= limit else expand(paragraph, limit))
    return pack(units, limit, "\n")
