import os
import re
import unicodedata
from collections import Counter
from typing import Literal

from openai import OpenAI, RateLimitError
from pydantic import BaseModel, Field, ValidationError

from rag_shift.preprocessing import heading_path

# tópico -> escopo (o escopo vai no prompt; a lista é fechada)
TOPICS = {
    "inteligência artificial e dados": "IA, IA generativa, LLMs, agentes, data science, analytics",
    "cibersegurança e privacidade": "ataques, segurança da informação, proteção de dados, LGPD",
    "finanças digitais e cripto": "open finance, bancos digitais, fintechs, meios de pagamento, Pix, cripto, DeFi, web3",
    "startups e investimentos": "empreendedorismo, venture capital, CVC, rodadas, fusões e aquisições",
    "estratégia e negócios digitais": "estratégia corporativa, transformação digital, inovação nas empresas, disputa entre big techs, resultados",
    "trabalho, pessoas e liderança": "RH, carreira, cultura organizacional, gestão, liderança, diversidade, futuro do trabalho",
    "consumo, marketing e varejo": "comportamento do consumidor, CX, publicidade, e-commerce, varejo",
    "deep tech e infraestrutura": "semicondutores, cloud, data centers, telecom/5G, computação quântica, robótica, espaço",
    "saúde e biotecnologia": "healthtech, ciências da vida, biotecnologia",
    "energia, clima e sustentabilidade": "transição energética, ESG, clima, COP",
    "mobilidade e cidades": "veículos elétricos e autônomos, transporte, smart cities",
    "regulação, governo e geopolítica": "leis, regulação de IA e de plataformas, antitruste, políticas públicas, disputa EUA-China",
    "sociedade, educação e cultura": "impactos sociais, educação, mídia, entretenimento, desinformação, bem-estar",
}
Topic = Literal[tuple(TOPICS)]  # type: ignore[valid-type]

LIST_FIELDS = ("companies", "technologies", "places", "people")


class Enrichment(BaseModel):
    companies: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)  # type: ignore[valid-type]


_TOPIC_LIST = "\n".join(f"- {name}: {scope}" for name, scope in TOPICS.items())
SYSTEM_PROMPT = f"""Você extrai metadados de uma matéria da newsletter The Shift, em português.

Campos:
- companies: empresas e organizações, inclusive órgãos públicos e reguladores (ANAC, Bacen), universidades e ONGs. Nome curto oficial, sem sufixos como Inc, Corp, Corporation, S.A. (ex.: "Nvidia", "Google"). Não inclua "The Shift", a própria newsletter.
- technologies: produtos, modelos, plataformas, subáreas e conceitos tecnológicos específicos (ex.: "ChatGPT", "Pix", "IA generativa", "visão computacional", "computação quântica", "tokenização", "embedded finance"). NUNCA inclua os termos genéricos "IA", "AI", "inteligência artificial", "tecnologia", "app", "API", "dados", "nuvem" quando aparecem sozinhos; use a subárea específica ("IA generativa", "agentes de IA") ou omita.
- places: países, estados, cidades e blocos (ex.: "Brasil", "EUA", "São Paulo", "União Europeia").
- people: pessoas citadas pelo nome.
- topics: de 1 a 3, exclusivamente da lista abaixo; o primeiro é o principal.

Lista de tópicos (tópico: o que cobre):
{_TOPIC_LIST}

Regras para os tópicos:
- Classifique pelo assunto da matéria, não pelo setor das empresas citadas.
- Use "inteligência artificial e dados" só se a IA for o assunto central. Se a matéria trata de outro tema usando IA, o tópico é o do tema (ex.: IA no RH -> "trabalho, pessoas e liderança"). IA e trabalho -> "trabalho, pessoas e liderança", com "inteligência artificial e dados" como secundário.
- Veículo elétrico -> "mobilidade e cidades", não "energia, clima e sustentabilidade".
- Regulação de um setor -> "regulação, governo e geopolítica", com o setor como secundário.

Inclua só o que está no texto; não invente. Se não houver, devolva lista vazia."""

# --- normalização determinística ---

# termos genéricos (por chave) que não valem como tecnologia, e entidades fora de escopo
BLOCKLIST = {
    "technologies": {
        "ia", "ai", "inteligencia artificial", "tecnologia", "app", "api",
        "dados", "nuvem", "data", "cloud",
    },
    "companies": {"the shift"},
}

# só grafia e renomeação; subsidiárias (WhatsApp, Instagram, YouTube) ficam separadas
ALIASES = {
    "companies": {
        "alphabet": "Google",
        "facebook": "Meta",
        "twitter": "X",
        "open ai": "OpenAI",
        "amazon web services": "AWS",
    },
    "technologies": {
        "genai": "IA generativa",
        "gen ai": "IA generativa",
    },
    "places": {
        "eua": "Estados Unidos",
        "ee.uu.": "Estados Unidos",
        "us": "Estados Unidos",
        "usa": "Estados Unidos",
    },
    "people": {},
}

_SUFFIX = re.compile(
    r"[\s,]+(inc|corp|corporation|ltd|ltda|s\.?\s?a|llc|gmbh|plc|co|company)\.?$",
    re.IGNORECASE,
)
_EDGE = " \t\n.,;:!?\"'“”‘’()[]"


def entity_key(name: str) -> str:
    """Chave de comparação: sem acento, minúsculas, espaços colapsados."""
    decomposed = unicodedata.normalize("NFD", name)
    plain = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", plain).strip().lower()


def clean_name(name: str, field: str) -> str:
    name = name.strip(_EDGE)
    if field == "companies":
        # remove sufixos societários repetidos ("Foo Co., Ltd.")
        while True:
            stripped = _SUFFIX.sub("", name).strip(_EDGE)
            if stripped == name or not stripped:
                break
            name = stripped
    return name


def normalize_values(values: list[str], field: str) -> list[str]:
    """Limpa, aplica bloqueio e aliases e remove duplicatas, mantendo a ordem."""
    seen, result = set(), []
    for raw in values:
        name = clean_name(raw, field)
        key = entity_key(name)
        if not key or key in BLOCKLIST.get(field, set()):
            continue
        name = ALIASES[field].get(key, name)
        key = entity_key(name)
        if key not in seen:
            seen.add(key)
            result.append(name)
    return result


def canonicalize(sections: list[dict]) -> int:
    """Uma grafia por entidade no corpus: a mais frequente por chave (aliases têm prioridade).

    Altera as seções no lugar e devolve quantas mudaram.
    """
    counts = {field: {} for field in LIST_FIELDS}
    for section in sections:
        enrichment = section["enrichment"]
        if enrichment.get("status") not in ("ok", "empty"):
            continue
        for field in LIST_FIELDS:
            for name in enrichment.get(field, []):
                counts[field].setdefault(entity_key(name), Counter())[name] += 1

    # empate: a grafia que ordena primeiro, para o resultado ser determinístico
    canonical = {
        field: {
            key: sorted(spellings.items(), key=lambda item: (-item[1], item[0]))[0][0]
            for key, spellings in by_key.items()
        }
        for field, by_key in counts.items()
    }
    changed = 0
    for section in sections:
        enrichment = section["enrichment"]
        if enrichment.get("status") not in ("ok", "empty"):
            continue
        touched = False
        for field in LIST_FIELDS:
            new = []
            for name in enrichment.get(field, []):
                name = ALIASES[field].get(entity_key(name), canonical[field][entity_key(name)])
                if name not in new:
                    new.append(name)
            if new != enrichment.get(field, []):
                enrichment[field] = new
                touched = True
        changed += touched
    return changed


# --- extração ---

def build_client() -> OpenAI:
    # max_retries: o SDK repete 429/5xx com espera crescente antes de desistir
    return OpenAI(
        api_key=os.environ["ENRICH_API_KEY"],
        base_url=os.environ["ENRICH_BASE_URL"],
        max_retries=5,
    )


def section_text(section: dict) -> str:
    return heading_path(section) + "\n\n" + "\n\n".join(section["chunks"])


def extract(client: OpenAI, section: dict) -> tuple[Enrichment, int]:
    """Extrai os metadados de uma matéria. Devolve (resultado, tentativas)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": section_text(section)},
    ]
    schema = {
        "name": "enrichment",
        "strict": True,
        "schema": Enrichment.model_json_schema(),
    }
    formats = [{"type": "json_schema", "json_schema": schema}, {"type": "json_object"}]
    last_error = None
    for attempt, response_format in enumerate(formats, start=1):
        response = client.chat.completions.create(
            model=os.environ["ENRICH_MODEL"],
            messages=messages,
            response_format=response_format,
            temperature=0,
            extra_body={"reasoning_effort": "low"},
        )
        try:
            return Enrichment.model_validate_json(response.choices[0].message.content), attempt
        except (ValidationError, ValueError, TypeError) as error:
            last_error = error
    raise ValueError(f"resposta inválida: {str(last_error)[:200]}")


def enrich_section(client: OpenAI, section: dict, date: str) -> dict:
    """Gera o dict gravado em `enrichment`, com status; nunca lança exceção da API."""
    try:
        result, attempts = extract(client, section)
    except RateLimitError as error:
        return {"status": "rate_limited", "error": str(error)[:200], "attempts": 1}
    except Exception as error:  # noqa: BLE001 (registrar em vez de descartar em silêncio)
        return {"status": "failed", "error": f"{type(error).__name__}: {str(error)[:200]}", "attempts": 1}

    data = result.model_dump()
    for field in LIST_FIELDS:
        data[field] = normalize_values(data[field], field)
    has_content = any(data[field] for field in (*LIST_FIELDS, "topics"))
    return {
        "status": "ok" if has_content else "empty",
        "year": int(date[:4]),
        **data,
        "attempts": attempts,
    }
