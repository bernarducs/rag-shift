import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from rag_shift.config import COLLECTION, VECTOR_SIZE


def build_index(vectors: np.ndarray, chunks: list[dict]) -> QdrantClient:
    client = QdrantClient(":memory:")
    client.create_collection(
        COLLECTION,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    client.upload_points(
        COLLECTION,
        [
            PointStruct(id=i, vector=vector.tolist(), payload=chunk)
            for i, (vector, chunk) in enumerate(zip(vectors, chunks))
        ],
        batch_size=1000,
    )
    return client
