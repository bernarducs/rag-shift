import argparse
import os
import sys

import rag_shift.config  # noqa: F401  (carrega o .env antes dos demais imports)
from rag_shift.corpus import find_links, load_processed
from rag_shift.embeddings import get_embeddings, load_model
from rag_shift.generator import generate_answer
from rag_shift.index import build_index
from rag_shift.preprocessing import ensure_tokenizer
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rag-shift",
        description=(
            "Responde perguntas sobre os emails da newsletter The Shift: recupera os "
            "trechos mais relevantes e gera a resposta com um modelo do Groq."
        ),
        epilog=(
            "Antes da primeira consulta, rode `rag-shift-build` para gerar a pasta "
            "processada. Parâmetros e chaves ficam no .env (veja env.template)."
        ),
    )
    parser.add_argument("query", help='pergunta entre aspas, ex.: "o que é machine learning"')
    return parser.parse_args()


def main() -> None:
    query = parse_args().query

    # falha cedo se faltar algo no .env, antes de qualquer processamento pesado
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        sys.exit(f"Variáveis ausentes no .env: {', '.join(missing)}")

    ensure_tokenizer()
    model = load_model()
    vectors, chunks = get_embeddings(model)
    client = build_index(vectors, chunks)
    docs = retrieve(client, model, query)

    print(generate_answer(query, docs))
    print("\n")
    print("top 5 documentos relevantes:")
    processed = load_processed()
    for score, doc in docs:
        print(f"{score:.3f}".replace(".", ",") + f" - {doc['subject']}")
        links = find_links(doc, processed)
        if links:
            print("   Fontes:")
        for link in links:
            # título só nos itens de lista; o próprio site aparece como "The Shift"
            if link.get("title"):
                print(f"   - {link['title']}")
                print(f"     {link['url']}")
            elif link["domain"] == "theshift.info":
                print(f"   - The Shift: {link['url']}")
            else:
                print(f"   - {link['url']}")
