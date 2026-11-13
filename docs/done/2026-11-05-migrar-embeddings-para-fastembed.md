# Migrar embeddings para FastEmbed + Qdrant persistente

> **Status: implementado na branch `feat/fastembed` (2026-11).** Verificado no projeto: top 5 de 10
> perguntas idêntico ao do sentence-transformers (10 de 10, diferença de score 0,0000); ingestão de
> 18.278 chunks em 13m45s; `.venv` de 5,7 GB para 262 MB; abrir o índice ~2,2 s e a 1ª consulta ~1,6 s
> (a consulta CLI completa, com as duas chamadas ao Groq, leva ~6 s); funciona offline
> (`HF_HUB_OFFLINE=1`) depois do download; `.cache/qdrant` 88 MB e `.cache/fastembed` 465 MB. O texto
> abaixo é o registro da investigação, anterior à implementação. A busca híbrida (BM25 + denso, RRF) veio em seguida, na branch `feat/busca-hibrida`: sobre 10 perguntas de referência o placar aproximado ficou empatado (38 e 37 de 50), "Um tutor digital para cada pessoa" subiu da 79ª para a 8ª posição em "chatgpt na educação" e caiu da 5ª para a 8ª em "…em 2026"; com o filtro `ChatGPT` + tópico educação, 4ª no denso e 2ª no híbrido. O que mais pesa é o filtro por tópico.

## Motivação

Hoje `embeddings.py` carrega `SentenceTransformer` (torch), vetoriza o corpus uma vez e guarda em
`.cache/` (`embeddings.npy` + `chunks.json`); a cada execução o `index.py` recria o Qdrant em memória
(`:memory:`) a partir desse cache e o `retriever.py` vetoriza a pergunta com o mesmo modelo.

O [FastEmbed](https://github.com/qdrant/fastembed) (Qdrant, ONNX) é integrado ao `qdrant-client`
(`qdrant-client[fastembed]`): o cliente recebe `models.Document(text=..., model=...)` na ingestão e
na consulta e calcula o vetor sozinho, sem instanciar um modelo à parte.

## O que foi verificado

- **Versões testadas:** `fastembed` 0.9.1, `qdrant-client` 1.20.0.
- **O `intfloat/multilingual-e5-small` NÃO está no catálogo do FastEmbed.** O único e5 listado é o
  `intfloat/multilingual-e5-large` (1024 dimensões, 2,2 GB). Resultados de busca na web sugeriam o
  contrário (trecho de README e wrappers de terceiros); para essa versão estavam errados.
- **Funciona como modelo customizado**, registrado antes do uso:

  ```python
  from fastembed import TextEmbedding
  from fastembed.common.model_description import ModelSource, PoolingType

  TextEmbedding.add_custom_model(
      model="intfloat/multilingual-e5-small",
      pooling=PoolingType.MEAN,
      normalization=True,
      sources=ModelSource(hf="intfloat/multilingual-e5-small"),
      dim=384,
      model_file="onnx/model.onnx",
  )
  ```

  Os vetores saíram **idênticos** aos do sentence-transformers (cosseno 1,0000, mínimo e média, em
  200 chunks do cache).
- **Prefixos não são automáticos.** O FastEmbed não acrescenta `query: ` nem `passage: `; continuam
  por nossa conta (`passage: {heading_path}\n{texto}` na ingestão, `query: {pergunta}` na consulta).
- **Integração com o Qdrant:** `upload_collection(..., vectors=[models.Document(...)])` e
  `query_points(query=models.Document(...))` funcionaram, tanto em `:memory:` quanto com
  `QdrantClient(path=...)`.
- **Velocidade de vetorização equivalente:** 6,8 s (FastEmbed) contra 7,9 s (sentence-transformers)
  para 200 chunks no mesmo CPU. Uma amostra só; vale como "igual", não como ganho.

## Medições (18.278 chunks)

| | atual (torch + cache npy + Qdrant em memória) | FastEmbed + Qdrant em disco |
|---|---|---|
| ambiente (`.venv`) | 5,7 GB (torch 1,15 GB, libs CUDA da NVIDIA 3 GB, triton 1 GB) | 219 MB (onnxruntime 63 MB) |
| início até a 1ª consulta (3 execuções, sem o Groq) | 17 a 20 s | 2,6 a 2,9 s |
| ingestão única | ~12 min (gera o cache) | 764 s (12,7 min) |
| disco | `.cache/` (não medido) | 84 MB |

Detalhe do início atual: imports 7,5-13 s, carregar o modelo 3,5-4,7 s, ler o cache 0,2-0,4 s, montar
o Qdrant 2-3,5 s, consulta ~1,5 s (o README diz ~10 s; aqui deu quase o dobro). Detalhe do novo:
imports 0,6 s, abrir o Qdrant 0,7 s, carregar o modelo e consultar ~1,4 s. O ambiente isolado novo
inclui `qdrant-client[fastembed]`, nltk, groq e python-dotenv.

Na comparação, o 1º resultado foi o mesmo nos dois fluxos. O top 5 completo **não** foi comparado.

## Por que o Qdrant precisa ser persistente

O `rag-shift "pergunta"` é um processo por pergunta. Com `:memory:`, os dados somem ao final, então
a ingestão com `Document` (que calcula os vetores) se repetiria a cada pergunta (~12 min). Com
`QdrantClient(path=...)`, a ingestão roda uma vez e as execuções seguintes só abrem a pasta e
consultam. Confirmado: a 2ª e a 3ª execução não revetorizaram.

## Ressalvas

- **Um processo por vez:** o modo local trava a pasta
  (`RuntimeError: Storage folder ... is already accessed by another instance of Qdrant client`).
  Duas execuções simultâneas do CLI falhariam. Servidor Qdrant (Docker) não tem esse limite.
- **Fechar o cliente:** sem `client.close()` aparece um `ImportError: sys.meta_path is None` ao
  encerrar o Python (ruído do `__del__`).
- **Cache do FastEmbed:** por padrão fica numa pasta temporária; fixar com a variável
  `FASTEMBED_CACHE_PATH` (ou `cache_dir`).
- **Offline:** o `HF_HUB_OFFLINE=1` com o FastEmbed **não foi testado**.
- **Modelo customizado:** depende da API `add_custom_model` e de o repositório da Hugging Face ter
  `onnx/model.onnx` (tem, em fp32).
- **Não medido:** tamanho do `.cache/` atual, início com o `HF_HUB_OFFLINE=1`, consumo de memória.
- **Só de memória, não testado aqui:** modelos esparsos (BM25/SPLADE) do FastEmbed para busca híbrida
  no Qdrant, que poderiam melhorar a busca por entidade (termo exato) discutida em `2026-11-05-enriquecimento-das-materias.md`.

## Mudanças previstas no código

- `pyproject.toml`: trocar `sentence-transformers` por `qdrant-client[fastembed]` (`uv remove` /
  `uv add`).
- `embeddings.py`: reduz-se a registrar o modelo customizado e montar os textos com prefixo
  (`heading_path` já existe em `preprocessing.py`). Saem `load_model`, `get_embeddings` e o cache
  `embeddings.npy`/`chunks.json`.
- `index.py`: abrir `QdrantClient(path=CACHE_DIR / "qdrant")`; se a coleção não existe
  (`collection_exists`), criar e ingerir com `Document` a partir de `load_corpus()`; `close()` no fim.
- `retriever.py`: `query_points(query=models.Document(text="query: " + pergunta, model=...))`, sem
  `model.encode`. Manter o `limit=top_k * 10` e a deduplicação por `mail_id`.
- `cli.py`: remover `load_model`/`get_embeddings`; avisar na primeira execução que a ingestão leva
  ~12 min.
- Regra de cache: mudou corpus, `CHUNK_SIZE` ou `EMBEDDING_MODEL` → apagar `.cache/qdrant`.
- Atualizar `README.md` e `AGENTS.md` (módulo `embeddings.py`, tempos, regra de cache).

## Verificação ao implementar

1. Comparar o top 5 de ~10 perguntas antes e depois (mesmos `mail_id` e scores muito próximos).
2. Conferir que a 2ª execução não revetoriza e mede ~3 s até a consulta.
3. Testar `HF_HUB_OFFLINE=1`.
4. Conferir que `uv run rag-shift-build` + apagar `.cache/qdrant` reconstrói do zero.
