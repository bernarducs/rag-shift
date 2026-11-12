import os
import sys
from typing import Literal

from groq import Groq
from pydantic import BaseModel, Field, ValidationError

from rag_shift.enrichment import (
    _TOPIC_LIST,
    ALIASES,
    LIST_FIELDS,
    Topic,
    entity_key,
    group_key,
    normalize_values,
)

GroupBy = Literal["companies", "technologies", "places", "people", "topics", "year"]


class QueryPlan(BaseModel):
    mode: Literal["busca", "lista", "contagem", "resumo"] = "busca"
    companies: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)  # type: ignore[valid-type]
    group_by: GroupBy | None = None
    query: str = ""
    title: str = ""  # só no modo resumo: título da matéria citada


PLAN_PROMPT = f"""Você converte a pergunta de um usuário sobre a newsletter The Shift (2022 a 2026) em um plano de consulta JSON.

Campos:
- mode: "busca" (pergunta que pede explicação ou resposta), "lista" (pede notícias/matérias de algo), "contagem" (pede "quantos", "quais mais aparecem", ranking) ou "resumo" (pede resumir ou dizer o que traz uma matéria específica, citada pelo título).
- companies, technologies, places, people: entidades citadas na pergunta, como escritas (empresas e organizações; produtos, modelos e conceitos tecnológicos; países, estados e cidades; pessoas). Só o que está na pergunta.
- years: anos citados (inteiros).
- topics: só se a pergunta tratar claramente de um destes assuntos, com o nome exato:
{_TOPIC_LIST}
- group_by: só em contagem de ranking ("quais empresas mais aparecem" -> companies; "por ano" -> year); senão null.
- title: só em "resumo": o título da matéria como o usuário escreveu; nesse modo deixe as entidades, anos e tópicos vazios.
- query: o que sobrar da pergunta para a busca semântica (o assunto livre), sem as entidades e anos já extraídos; vazio se nada sobrar.

Exemplos:
"quantas matérias sobre cibersegurança em 2022?" -> {{"mode":"contagem","years":[2022],"topics":["cibersegurança e privacidade"],"group_by":null,"query":""}}
"quais empresas mais aparecem em 2024?" -> {{"mode":"contagem","years":[2024],"group_by":"companies","query":""}}
"notícias sobre a Nvidia" -> {{"mode":"lista","companies":["Nvidia"],"query":""}}
"resuma a matéria IA Agêntica expõe a gestão" -> {{"mode":"resumo","title":"IA Agêntica expõe a gestão"}}
"o que foi dito sobre ChatGPT na educação?" -> {{"mode":"busca","technologies":["ChatGPT"],"query":"educação"}}
Responda apenas com o JSON."""


def plan_query(question: str) -> QueryPlan:
    """Interpreta a pergunta com o Groq; na falha, devolve uma busca simples sem filtros."""
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    schema = {"name": "query_plan", "strict": False, "schema": QueryPlan.model_json_schema()}
    formats = [{"type": "json_schema", "json_schema": schema}, {"type": "json_object"}]
    last_error = None
    for response_format in formats:
        try:
            response = client.chat.completions.create(
                model=os.environ["MODEL"],
                messages=[
                    {"role": "system", "content": PLAN_PROMPT},
                    {"role": "user", "content": question},
                ],
                response_format=response_format,
                temperature=0,
            )
            return QueryPlan.model_validate_json(response.choices[0].message.content)
        except (ValidationError, ValueError, TypeError) as error:
            last_error = error
        except Exception as error:  # noqa: BLE001 (rede/API: cai na busca simples)
            last_error = error
            break
    print(f"Não consegui interpretar a pergunta ({type(last_error).__name__}); usando só a busca semântica.", file=sys.stderr)
    return QueryPlan(query=question)


def build_vocabulary(processed: dict[tuple[int, str], dict]) -> dict[str, dict[str, str]]:
    """Campo -> {group_key: grafia canônica}, a partir do enrichment gravado."""
    vocabulary = {field: {} for field in LIST_FIELDS}
    for mail in processed.values():
        for section in mail["sections"]:
            for field in LIST_FIELDS:
                for name in section["enrichment"].get(field, []):
                    vocabulary[field][group_key(name)] = name
    return vocabulary


def resolve_name(name: str, field: str, vocabulary: dict[str, dict[str, str]]) -> tuple[str, str] | None:
    """Acha (campo, grafia canônica) do nome, tentando primeiro o campo indicado, depois os outros."""
    for candidate_field in (field, *(f for f in LIST_FIELDS if f != field)):
        cleaned = normalize_values([name], candidate_field)
        if not cleaned:
            continue
        key = group_key(ALIASES[candidate_field].get(entity_key(cleaned[0]), cleaned[0]))
        if key in vocabulary[candidate_field]:
            return candidate_field, vocabulary[candidate_field][key]
    return None


def resolve_entities(
    plan: QueryPlan, vocabulary: dict[str, dict[str, str]]
) -> tuple[QueryPlan, list[str]]:
    """Troca as entidades pela grafia do corpus; as que não existem vão para a busca semântica.

    Devolve (plano resolvido, avisos).
    """
    resolved = {field: [] for field in LIST_FIELDS}
    unknown, warnings = [], []
    for field in LIST_FIELDS:
        for name in getattr(plan, field):
            found = resolve_name(name, field, vocabulary)
            if found is None:
                unknown.append(name)
                warnings.append(f"'{name}' não está no vocabulário; usada só na busca semântica.")
            elif found[1] not in resolved[found[0]]:
                resolved[found[0]].append(found[1])
    query = " ".join([plan.query, *unknown]).strip()
    return plan.model_copy(update={**resolved, "query": query}), warnings
