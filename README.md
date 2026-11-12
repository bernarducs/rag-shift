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

A saída é a resposta do LLM seguida dos 5 emails mais relevantes (`score - assunto`). Cada resultado traz a data do email no fuso de Brasília e o caminho da matéria (`20/04/2024 - edição > seção > título`; é a data em que a The Shift publicou, não a dos artigos citados) e as **fontes**: todos os links da matéria (com o título quando o link é um item de lista). Os links vêm de `rag-shift-build`; vídeos do YouTube e links de rodapé são ignorados.

## Comandos

| Comando | O que faz |
|---|---|
| `uv run rag-shift "pergunta"` | Interpreta a pergunta (busca, lista ou contagem, com filtros) e responde |
| `uv run rag-shift-build` | Aplica o chunking estrutural nos emails brutos e grava `the-shift-mails-processed/` |
| `uv run rag-shift-enrich` | Extrai empresas, tecnologias, lugares, pessoas e tópicos de cada matéria com um LLM e grava em `enrichment` |

Use `--help` em qualquer um dos três para ver as opções.

## Perguntas, filtros e contagens

O Groq converte a pergunta em um plano (modo, empresas, tecnologias, lugares, pessoas, anos, tópicos).
As entidades são casadas com o vocabulário do corpus (ex.: "NVIDIA" vira "Nvidia"); as que não existem
vão para a busca semântica, com aviso. Entre campos vale E, dentro de um campo vale OU.

```bash
uv run rag-shift "quantas matérias sobre cibersegurança em 2022?"   # contagem, só Python, ~3 s
uv run rag-shift "quais empresas mais aparecem em 2024?"            # ranking
uv run rag-shift "liste as notícias sobre a Nvidia" --limit 10      # lista, mais recentes primeiro
uv run rag-shift "o que foi dito sobre ChatGPT na educação?"        # busca semântica com filtro
uv run rag-shift "o que traz a matéria IA Agêntica expõe a gestão?"  # resumo de uma matéria pelo título
```

Opções: `--limit N` (itens mostrados, padrão `TOP_K`), `--modo {busca,lista,contagem,resumo}` (força o modo) e
`--sem-filtro` (só a busca semântica, sem interpretar a pergunta). Se o filtro não achar nada, a busca repete sem ele.

## Enriquecimento

Opcional. O resultado vai para o payload dos chunks no Qdrant (`year`, `companies`, `technologies`,
`places`, `people`, `topics`), usado pelos filtros acima. Precisa de `ENRICH_API_KEY`, `ENRICH_BASE_URL` e `ENRICH_MODEL`
no `.env` (qualquer API compatível com a da OpenAI; o projeto usa `openai/gpt-oss-120b` na DeepInfra).

```bash
uv run rag-shift-enrich --limit 20   # teste com poucas matérias
uv run rag-shift-enrich              # corpus inteiro; retomável (pula o que já está feito)
uv run rag-shift-enrich --retry-failed
```

Cada matéria recebe um `status` (`ok`, `empty`, `failed`, `rate_limited`). Critérios, tópicos e
aliases estão em `to-do/enriquecimento.md`.

## Primeira execução

- **Demora cerca de 12 min**: os chunks processados são vetorizados em CPU. O resultado fica em `.cache/`; as próximas execuções levam ~10 s. Se mudar o corpus, o chunking, o modelo ou o enrichment, rode `rag-shift-build` de novo e apague `.cache/`.
- **Precisa de internet** para baixar o modelo de embeddings e o tokenizer do NLTK. Deixe `HF_HUB_OFFLINE=0` no `.env` e, depois do download, troque para `1` para rodar offline.
- A chamada ao Groq sempre usa a rede.
