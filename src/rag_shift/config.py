from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

# carrega o .env aqui, antes de importar sentence_transformers/huggingface_hub,
# que leem HF_HUB_OFFLINE apenas no momento do import
load_dotenv(ROOT / ".env")
CORPUS_DIR = ROOT / "the-shift-mails-outputs"
CACHE_DIR = ROOT / ".cache"

COLLECTION = "the-shift-mails"
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
VECTOR_SIZE = 384
TOP_K = 5
CHUNK_SIZE = 1000

SYSTEM_PROMPT = (
    "Você responde perguntas usando apenas o contexto fornecido, trechos de emails "
    "da newsletter The Shift. Responda em português. Se o contexto não tiver "
    "a resposta, diga que não encontrou nos documentos."
)
