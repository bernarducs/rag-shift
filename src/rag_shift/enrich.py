import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import rag_shift.config  # noqa: F401  (carrega o .env antes dos demais imports)
from rag_shift.config import PROCESSED_DIR
from rag_shift.corpus import load_mail
from rag_shift.enrichment import build_client, canonicalize, enrich_section

REQUIRED_ENV = ["ENRICH_API_KEY", "ENRICH_BASE_URL", "ENRICH_MODEL"]
# estados que o --retry-failed reprocessa; "empty" só se refaz apagando o enrichment
RETRY_STATUSES = ("failed", "rate_limited")
# 429 seguidos depois dos retries do SDK: provável limite diário, parar sem perder nada
MAX_CONSECUTIVE_RATE_LIMITED = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rag-shift-enrich",
        description=(
            "Extrai metadados (empresas, tecnologias, lugares, pessoas e tópicos) de cada "
            "matéria com um LLM e grava em `enrichment` dos arquivos de "
            "the-shift-mails-processed/. Retomável: pula o que já foi feito."
        ),
        epilog=(
            "Chave, URL e modelo ficam no .env (ENRICH_API_KEY, ENRICH_BASE_URL, ENRICH_MODEL). "
            "Rode `rag-shift-build` antes."
        ),
    )
    parser.add_argument("--limit", type=int, help="processa no máximo N matérias (para testar)")
    parser.add_argument("--workers", type=int, default=8, help="chamadas em paralelo (padrão: 8)")
    parser.add_argument(
        "--retry-failed", action="store_true", help="reprocessa as matérias com status failed/rate_limited"
    )
    parser.add_argument(
        "--normalize-only",
        action="store_true",
        help="só reaplica a normalização (aliases, bloqueio, grafia canônica), sem chamar o LLM",
    )
    return parser.parse_args()


def save(path: Path, mail: dict) -> None:
    # grava em arquivo temporário e troca, para uma interrupção não corromper o JSON
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(mail, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def needs_work(section: dict, retry_failed: bool) -> bool:
    status = section["enrichment"].get("status")
    return not status or (retry_failed and status in RETRY_STATUSES)


def normalize_corpus(mails: dict[Path, dict]) -> int:
    sections = [s for mail in mails.values() for s in mail["sections"]]
    changed = canonicalize(sections)
    if changed:
        for path, mail in mails.items():
            save(path, mail)
    return changed


def summary(mails: dict[Path, dict]) -> str:
    counts: dict[str, int] = {}
    for mail in mails.values():
        for section in mail["sections"]:
            status = section["enrichment"].get("status", "pendente")
            counts[status] = counts.get(status, 0) + 1
    return ", ".join(f"{status}: {n}" for status, n in sorted(counts.items()))


def main() -> None:
    args = parse_args()
    if not PROCESSED_DIR.exists() or not list(PROCESSED_DIR.glob("*.json")):
        sys.exit("Pasta processada vazia. Rode antes: uv run rag-shift-build")

    mails = {path: load_mail(path) for path in sorted(PROCESSED_DIR.glob("*.json"))}

    if args.normalize_only:
        print(f"{normalize_corpus(mails)} matérias ajustadas na normalização.")
        print(summary(mails))
        return

    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        sys.exit(f"Variáveis ausentes no .env: {', '.join(missing)}")

    jobs = [
        (path, index)
        for path, mail in mails.items()
        for index, section in enumerate(mail["sections"])
        if needs_work(section, args.retry_failed)
    ]
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"{len(jobs)} matérias a processar com {args.workers} chamadas em paralelo.")

    client = build_client()
    lock = threading.Lock()
    stop = threading.Event()
    state = {"done": 0, "consecutive_rate_limited": 0}

    def run(path: Path, index: int) -> str:
        if stop.is_set():
            return "cancelled"
        mail = mails[path]
        result = enrich_section(client, mail["sections"][index], mail["date"])
        with lock:
            mail["sections"][index]["enrichment"] = result
            save(path, mail)
            state["done"] += 1
            if result["status"] == "rate_limited":
                state["consecutive_rate_limited"] += 1
                if state["consecutive_rate_limited"] >= MAX_CONSECUTIVE_RATE_LIMITED:
                    stop.set()
            else:
                state["consecutive_rate_limited"] = 0
            if state["done"] % 100 == 0:
                print(f"{state['done']}/{len(jobs)}", flush=True)
        return result["status"]

    executor = ThreadPoolExecutor(max_workers=args.workers)
    try:
        futures = [executor.submit(run, path, index) for path, index in jobs]
        for future in as_completed(futures):
            future.result()
    except KeyboardInterrupt:
        print("\nInterrompido; o que já foi gravado fica salvo. Rode de novo para retomar.")
        stop.set()
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    if stop.is_set() and state["consecutive_rate_limited"] >= MAX_CONSECUTIVE_RATE_LIMITED:
        print("Parado: muitos 429 seguidos (possível limite diário). Rode de novo mais tarde.")

    print(f"{normalize_corpus(mails)} matérias ajustadas na normalização.")
    print(summary(mails))
    print("Falhas: rode com --retry-failed. Matérias com status empty merecem revisão.")
