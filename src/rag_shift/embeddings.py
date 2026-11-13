import os

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType
from qdrant_client.models import Document

from rag_shift.preprocessing import heading_path

_registered = False


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


# o e5 pede os prefixos "passage: " e "query: "; o FastEmbed não os acrescenta
def passage_document(chunk: dict) -> Document:
    return Document(text=f"passage: {heading_path(chunk)}\n{chunk['text']}", model=model_name())


def query_document(query: str) -> Document:
    return Document(text=f"query: {query}", model=model_name())
