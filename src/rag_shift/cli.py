import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import rag_shift.config  # noqa: F401  (carrega o .env antes dos demais imports)
from rag_shift.corpus import find_links, load_processed
from rag_shift.filters import count, find_by_title, list_sections
from rag_shift.preprocessing import ensure_tokenizer, heading_path
from rag_shift.query_plan import QueryPlan, build_vocabulary, plan_query, resolve_entities

REQUIRED_ENV = [
    "GROQ_API_KEY",
    "MODEL",
    "COLLECTION",
    "EMBEDDING_MODEL",
    "VECTOR_SIZE",
    "TOP_K",
    "CHUNK_SIZE",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rag-shift",
        description=(
            "Responde perguntas sobre os emails da newsletter The Shift. A pergunta é "
            "interpretada (busca, lista ou contagem, com filtros de empresa, tecnologia, "
            "lugar, pessoa, ano e tópico); a busca recupera os trechos mais relevantes e "
            "gera a resposta com um modelo do Groq, e as contagens saem dos arquivos processados."
        ),
        epilog=(
            "Antes da primeira consulta, rode `rag-shift-build` para gerar a pasta "
            "processada. Parâmetros e chaves ficam no .env (veja env.template)."
        ),
    )
    parser.add_argument("query", help='pergunta entre aspas, ex.: "o que é machine learning"')
    parser.add_argument(
        "--limit", type=int, help="quantidade de matérias/documentos mostrados (padrão: TOP_K)"
    )
    parser.add_argument(
        "--modo",
        choices=["busca", "lista", "contagem", "resumo"],
        help="força o modo, ignorando o que o LLM entendeu",
    )
    parser.add_argument(
        "--sem-filtro",
        action="store_true",
        help="só a busca semântica, sem interpretar a pergunta nem filtrar",
    )
    return parser.parse_args()


def describe(plan: QueryPlan) -> str:
    parts = [f"modo: {plan.mode}"]
    for label, values in (
        ("empresas", plan.companies),
        ("tecnologias", plan.technologies),
        ("lugares", plan.places),
        ("pessoas", plan.people),
        ("anos (data do email)", plan.years),
        ("tópicos", plan.topics),
    ):
        if values:
            parts.append(f"{label}: {', '.join(map(str, values))}")
    if plan.group_by:
        parts.append(f"agrupar por: {plan.group_by}")
    if plan.title:
        parts.append(f"matéria: {plan.title}")
    if plan.query:
        parts.append(f"consulta: {plan.query}")
    return " | ".join(parts)


def brazil_date(iso: str) -> str:
    """Data do email (gravada em UTC) no fuso de Brasília, como dd/mm/aaaa."""
    moment = datetime.fromisoformat(iso).astimezone(ZoneInfo("America/Sao_Paulo"))
    return moment.strftime("%d/%m/%Y")


def print_item(date: str, path: str) -> None:
    # a data é a do email da The Shift que traz a matéria (não a de publicação dos artigos citados)
    print(f"   {brazil_date(date)} - {path}")


def print_sources(links: list[dict], max_links: int | None = None) -> None:
    if links:
        print("   Fontes:")
    for link in links[:max_links]:
        # título só nos itens de lista; o próprio site aparece como "The Shift"
        if link.get("title"):
            print(f"   - {link['title']}")
            print(f"     {link['url']}")
        elif link["domain"] == "theshift.info":
            print(f"   - The Shift: {link['url']}")
        else:
            print(f"   - {link['url']}")
    if max_links is not None and len(links) > max_links:
        print(f"   (+{len(links) - max_links} links)")


def show_count(processed: dict[tuple[int, str], dict], plan: QueryPlan) -> None:
    result = count(processed, plan)
    print(f"{result['sections']} matérias em {result['mails']} emails")
    for value, total in result["groups"] or []:
        print(f"{total:>6}  {value}")


def show_list(processed: dict[tuple[int, str], dict], plan: QueryPlan, limit: int) -> None:
    for mail, section in list_sections(processed, plan, limit):
        print_item(mail["date"], heading_path(section))
        # seções como "Garimpo do dia" têm dezenas de links; a lista mostra só os primeiros
        print_sources(section.get("links", []), max_links=3)


def summarize(processed: dict[tuple[int, str], dict], plan: QueryPlan, question: str) -> bool:
    """Resume a matéria achada pelo título, usando o texto inteiro dela. False se não achar."""
    from rag_shift.generator import generate_answer

    matches = find_by_title(processed, plan.title)
    if not matches:
        print(f"Não achei matéria com o título '{plan.title}'; usando a busca.", file=sys.stderr)
        return False
    # o gerador espera payloads de chunk; aqui o "chunk" é a matéria inteira
    docs = [
        (1.0, {**section, "date": mail["date"], "text": "\n\n".join(section["chunks"])})
        for mail, section in matches
    ]
    print(generate_answer(question, docs))
    print("\n")
    print("matérias usadas:")
    for mail, section in matches:
        print_item(mail["date"], heading_path(section))
        print_sources(section.get("links", []), max_links=3)
    return True


def search(processed: dict[tuple[int, str], dict], plan: QueryPlan, question: str, limit: int) -> None:
    # imports pesados (fastembed) só aqui, para a contagem e a lista não pagarem por eles
    from rag_shift.generator import generate_answer
    from rag_shift.index import open_index
    from rag_shift.retriever import retrieve_with_plan

    # a pergunta original, não a `query` reescrita pelo LLM: reescrever perdia palavras
    semantic = question
    client = open_index()
    try:
        docs, notes = retrieve_with_plan(client, processed, plan, semantic, limit, limit)
        for note in notes:
            print(note, file=sys.stderr)
    finally:
        # libera a pasta do Qdrant (o modo local aceita um processo por vez)
        client.close()

    print(generate_answer(question, docs))
    print("\n")
    print(f"top {limit} documentos relevantes:")
    # a busca híbrida devolve o score da fusão (RRF), que não é cosseno: mostra só a ordem
    for rank, (_, doc) in enumerate(docs, start=1):
        print(f"{rank}. {doc['subject']}")
        print_item(doc["date"], heading_path(doc))
        print_sources(find_links(doc, processed))


def main() -> None:
    args = parse_args()
    question = args.query

    # falha cedo se faltar algo no .env, antes de qualquer processamento pesado
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        sys.exit(f"Variáveis ausentes no .env: {', '.join(missing)}")

    ensure_tokenizer()
    processed = load_processed()
    limit = args.limit or int(os.environ["TOP_K"])

    if args.sem_filtro:
        plan = QueryPlan(mode="busca", query=question)
    else:
        plan = plan_query(question)
        plan, warnings = resolve_entities(plan, build_vocabulary(processed))
        for warning in warnings:
            print(warning, file=sys.stderr)
    if args.modo:
        plan = plan.model_copy(update={"mode": args.modo})
    print(describe(plan), file=sys.stderr)

    if plan.mode == "contagem":
        show_count(processed, plan)
    elif plan.mode == "lista" and not plan.query:
        show_list(processed, plan, limit)
    elif plan.mode == "resumo" and summarize(processed, plan, question):
        pass
    else:
        search(processed, plan, question, limit)
