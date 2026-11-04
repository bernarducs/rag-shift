import os

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


def build_index(vectors: np.ndarray, chunks: list[dict]) -> QdrantClient:
    collection = os.environ["COLLECTION"]
    client = QdrantClient(":memory:")
    client.create_collection(
        collection,
        vectors_config=VectorParams(size=int(os.environ["VECTOR_SIZE"]), distance=Distance.COSINE),
    )
    client.upload_points(
        collection,
        [
            PointStruct(id=i, vector=vector.tolist(), payload=chunk)
            for i, (vector, chunk) in enumerate(zip(vectors, chunks))
        ],
        batch_size=1000,
    )
    return client
