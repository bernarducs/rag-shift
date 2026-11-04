import os

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

def retrieve(
    client: QdrantClient, model: SentenceTransformer, query: str
) -> list[tuple[float, dict]]:
    top_k = int(os.environ["TOP_K"])
    vector = model.encode("query: " + query, normalize_embeddings=True)
    hits = client.query_points(
        os.environ["COLLECTION"], query=vector.tolist(), limit=top_k * 10
    ).points
    # um resultado por email, mantendo o chunk de maior score
    best: dict[int, tuple[float, dict]] = {}
    for hit in hits:
        mail_id = hit.payload["mail_id"]
        if mail_id not in best:
            best[mail_id] = (hit.score, hit.payload)
    return list(best.values())[:top_k]
