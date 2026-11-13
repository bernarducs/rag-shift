import os

from qdrant_client import QdrantClient
from qdrant_client.models import Filter

from rag_shift.corpus import mail_key
from rag_shift.embeddings import query_document


def retrieve(
    client: QdrantClient,
    query: str,
    query_filter: Filter | None = None,
    top_k: int | None = None,
) -> list[tuple[float, dict]]:
    top_k = top_k or int(os.environ["TOP_K"])
    hits = client.query_points(
        os.environ["COLLECTION"],
        query=query_document(query),
        query_filter=query_filter,
        limit=top_k * 10,
    ).points
    # um resultado por email, mantendo o chunk de maior score
    best: dict[tuple[int, str], tuple[float, dict]] = {}
    for hit in hits:
        key = mail_key(hit.payload)
        if key not in best:
            best[key] = (hit.score, hit.payload)
    return list(best.values())[:top_k]
