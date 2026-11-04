# rag-shift

Protótipo de RAG por linha de comando sobre emails da newsletter The Shift.
Recupera os trechos mais próximos da pergunta (Qdrant em memória, similaridade cosseno,
embeddings `intfloat/multilingual-e5-small`) e gera a resposta com um modelo via API do Groq.

## Requisitos

- Python 3.12 e [uv](https://docs.astral.sh/uv/)
- **Token da API do Groq** (`GROQ_API_KEY`), gerado em [console.groq.com](https://console.groq.com/keys), e o nome de um modelo disponível no Groq em `MODEL`
- Os JSONs dos emails em `the-shift-mails-outputs/`

## Como rodar

```bash
cp env.template .env          # preencha GROQ_API_KEY e MODEL
uv run rag-shift-build        # gera the-shift-mails-processed/ (~10 s)
uv run rag-shift "o que é machine learning"
```

A saída é a resposta do LLM seguida dos 5 emails mais relevantes (`score - assunto`).

## Comandos

| Comando | O que faz |
|---|---|
| `uv run rag-shift "pergunta"` | Busca os trechos relevantes e responde com o Groq |
| `uv run rag-shift-build` | Aplica o chunking estrutural nos emails brutos e grava `the-shift-mails-processed/` |

Use `--help` em qualquer um dos dois para ver as opções.

## Primeira execução

- **Demora cerca de 12 min**: os chunks processados são vetorizados em CPU. O resultado fica em `.cache/`; as próximas execuções levam ~10 s. Se mudar o corpus, o chunking ou o modelo, rode `rag-shift-build` de novo e apague `.cache/`.
- **Precisa de internet** para baixar o modelo de embeddings e o tokenizer do NLTK. Deixe `HF_HUB_OFFLINE=0` no `.env` e, depois do download, troque para `1` para rodar offline.
- A chamada ao Groq sempre usa a rede.
