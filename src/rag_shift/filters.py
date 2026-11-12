from collections import Counter

from qdrant_client.models import FieldCondition, Filter, MatchAny

from rag_shift.corpus import mail_key
from rag_shift.enrichment import group_key
from rag_shift.query_plan import QueryPlan

ENTITY_FIELDS = ("companies", "technologies", "places", "people")


def conditions(plan: QueryPlan) -> dict[str, list]:
    """Campo -> valores aceitos. Dentro de um campo vale OU; entre campos vale E."""
    result = {field: getattr(plan, field) for field in (*ENTITY_FIELDS, "topics")}
    result["year"] = plan.years
    return {field: values for field, values in result.items() if values}


def has_filter(plan: QueryPlan) -> bool:
    return bool(conditions(plan))


def qdrant_filter(plan: QueryPlan) -> Filter | None:
    must = [
        FieldCondition(key=field, match=MatchAny(any=values))
        for field, values in conditions(plan).items()
    ]
    return Filter(must=must) if must else None


def section_values(mail: dict, section: dict, field: str) -> list:
    if field == "year":
        return [int(mail["date"][:4])]
    return section["enrichment"].get(field, [])


def section_matches(mail: dict, section: dict, plan: QueryPlan) -> bool:
    """Mesmo critério do filtro do Qdrant, aplicado aos arquivos processados."""
    return all(
        any(value in accepted for value in section_values(mail, section, field))
        for field, accepted in conditions(plan).items()
    )


def matching_sections(processed: dict[tuple[int, str], dict], plan: QueryPlan) -> list[tuple[dict, dict]]:
    return [
        (mail, section)
        for mail in processed.values()
        for section in mail["sections"]
        if section_matches(mail, section, plan)
    ]


def count(processed: dict[tuple[int, str], dict], plan: QueryPlan, top: int = 20) -> dict:
    """Contagem em Python sobre os processados: matérias, emails e ranking por `group_by`."""
    matches = matching_sections(processed, plan)
    groups = None
    if plan.group_by:
        groups = Counter(
            value
            for mail, section in matches
            for value in section_values(mail, section, plan.group_by)
        ).most_common(top)
    return {
        "sections": len(matches),
        "mails": len({mail_key(mail) for mail, _ in matches}),
        "groups": groups,
    }


def list_sections(processed: dict[tuple[int, str], dict], plan: QueryPlan, limit: int) -> list[tuple[dict, dict]]:
    """Matérias filtradas, das mais recentes para as mais antigas."""
    matches = matching_sections(processed, plan)
    return sorted(matches, key=lambda pair: pair[0]["date"], reverse=True)[:limit]


def find_by_title(processed: dict[tuple[int, str], dict], title: str, limit: int = 3) -> list[tuple[dict, dict]]:
    """Matérias cujo título casa com `title`, ignorando acento, caixa e pontuação.

    Título igual tem prioridade; sem ele, vale um título que contenha o texto (ou o contrário,
    para títulos de 12+ caracteres). Mais recentes primeiro.
    """
    key = group_key(title)
    if not key:
        return []
    exact, partial = [], []
    for mail in processed.values():
        for section in mail["sections"]:
            section_key = group_key(section["title"])
            if section_key == key:
                exact.append((mail, section))
            elif section_key and (key in section_key or (len(section_key) >= 12 and section_key in key)):
                partial.append((mail, section))
    pool = exact or partial
    return sorted(pool, key=lambda pair: pair[0]["date"], reverse=True)[:limit]
