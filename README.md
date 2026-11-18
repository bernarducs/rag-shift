# rag-shift

Protótipo de RAG por linha de comando sobre emails da newsletter The Shift.
Recupera os trechos mais próximos da pergunta com busca híbrida no Qdrant em disco (vetores
`intfloat/multilingual-e5-small` via FastEmbed/ONNX com similaridade cosseno, mais BM25 em português,
fundidos por RRF) e gera a resposta com um modelo via API do Groq.
Também responde a perguntas de filtro e contagem ("quantas matérias de 2022?", "notícias sobre a
Nvidia") a partir de metadados extraídos de cada matéria.

## Requisitos

- Python 3.12 e [uv](https://docs.astral.sh/uv/)
- **Token da API do Groq** (`GROQ_API_KEY`), gerado em [console.groq.com](https://console.groq.com/keys), e o nome de um modelo disponível no Groq em `MODEL`
- Os JSONs dos emails em `the-shift-mails-outputs/`

## Guia de uso

Do zero até a primeira resposta:

```bash
cp env.template .env                  # 1. preencha GROQ_API_KEY e MODEL
uv run rag-shift-build                # 2. gera the-shift-mails-processed/ (~10 s)
uv run rag-shift-enrich               # 3. (opcional) metadados para filtros e contagens; precisa de ENRICH_* no .env
uv run rag-shift "o que é machine learning"   # 4. a 1ª consulta indexa o corpus (~12 a 14 min); as próximas levam alguns segundos
```

- O passo 3 grava o `enrichment` em `the-shift-mails-processed/` e é retomável. Sem ele, o corpus
  funciona só como busca semântica (os filtros e as contagens ficam vazios).
- Mudou o corpus, o chunking, o modelo de embeddings ou o enrichment? Rode `rag-shift-build` de novo
  (se for o caso) e apague `.cache/qdrant` e `.cache/qdrant-ready`; a próxima consulta reindexa.
- Só um `rag-shift` por vez: o Qdrant em disco trava a pasta (uma 2ª execução simultânea avisa e sai).
- A 1ª consulta precisa de internet para baixar o modelo de embeddings (~465 MB, em `.cache/fastembed`) e o tokenizer do NLTK. Deixe
  `HF_HUB_OFFLINE=0` no `.env` e, depois do download, troque para `1` para rodar offline. A chamada
  ao Groq sempre usa a rede.

### Tipos de pergunta

O Groq converte a pergunta em um plano (modo, empresas, tecnologias, lugares, pessoas, anos, tópicos)
e o CLI imprime a interpretação em uma linha (`modo: ... | empresas: ...`) antes da resposta.

| Modo | Quando | O que imprime | Exemplo |
|---|---|---|---|
| `busca` | pergunta que pede explicação | resposta do LLM + os `--limit` documentos mais relevantes | `uv run rag-shift "o que foi dito sobre ChatGPT na educação?"` |
| `lista` | pede notícias ou matérias de algo | matérias filtradas, mais recentes primeiro (sem LLM de resposta, sem embeddings) | `uv run rag-shift "liste as notícias sobre a Nvidia" --limit 10` |
| `contagem` | "quantos", "quais mais aparecem" | totais e ranking, calculados em Python sobre os arquivos processados (~3 s) | `uv run rag-shift "quais empresas mais aparecem em 2024?"` |
| `resumo` | pede o que traz uma matéria pelo título | resumo do texto inteiro da matéria (sem embeddings) | `uv run rag-shift "o que traz a matéria IA Agêntica expõe a gestão?"` |

Regras dos filtros:

- Entre campos vale E, dentro de um campo vale OU. O tópico casa com qualquer tópico da matéria.
- As entidades são casadas com o vocabulário do corpus ("NVIDIA" vira "Nvidia"). As que não existem
  viram só busca semântica, com aviso.
- Na `busca`, um assunto que corresponda a um dos 13 tópicos entra no filtro junto com a entidade
  ("chatgpt na educação" filtra por `ChatGPT` e pelo tópico "sociedade, educação e cultura").
- Se o filtro deixar menos de `--limit` emails, a busca solta os filtros em cascata (primeiro o
  tópico, depois as entidades, por último o ano) até sobrar esse mínimo, e o CLI diz o que soltou.
  O ano filtra pela data do email, não pelo assunto da matéria.
- Se a busca com filtro não achar nada, ela repete sem o filtro. Se a matéria do `resumo` não for
  achada pelo título, cai na busca.
- Na busca, a pergunta original (não uma versão reescrita) é a que vira embedding.

### Saída

Os documentos da busca vêm numerados pela ordem de relevância (o score da fusão híbrida não é uma similaridade, então não é exibido). Cada documento ou matéria mostra a data do email no fuso de Brasília e o caminho
`edição > seção > título`. É a data em que a The Shift publicou, não a dos artigos citados. Abaixo vêm
as **fontes**: os links da matéria, com o título quando o link é um item de lista (na lista de matérias,
só os 3 primeiros e a contagem do resto). Vídeos do YouTube e links de rodapé são ignorados.

```
1. IA Agêntica expõe a gestão
   19/11/2025 - Inteligência Aumentada > IA Agêntica expõe a gestão
   Fontes:
   - The Shift: https://theshift.info/hot/quatro-tensoes-redesenham-a-gestao-na-era-da-ia-agentica/
```

## Referência do CLI

### `rag-shift "pergunta"`

| Opção | O que faz |
|---|---|
| `pergunta` | obrigatória, entre aspas |
| `--limit N` | itens mostrados na busca e na lista (padrão: `TOP_K` do `.env`) |
| `--modo {busca,lista,contagem,resumo}` | força o modo, ignorando o que o LLM entendeu |
| `--sem-filtro` | só a busca semântica: não interpreta a pergunta nem filtra (uma chamada a menos ao Groq). Dá para combinar com `--modo` |
| `-h`, `--help` | ajuda |

### `rag-shift-build`

Lê `the-shift-mails-outputs/`, aplica o chunking estrutural, captura os links e grava
`the-shift-mails-processed/`, preservando o `enrichment` das matérias que não mudaram. Não tem opções
além de `--help`.

### `rag-shift-enrich`

Extrai empresas, tecnologias, lugares, pessoas e tópicos de cada matéria com um LLM e grava em
`enrichment`. Retomável: pula o que já foi feito. Precisa de `ENRICH_API_KEY`, `ENRICH_BASE_URL` e
`ENRICH_MODEL` no `.env` (qualquer API compatível com a da OpenAI; o projeto usa
`openai/gpt-oss-120b` na DeepInfra).

| Opção | O que faz |
|---|---|
| `--limit N` | processa no máximo N matérias (para testar) |
| `--workers N` | chamadas em paralelo (padrão: 8) |
| `--retry-failed` | reprocessa as matérias com status `failed` ou `rate_limited` |
| `--normalize-only` | só reaplica a normalização (limpeza, bloqueio, aliases e grafia canônica), sem chamar o LLM |

Cada matéria recebe um `status` (`ok`, `empty`, `failed`, `rate_limited`). Critérios, tópicos e
aliases estão em `docs/done/2026-11-05-enriquecimento-das-materias.md`. O enrichment vai para o payload dos chunks no Qdrant
(`year`, `companies`, `technologies`, `places`, `people`, `topics`).

### Variáveis do `.env` (veja `env.template`)

| Variável | Para quê |
|---|---|
| `GROQ_API_KEY`, `MODEL` | resposta e interpretação da pergunta (Groq) |
| `COLLECTION`, `EMBEDDING_MODEL`, `VECTOR_SIZE` | coleção do Qdrant e modelo de embeddings (384 dimensões para o e5-small) |
| `TOP_K` | documentos mostrados por padrão (`--limit`) |
| `CHUNK_SIZE` | tamanho máximo do chunk, em caracteres; mudar exige rebuild e apagar o cache |
| `HF_HUB_OFFLINE` | `0` para baixar o modelo, `1` para rodar offline |
| `ENRICH_API_KEY`, `ENRICH_BASE_URL`, `ENRICH_MODEL` | só para o `rag-shift-enrich` |
