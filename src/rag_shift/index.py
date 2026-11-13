import os
import sys
import warnings

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from rag_shift.config import CACHE_DIR, QDRANT_DIR, QDRANT_READY
from rag_shift.corpus import load_corpus
from rag_shift.embeddings import passage_document


def ingest(client: QdrantClient, collection: str) -> None:
    chunks = load_corpus()
    print(
        f"Indexando {len(chunks)} chunks (primeira execução, ~12 min; as próximas abrem direto)...",
        file=sys.stderr,
    )
    client.create_collection(
        collection,
        vectors_config=VectorParams(size=int(os.environ["VECTOR_SIZE"]), distance=Distance.COSINE),
    )
    # índices de filtro; no modo local não aceleram nada, mas deixam o esquema pronto
    # para um servidor Qdrant
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Payload indexes have no effect")
        for field in ("companies", "technologies", "places", "people", "topics"):
            client.create_payload_index(collection, field, PayloadSchemaType.KEYWORD)
        client.create_payload_index(collection, "year", PayloadSchemaType.INTEGER)
    # o próprio cliente calcula os vetores a partir dos Documents
    client.upload_collection(
        collection,
        vectors=(passage_document(chunk) for chunk in chunks),
        payload=chunks,
        ids=range(len(chunks)),
        batch_size=64,
    )
    # só depois de terminar: uma ingestão interrompida não é reaproveitada
    QDRANT_READY.write_text(str(len(chunks)), encoding="utf-8")


def open_index() -> QdrantClient:
    """Abre o Qdrant em disco; ingere o corpus se ainda não houver índice completo.

    O modo local trava a pasta: só um processo por vez. Quem chama deve fechar o cliente.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    collection = os.environ["COLLECTION"]
    try:
        client = QdrantClient(path=str(QDRANT_DIR))
    except RuntimeError as error:
        if "already accessed" not in str(error):
            raise
        sys.exit("O índice está em uso por outra execução do rag-shift. Espere ela terminar e tente de novo.")
    ready = QDRANT_READY.exists() and client.collection_exists(collection)
    if ready and client.count(collection).count != int(QDRANT_READY.read_text()):
        ready = False
    if not ready:
        # índice ausente ou incompleto: recomeça do zero
        if client.collection_exists(collection):
            client.delete_collection(collection)
        QDRANT_READY.unlink(missing_ok=True)
        ingest(client, collection)
    return client
