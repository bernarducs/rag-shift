import os
import sys

import nltk

import rag_shift.config  # noqa: F401  (carrega o .env antes dos demais imports)
from rag_shift.embeddings import get_embeddings, load_model
from rag_shift.generator import generate_answer
from rag_shift.index import build_index
from rag_shift.retriever import retrieve

REQUIRED_ENV = [
    "GROQ_API_KEY",
    "MODEL",
    "COLLECTION",
    "EMBEDDING_MODEL",
    "VECTOR_SIZE",
    "TOP_K",
    "CHUNK_SIZE",
]


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('Uso: uv run rag-shift "sua pergunta"')
    query = sys.argv[1]

    # falha cedo se faltar algo no .env, antes de qualquer processamento pesado
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        sys.exit(f"Variáveis ausentes no .env: {', '.join(missing)}")

    # baixa o tokenizer apenas se ainda não existir localmente
    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab", quiet=True)
    model = load_model()
    vectors, chunks = get_embeddings(model)
    client = build_index(vectors, chunks)
    docs = retrieve(client, model, query)

    print(generate_answer(query, docs))
    print("\n")
    print("top 5 documentos relevantes:")
    for score, doc in docs:
        print(f"{score:.3f}".replace(".", ",") + f" - {doc['subject']}")
