# AGENTS.md

Protótipo de RAG (CLI) sobre emails da The Shift. Python 3.12, gerenciado com `uv`.

## Comandos
- Rodar: `uv run rag-shift "pergunta"`
- Adicionar dependência: `uv add <pacote>`

## Estrutura (`src/rag_shift/`)
- `config.py`: caminhos e prompt; carrega o `.env` em `os.environ` (os módulos leem `os.environ[...]` onde usam: modelo, coleção, TOP_K, CHUNK_SIZE, chaves do Groq); carrega o `.env` (precisa ser importado antes de `sentence_transformers`)
- `preprocessing.py`: `clean_text` (regex: URLs, rodapé, escapes) e `chunk_text` (nltk, por sentenças)
- `corpus.py`: lê `the-shift-mails-outputs/*.json` e gera os chunks
- `embeddings.py`: modelo SentenceTransformer e cache em `.cache/`
- `index.py`: Qdrant em memória, coleção `the-shift-mails`, `Distance.COSINE`
- `retriever.py`: top 5, um resultado por email (maior score)
- `generator.py`: resposta via Groq (`GROQ_API_KEY`, `MODEL`)
- `cli.py`: ponto de entrada (`rag-shift`)

## Convenções
- Commits em pt_BR, formato convencional (`feat:`, `fix:`, `chore:`), sem atribuição a IA
- Uma branch por tarefa (`feat/`, `fix/`, `chore/` + kebab-case); nunca commitar direto em master
- Nunca commitar sem confirmação do usuário
- Nunca executar `sudo` nem comandos git que falam com remoto (push, pull, fetch, clone, remote); apresentar o comando para o usuário rodar
- Variáveis em inglês, comentários em português

## Cuidados
- `.env`, `.cache/` e o conteúdo de `the-shift-mails-outputs/` não vão para o git (só o `.gitkeep`)
- Mudar corpus, `CHUNK_SIZE` ou `EMBEDDING_MODEL` exige apagar `.cache/`
- Os `\r\n\t` do corpus já são whitespace real após `json.load`; a limpeza é feita com regex, não com nltk
