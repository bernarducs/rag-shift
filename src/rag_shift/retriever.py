import os

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FusionQuery, Fusion, Prefetch

from rag_shift.corpus import mail_key
from rag_shift.embeddings import DENSE, SPARSE, query_document, sparse_document


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
