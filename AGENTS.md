# AGENTS.md

Protótipo de RAG (CLI) sobre emails da The Shift. Python 3.12, gerenciado com `uv`.

## Comandos
- Gerar a pasta processada (antes da 1ª consulta e quando o chunking mudar): `uv run rag-shift-build`
- Rodar: `uv run rag-shift "pergunta"`
- Enriquecer as matérias com LLM (retomável; precisa de `ENRICH_*` no `.env`): `uv run rag-shift-enrich` (`--limit N` para testar, `--retry-failed`, `--normalize-only`)
- Ajuda dos comandos: `uv run rag-shift --help` e `uv run rag-shift-build --help` (argparse)
- Adicionar dependência: `uv add <pacote>`

## Estrutura (`src/rag_shift/`)
- `config.py`: caminhos e prompt; carrega o `.env` em `os.environ` (os módulos leem `os.environ[...]` onde usam: modelo, coleção, TOP_K, CHUNK_SIZE, chaves do Groq); deve ser importado antes de `sentence_transformers` (o `HF_HUB_OFFLINE` é lido no import)
- `preprocessing.py`: chunking estrutural. `normalize` (rodapé, URLs, escapes, preservando os `\n`), `split_sections` (títulos `** Título` + linha de traços; 1º título = edição; título em maiúsculas sem corpo = seção), `strip_boilerplate`, `split_paragraphs` (2+ quebras), `chunk_section` (agrupa até `CHUNK_SIZE`; parágrafo longo cai para sentenças via nltk) e `heading_path` (`edição > seção > título`)
- `corpus.py`: `process_mail` (bruto -> sections/chunks), `build_processed` (grava `the-shift-mails-processed/`, preservando o `enrichment` por `hash` da matéria), `load_corpus` (lê o processado e achata em payloads com edition, section, title)
- `build.py`: ponto de entrada `rag-shift-build`
- `enrichment.py`: schema Pydantic (`companies`, `technologies`, `places`, `people`, `topics` com 13 tópicos fechados), prompt, chamada ao LLM (API compatível com a da OpenAI: `ENRICH_API_KEY`, `ENRICH_BASE_URL`, `ENRICH_MODEL`) e normalização determinística (lista de bloqueio, sufixos societários, aliases só de grafia, grafia canônica por frequência)
- `enrich.py`: ponto de entrada `rag-shift-enrich`; uma chamada por matéria em paralelo, grava `enrichment` com `status` (`ok`, `empty`, `failed`, `rate_limited`), retomável
- `embeddings.py`: modelo SentenceTransformer e cache em `.cache/`; o texto embeddado é `heading_path + texto`
- `index.py`: Qdrant em memória, coleção `the-shift-mails`, `Distance.COSINE`
- `retriever.py`: top 5, um resultado por email (maior score)
- `generator.py`: resposta via Groq (`GROQ_API_KEY`, `MODEL`)
- `cli.py`: ponto de entrada (`rag-shift`), argparse e checagem das variáveis obrigatórias do `.env`
- `scripts/inspect_chunks.py`: valida o chunking sem embeddings (`uv run python scripts/inspect_chunks.py [arquivo.json] | --stats`)

## Pipeline
`the-shift-mails-outputs/` (bruto, imutável) -> `rag-shift-build` -> `the-shift-mails-processed/` (um JSON por email: `sections[]` com `edition`, `section`, `title`, `hash`, `chunks`, `enrichment`) -> `rag-shift-enrich` (preenche `enrichment`) -> `.cache/` (embeddings) -> busca. Mudou o chunking: rebuild + apagar `.cache/`.

## Convenções
- Commits em pt_BR, formato convencional (`feat:`, `fix:`, `chore:`), sem atribuição a IA
- Uma branch por tarefa (`feat/`, `fix/`, `chore/` + kebab-case); nunca commitar direto em master
- Nunca commitar sem confirmação do usuário
- Nunca executar `sudo` nem comandos git que falam com remoto (push, pull, fetch, clone, remote); apresentar o comando para o usuário rodar
- Variáveis em inglês, comentários em português

## Cuidados
- `.env`, `.cache/` e o conteúdo de `the-shift-mails-outputs/` e `the-shift-mails-processed/` não vão para o git (só os `.gitkeep`)
- Mudar corpus, `CHUNK_SIZE` ou `EMBEDDING_MODEL` exige apagar `.cache/`
- Os `\r\n\t` do corpus já são whitespace real após `json.load`; a limpeza é feita com regex, não com nltk
- A hierarquia do texto vem do número de `\n` (1 = linha/bullet, 2 = parágrafo, 3+ = novo título); por isso `normalize` não colapsa as quebras
- 11 emails (convites/webinars) não têm títulos e caem no fallback: o email inteiro vira uma seção
