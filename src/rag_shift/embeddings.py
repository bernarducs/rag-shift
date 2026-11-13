import os

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType
from qdrant_client.models import Document

from rag_shift.preprocessing import heading_path

_registered = False
SPARSE_MODEL = "Qdrant/bm25"
DENSE, SPARSE = "dense", "bm25"  # nomes dos vetores na coleção


def model_name() -> str:
    """Registra o modelo no FastEmbed (uma vez) e devolve o nome.

    O multilingual-e5-small não está no catálogo do FastEmbed, então entra como modelo
    customizado (ONNX do repositório da Hugging Face, pooling por média, vetor normalizado).
    """
    global _registered
    name = os.environ["EMBEDDING_MODEL"]
    if not _registered:
        TextEmbedding.add_custom_model(
            model=name,
            pooling=PoolingType.MEAN,
            normalization=True,
            sources=ModelSource(hf=name),
            dim=int(os.environ["VECTOR_SIZE"]),
            model_file="onnx/model.onnx",
        )
        _registered = True
    return name


def chunk_text(chunk: dict) -> str:
    return f"{heading_path(chunk)}\n{chunk['text']}"


# o e5 pede os prefixos "passage: " e "query: "; o FastEmbed não os acrescenta
def passage_document(chunk: dict) -> Document:
    return Document(text=f"passage: {chunk_text(chunk)}", model=model_name())


def query_document(query: str) -> Document:
    return Document(text=f"query: {query}", model=model_name())


# BM25 (busca lexical) com stemmer e stopwords em português; o título entra no texto
def sparse_document(text: str) -> Document:
    return Document(text=text, model=SPARSE_MODEL, options={"language": "portuguese"})
