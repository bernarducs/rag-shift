# rag-shift

Protótipo de RAG por linha de comando sobre emails da newsletter The Shift.
Recupera os trechos mais próximos da pergunta (Qdrant em memória, similaridade cosseno,
embeddings `intfloat/multilingual-e5-small`) e gera a resposta com um modelo via API do Groq.

## Como rodar

```bash
cp env.template .env          # preencha GROQ_API_KEY e MODEL
# coloque os JSONs dos emails em the-shift-mails-outputs/
uv run rag-shift "o que é machine learning"
```

A saída é a resposta do LLM seguida dos 5 emails mais relevantes (`score - assunto`).

## Primeira execução

- **Demora cerca de 12 min**: o corpus é limpo, dividido em chunks e vetorizado em CPU. O resultado fica em `.cache/`; as próximas execuções levam ~10 s. Apague `.cache/` se mudar o corpus, o chunking ou o modelo.
- **Precisa de internet** para baixar o modelo de embeddings e o tokenizer do NLTK. Deixe `HF_HUB_OFFLINE=0` no `.env` e, depois do download, troque para `1` para rodar offline.
- A chamada ao Groq sempre usa a rede.
