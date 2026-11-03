from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from rag_shift.config import COLLECTION, TOP_K


def retrieve(
    client: QdrantClient, model: SentenceTransformer, query: str
) -> list[tuple[float, dict]]:
    vector = model.encode("query: " + query, normalize_embeddings=True)
    hits = client.query_points(COLLECTION, query=vector.tolist(), limit=TOP_K * 10).points
    # um resultado por email, mantendo o chunk de maior score
    best: dict[int, tuple[float, dict]] = {}
    for hit in hits:
        mail_id = hit.payload["mail_id"]
        if mail_id not in best:
            best[mail_id] = (hit.score, hit.payload)
    return list(best.values())[:TOP_K]
