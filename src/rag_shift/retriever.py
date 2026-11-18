import os

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FusionQuery, Fusion, Prefetch

from rag_shift.corpus import mail_key
from rag_shift.embeddings import DENSE, SPARSE, query_document, sparse_document
from rag_shift.filters import has_filter, qdrant_filter, relax_plan
from rag_shift.query_plan import QueryPlan


def retrieve(
    client: QdrantClient,
    query: str,
    query_filter: Filter | None = None,
    top_k: int | None = None,
) -> list[tuple[float, dict]]:
    top_k = top_k or int(os.environ["TOP_K"])
    limit = top_k * 10
    # busca híbrida: vizinhos densos + BM25, fundidos por RRF. O filtro vai dentro de cada
    # prefetch (o filtro externo não vale para eles). O score da fusão é relativo ao 1º.
    hits = client.query_points(
        os.environ["COLLECTION"],
        prefetch=[
            Prefetch(query=query_document(query), using=DENSE, filter=query_filter, limit=limit),
            Prefetch(query=sparse_document(query), using=SPARSE, filter=query_filter, limit=limit),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=limit,
    ).points
    # um resultado por email, mantendo o chunk de maior score
    best: dict[tuple[int, str], tuple[float, dict]] = {}
    for hit in hits:
        key = mail_key(hit.payload)
        if key not in best:
            best[key] = (hit.score, hit.payload)
    return list(best.values())[:top_k]


def retrieve_with_plan(
    client: QdrantClient,
    processed: dict[tuple[int, str], dict],
    plan: QueryPlan,
    question: str,
    top_k: int,
    min_mails: int,
) -> tuple[list[tuple[float, dict]], list[str]]:
    """Busca com os filtros do plano, soltando-os em cascata se sobrarem menos de `min_mails` emails.

    Devolve (resultados, avisos do que foi solto). Se mesmo assim nada voltar, repete sem filtro.
    """
    notes = []
    relaxed, dropped, remaining = relax_plan(processed, plan, min_mails)
    if dropped:
        notes.append(
            f"Poucos emails com os filtros (menos de {min_mails}); soltei {', '.join(dropped)}"
            f" e sobraram {remaining}."
        )
    docs = retrieve(client, question, qdrant_filter(relaxed), top_k)
    if not docs and has_filter(relaxed):
        notes.append("Nenhum resultado com os filtros; repetindo sem filtro.")
        docs = retrieve(client, question, None, top_k)
    return docs, notes
