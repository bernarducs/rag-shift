# AGENTS.md

Protótipo de RAG (CLI) sobre emails da The Shift. Python 3.12, gerenciado com `uv`.

## Comandos
- Gerar a pasta processada (antes da 1ª consulta e quando o chunking mudar): `uv run rag-shift-build`
- Rodar: `uv run rag-shift "pergunta"`
- Enriquecer as matérias com LLM (retomável; precisa de `ENRICH_*` no `.env`): `uv run rag-shift-enrich` (`--limit N` para testar, `--retry-failed`, `--normalize-only` reaplica limpeza, bloqueio, aliases e grafia canônica ao que já está gravado, sem chamar o LLM)
- Ajuda dos comandos: `uv run rag-shift --help` e `uv run rag-shift-build --help` (argparse)
- Adicionar dependência: `uv add <pacote>`

## Estrutura (`src/rag_shift/`)
- `config.py`: caminhos e prompt; carrega o `.env` em `os.environ` (os módulos leem `os.environ[...]` onde usam: modelo, coleção, TOP_K, CHUNK_SIZE, chaves do Groq); deve ser importado antes de `fastembed` (o `HF_HUB_OFFLINE` é lido no import); define `QDRANT_DIR`, `QDRANT_READY` e fixa o `FASTEMBED_CACHE_PATH` em `.cache/fastembed`
- `preprocessing.py`: chunking estrutural. `normalize` (= `tidy(strip_urls(prepare(body)))`: rodapé, URLs, escapes, preservando os `\n`; `link_text` é o mesmo texto com as URLs), `split_sections` (títulos `** Título` + linha de traços; 1º título = edição; título em maiúsculas sem corpo = seção), `strip_boilerplate`, `split_paragraphs` (2+ quebras), `chunk_section` (agrupa até `CHUNK_SIZE`; parágrafo longo cai para sentenças via nltk) `extract_links` (links de uma matéria: título só em item de lista `* Título (url)`, URL sem `utm_*`, deduplicada; descarta YouTube, WhatsApp, Mailchimp, assinatura/institucional do `theshift.info`, ícones de redes sociais; `theshift.info/hot` e `/talk` ficam) e `heading_path` (`edição > seção > título`)
- `corpus.py`: `process_mail` (bruto -> sections/chunks), `build_processed` (grava `the-shift-mails-processed/`, preservando o `enrichment` por `hash` da matéria), `load_corpus` (lê o processado e achata em payloads com edition, section, title, `year` e as listas do `enrichment`: companies, technologies, places, people, topics), `links_by_heading` (atribui os links a cada seção; se os títulos do texto com URLs não batem com os do normalizado, o email fica sem links e o build avisa), `load_processed` (indexa os emails por `mail_key` = `(mail_id, date)`) e `find_links` (acha os links da matéria de um chunk pelo texto, sem mudar o payload do índice nem o `.cache/`)
- `build.py`: ponto de entrada `rag-shift-build`
- `enrichment.py`: schema Pydantic (`companies`, `technologies`, `places`, `people`, `topics` com 13 tópicos fechados), prompt, chamada ao LLM (API compatível com a da OpenAI: `ENRICH_API_KEY`, `ENRICH_BASE_URL`, `ENRICH_MODEL`) e normalização determinística (lista de bloqueio, sufixos societários exceto depois de `&`, espaços e hifens Unicode, aliases só de grafia/sigla/nome por extenso e sem juntar subsidiárias, grafia canônica por frequência dentro de um grupo que ignora acento, caixa, espaço e pontuação, mantendo o `+` e o ponto entre dígitos; empate vai para a grafia com mais acentos), reaplicável com `renormalize` + `canonicalize`
- `enrich.py`: ponto de entrada `rag-shift-enrich`; uma chamada por matéria em paralelo, grava `enrichment` com `status` (`ok`, `empty`, `failed`, `rate_limited`), retomável
- `embeddings.py`: registra o `multilingual-e5-small` como modelo customizado do FastEmbed (não está no catálogo) e monta os `Document` com os prefixos do e5 (`passage: heading_path + texto`, `query: pergunta`); o próprio cliente do Qdrant calcula os vetores
- `index.py`: Qdrant em disco (`QdrantClient(path=.cache/qdrant)`, um processo por vez; `open_index` ingere na 1ª execução e grava o marcador `.cache/qdrant-ready` só ao terminar, então ingestão interrompida recomeça do zero), coleção `the-shift-mails`, `Distance.COSINE`; índices de payload `keyword` em companies, technologies, places, people, topics e `integer` em year
- `retriever.py`: top K (`--limit`), um resultado por email (maior score, pela `mail_key`); aceita `query_filter`
- `query_plan.py`: `QueryPlan` (modo busca/lista/contagem/resumo, `title` da matéria a resumir, empresas, tecnologias, lugares, pessoas, anos, tópicos, `group_by`, `query`), `plan_query` (Groq; na falha vira busca simples), `build_vocabulary` e `resolve_entities` (casam as entidades com a grafia do corpus via `group_key` + `ALIASES`; as desconhecidas vão para a `query`)
- `filters.py`: filtro único (OU dentro do campo, E entre campos) em duas formas: `qdrant_filter` e `section_matches`/`count`/`list_sections` em Python sobre os processados (contagens sem LLM nem embeddings) e `find_by_title` (acha a matéria pelo título, sem acento nem caixa, para o modo resumo)
- `generator.py`: resposta via Groq (`GROQ_API_KEY`, `MODEL`)
- `cli.py`: ponto de entrada (`rag-shift`), argparse (`--limit`, `--modo`, `--sem-filtro`), checagem das variáveis obrigatórias do `.env` e fluxo por modo; cada resultado mostra a data do email em Brasília (o `date` é UTC) e o `edição > seção > título`; resumo usa o texto inteiro da matéria; contagem, lista e resumo não carregam o modelo de embeddings (imports pesados só em `search`)
- `scripts/inspect_chunks.py`: valida o chunking sem embeddings (`uv run python scripts/inspect_chunks.py [arquivo.json] | --stats | --links [arquivo.json]`)

## Pipeline
`the-shift-mails-outputs/` (bruto, imutável) -> `rag-shift-build` -> `the-shift-mails-processed/` (um JSON por email: `sections[]` com `edition`, `section`, `title`, `hash`, `chunks`, `links`, `enrichment`) -> `rag-shift-enrich` (preenche `enrichment`) -> `.cache/qdrant` (índice com vetores e payload, gerado na 1ª consulta) -> busca. Mudou o chunking: rebuild + apagar `.cache/qdrant` e `.cache/qdrant-ready`.

## Convenções
- Commits em pt_BR, formato convencional (`feat:`, `fix:`, `chore:`), sem atribuição a IA
- Uma branch por tarefa (`feat/`, `fix/`, `chore/` + kebab-case); nunca commitar direto em master
- Nunca commitar sem confirmação do usuário
- Nunca executar `sudo` nem comandos git que falam com remoto (push, pull, fetch, clone, remote); apresentar o comando para o usuário rodar
- Variáveis em inglês, comentários em português

## Cuidados
- O `mail_id` **não é único** (865 emails, 557 ids): indexar ou deduplicar emails sempre por `mail_key` (`mail_id` + `date`), nunca só pelo `mail_id`
- `.env`, `.cache/` e o conteúdo de `the-shift-mails-outputs/` e `the-shift-mails-processed/` não vão para o git (só os `.gitkeep`)
- Mudar corpus, `CHUNK_SIZE`, `EMBEDDING_MODEL` ou o `enrichment` (que vai no `chunks.json`) exige apagar `.cache/qdrant` e `.cache/qdrant-ready` (a reindexação leva ~14 min; `.cache/fastembed` é só o modelo e pode ficar)
- O `hash` da seção vem só do texto normalizado, então `links` não o altera e o `enrichment` sobrevive ao build; ao mexer em `normalize` e afins, conferir que os `hash` não mudam
- Os `\r\n\t` do corpus já são whitespace real após `json.load`; a limpeza é feita com regex, não com nltk
- A hierarquia do texto vem do número de `\n` (1 = linha/bullet, 2 = parágrafo, 3+ = novo título); por isso `normalize` não colapsa as quebras
- 11 emails (convites/webinars) não têm títulos e caem no fallback: o email inteiro vira uma seção
