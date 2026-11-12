import os
import warnings

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams


def build_index(vectors: np.ndarray, chunks: list[dict]) -> QdrantClient:
    collection = os.environ["COLLECTION"]
    client = QdrantClient(":memory:")
    client.create_collection(
        collection,
        vectors_config=VectorParams(size=int(os.environ["VECTOR_SIZE"]), distance=Distance.COSINE),
    )
    # índices de filtro; em :memory: não aceleram nada (o modo local ignora), mas deixam
    # o esquema pronto para o Qdrant em disco ou servidor
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Payload indexes have no effect")
        for field in ("companies", "technologies", "places", "people", "topics"):
            client.create_payload_index(collection, field, PayloadSchemaType.KEYWORD)
        client.create_payload_index(collection, "year", PayloadSchemaType.INTEGER)
    client.upload_points(
        collection,
        [
            PointStruct(id=i, vector=vector.tolist(), payload=chunk)
            for i, (vector, chunk) in enumerate(zip(vectors, chunks))
        ],
        batch_size=1000,
    )
    return client
