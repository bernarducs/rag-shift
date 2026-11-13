import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

# carrega o .env aqui, antes de importar fastembed/huggingface_hub,
# que leem HF_HUB_OFFLINE apenas no momento do import
load_dotenv(ROOT / ".env")
CORPUS_DIR = ROOT / "the-shift-mails-outputs"
PROCESSED_DIR = ROOT / "the-shift-mails-processed"
CACHE_DIR = ROOT / ".cache"
# Qdrant em disco (ingestão feita uma vez) e marcador de ingestão completa
QDRANT_DIR = CACHE_DIR / "qdrant"
QDRANT_READY = CACHE_DIR / "qdrant-ready"
# o FastEmbed guardaria o modelo numa pasta temporária; fixa dentro do .cache/
os.environ.setdefault("FASTEMBED_CACHE_PATH", str(CACHE_DIR / "fastembed"))

SYSTEM_PROMPT = (
    "Você responde perguntas usando apenas o contexto fornecido, trechos de emails "
    "da newsletter The Shift. Responda em português. Se o contexto não tiver "
    "a resposta, diga que não encontrou nos documentos."
)
