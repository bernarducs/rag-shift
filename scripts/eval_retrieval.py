"""Avalia a busca: em que posição aparece o email com a matéria esperada de cada pergunta.

Uso:
    uv run python scripts/eval_retrieval.py [--sem-plano] [--depth N] [--detalhes]

Cada pergunta de `scripts/eval_questions.json` tem uma lista de emails esperados (`mail_id` + data,
mais o título da matéria para leitura); vale o primeiro que aparecer. A avaliação roda a busca de
duas formas e mede a posição desse email entre os emails devolvidos:

- `sem filtro`: só a busca híbrida, com a pergunta original (igual a `rag-shift --sem-filtro`);
- `com plano`: o plano do LLM (Groq) vira filtro, como no `rag-shift` normal, com a mesma volta
  para a busca sem filtro quando o filtro não devolve nada. Depende do Groq e pode variar entre
  execuções; `--sem-plano` pula esta parte.

Não gera resposta (não chama o `generate_answer`), então só o plano usa o LLM.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import rag_shift.config  # noqa: F401  (carrega o .env antes dos demais imports)
from rag_shift.corpus import load_processed
from rag_shift.filters import conditions
from rag_shift.index import open_index
from rag_shift.preprocessing import ensure_tokenizer
from rag_shift.query_plan import QueryPlan, build_vocabulary, plan_query, resolve_entities
from rag_shift.retriever import retrieve, retrieve_with_plan

QUESTIONS = Path(__file__).parent / "eval_questions.json"
REQUIRED_ENV = ["COLLECTION", "EMBEDDING_MODEL", "VECTOR_SIZE", "TOP_K", "CHUNK_SIZE"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Avalia a posição do email esperado na busca.")
    parser.add_argument(
        "--sem-plano", action="store_true", help="não chama o LLM: avalia só a busca sem filtro"
    )
    parser.add_argument(
        "--depth", type=int, default=30, help="quantos emails olhar por pergunta (padrão: 30)"
    )
    parser.add_argument(
        "--detalhes", action="store_true", help="mostra o plano e os 5 primeiros de cada busca"
    )
    return parser.parse_args()


def position(docs: list[tuple[float, dict]], expected: list[dict]) -> int | None:
    """Posição (a partir de 1) do primeiro email esperado nos `docs`; None se nenhum aparece.

    A busca devolve um resultado por email, então o gabarito são emails (`mail_id` + data, já que
    o `mail_id` sozinho se repete); o título da matéria só ajuda a leitura. Uma pergunta pode ter
    mais de um email esperado, e vale o que aparecer primeiro.
    """
    keys = {(item["mail_id"], item["date"]) for item in expected}
    for rank, (_, doc) in enumerate(docs, start=1):
        if (doc["mail_id"], doc["date"][:10]) in keys:
            return rank
    return None


def search_with_plan(client, processed, vocabulary, question: str, depth: int):
    """Mesmo caminho do `rag-shift`: plano -> filtro -> relaxamento -> volta sem filtro."""
    plan = plan_query(question)
    plan, _ = resolve_entities(plan, vocabulary)
    # o relaxamento usa o TOP_K do CLI (não a profundidade da avaliação) como mínimo de emails
    docs, notes = retrieve_with_plan(
        client, processed, plan, question, depth, int(os.environ["TOP_K"])
    )
    return plan, docs, notes


def label_found(plan: QueryPlan, label: dict) -> bool:
    """O plano trouxe o rótulo esperado (tecnologia, empresa ou tópico) da matéria?"""
    return label["value"] in conditions(plan).get(label["field"], [])


def fmt(rank: int | None) -> str:
    return "-" if rank is None else str(rank)


def summarize(name: str, ranks: list[int | None]) -> None:
    total = len(ranks)
    hit1 = sum(1 for r in ranks if r == 1)
    hit5 = sum(1 for r in ranks if r is not None and r <= 5)
    mrr = sum(1 / r for r in ranks if r) / total
    print(f"{name:<12} hit@1 {hit1}/{total}   hit@5 {hit5}/{total}   MRR {mrr:.3f}")


def main() -> None:
    args = parse_args()
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if not args.sem_plano and not os.environ.get("GROQ_API_KEY"):
        missing.append("GROQ_API_KEY")
    if missing:
        sys.exit(f"Variáveis ausentes no .env: {', '.join(missing)}")

    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    ensure_tokenizer()
    processed = load_processed()
    vocabulary = build_vocabulary(processed)

    plain: list[int | None] = []
    planned: list[int | None] = []
    labels: list[bool] = []
    client = open_index()
    try:
        print(f"{'#':>2}  {'sem filtro':>10}  {'com plano':>9}  {'rótulo':>6}  pergunta")
        for number, item in enumerate(questions, start=1):
            question, expected = item["question"], item["expected"]

            docs = retrieve(client, question, None, args.depth)
            plain_rank = position(docs, expected)
            plain.append(plain_rank)

            plan_rank, label_ok, plan = None, None, None
            if not args.sem_plano:
                plan, planned_docs, notes = search_with_plan(
                    client, processed, vocabulary, question, args.depth
                )
                plan_rank = position(planned_docs, expected)
                label_ok = label_found(plan, item["label"])
                planned.append(plan_rank)
                labels.append(label_ok)

            label_text = "-" if label_ok is None else ("sim" if label_ok else "não")
            print(f"{number:>2}  {fmt(plain_rank):>10}  {fmt(plan_rank):>9}  {label_text:>6}  {question}")

            if args.detalhes:
                for target in expected:
                    print(f"      esperado: {target['date']} - {target['title']}")
                if plan is not None:
                    print(f"      plano: {conditions(plan) or 'sem filtro'} (rótulo: {item['label']['value']})")
                    for note in notes:
                        print(f"      {note}")
                for rank, (_, doc) in enumerate(docs[:5], start=1):
                    print(f"      {rank}. {doc['date'][:10]} - {doc['title']}")
    finally:
        # libera a pasta do Qdrant (o modo local aceita um processo por vez)
        client.close()

    print(f"\n('-' = fora dos {args.depth} primeiros emails)")
    summarize("sem filtro", plain)
    if planned:
        summarize("com plano", planned)
        print(f"rótulo esperado no plano: {sum(labels)}/{len(labels)}")


if __name__ == "__main__":
    main()
