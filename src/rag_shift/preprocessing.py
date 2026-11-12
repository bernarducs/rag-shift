import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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


def prepare(body: str) -> str:
    # corta o rodapé da newsletter
    for marker in FOOTER_MARKERS:
        body = body.split(marker)[0]
    # padroniza quebras e caracteres invisíveis, preservando a estrutura de \n
    body = body.replace("\r\n", "\n").replace("\r", "")
    body = body.replace("\xa0", " ")
    return re.sub(r"[​‌‍﻿]", "", body)


def strip_urls(body: str) -> str:
    # remove urls (com ou sem parênteses)
    body = re.sub(r"\(\s*https?://[^\s)]*\s*\)", "", body)
    return re.sub(r"https?://\S+", "", body)


def tidy(body: str) -> str:
    # espaços sobrando, inclusive antes de pontuação deixados pelas urls
    body = re.sub(r"[ \t]+([.,;:])", r"\1", body)
    body = re.sub(r"[ \t]{2,}", " ", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    return body.strip()


def normalize(body: str) -> str:
    return tidy(strip_urls(prepare(body)))


def link_text(body: str) -> str:
    # mesmo texto do normalize, mas com as urls: os títulos caem nas mesmas posições
    return tidy(prepare(body))


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
        return [{"edition": "", "section": "", "title": subject, "body": text, "heading": None}]

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
            {"edition": edition, "section": section, "title": title, "body": body, "heading": i}
        )
    return sections


URL_RE = re.compile(r"\(\s*(https?://[^\s)]*)\s*\)|(https?://[^\s)\]>]+)")
TRACKING_PARAMS = ("utm_", "mc_cid", "mc_eid")
SOCIAL_DOMAINS = ("linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com")
# links do próprio site que levam a uma matéria
OWN_SITE_PATHS = ("hot", "talk")


def clean_url(url: str) -> str:
    # tira só os parâmetros de rastreamento, mantendo o resto da query e o fragmento
    parts = urlsplit(url.rstrip(".,;"))
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.startswith(TRACKING_PARAMS)]
    return urlunsplit(parts._replace(query=urlencode(query)))


def link_domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def keep_link(url: str, line_text: str) -> bool:
    domain, path = link_domain(url), urlsplit(url).path.strip("/")
    if not domain:  # url malformada, ex.: "http://"
        return False
    if domain in ("youtube.com", "youtu.be", "wa.me", "mailchi.mp"):
        return False
    if domain == "api.whatsapp.com" or domain.endswith(("list-manage.com", "mailchimp.com")):
        return False
    if "maillist-manage" in domain:  # redirecionamento de rastreamento
        return False
    if domain == "theshift.info":
        return path.split("/")[0] in OWN_SITE_PATHS
    if domain.endswith(SOCIAL_DOMAINS):
        # ícone de rede social: a linha não tem texto além do nome da rede
        return len(re.sub(r"[^\w]", "", line_text)) > 12
    return True


def extract_links(text: str) -> list[dict]:
    """Links de uma matéria (texto ainda com as urls), sem rodapé nem ruído.

    O título só é guardado para item de lista (`* Título (url)`), onde ele é a
    manchete da fonte; nos links no meio do texto fica só a url.
    """
    links: dict[str, dict] = {}
    for line in strip_boilerplate(text).split("\n"):
        matches = list(URL_RE.finditer(line))
        for n, match in enumerate(matches):
            url = clean_url(match.group(1) or match.group(2))
            before = line[: match.start()]
            plain_line = URL_RE.sub("", line)
            if not keep_link(url, plain_line):
                continue
            title = ""
            tail = line[match.end():].strip(" .,;:!?)")
            if n == 0 and before.startswith("* ") and not tail and not URL_RE.search(tail):
                title = before.removeprefix("* ").strip(" .,;:-–—")[:200]
            entry = links.setdefault(url, {"url": url, "domain": link_domain(url), "title": ""})
            entry["title"] = entry["title"] or title
    return [{k: v for k, v in entry.items() if v} for entry in links.values()]


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
