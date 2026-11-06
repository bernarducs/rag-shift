# Enriquecimento das matérias

> **Status: experimento concluído (2026-11); decisão: Groq direto com JSON schema, modelo
> `openai/gpt-oss-120b`. Implementação ainda não feita.** GLiNER e LangExtract foram descartados.
> Os números estão em "Resultado do experimento". As seções "Alternativas" e "Desempenho esperado"
> são o texto original, escrito antes do experimento (de memória, não medido).

## Motivação

O RAG atual só faz busca semântica. Isso não responde bem a dois tipos de pergunta:

- **Busca por entidade**: "busque notícias sobre a NVIDIA". A busca vetorial até traz trechos que
  citam a empresa, mas sem garantia (o e5-small trata nomes próprios de forma irregular) e sem
  filtro exato.
- **Agregação / contagem**: "quantos documentos são de 2022?", "quais empresas mais aparecem?".
  O LLM só enxerga o top 5 e não consegue contar; isso exige metadados estruturados.

Enriquecer cada matéria com metadados (empresas, tecnologias, tópicos, ano...) permite filtrar no
Qdrant (payload) combinando filtro exato + busca semântica, e responder agregações a partir dos
metadados, sem passar pelo LLM.

## Onde isso se encaixa

Pipeline atual: `the-shift-mails-outputs/` (bruto) → `rag-shift-build` →
`the-shift-mails-processed/` (um JSON por email, `sections[]` com `hash` e `enrichment: {}`) →
`.cache/` (embeddings) → busca.

- O campo `enrichment` já existe, vazio, **por matéria** (não por chunk), para sobreviver a mudanças
  de `CHUNK_SIZE`. O `build_processed` preserva o conteúdo enquanto o `hash` da matéria não muda.
- O enrichment precisa ser gravado nos arquivos processados (estágio caro, retomável) e depois
  copiado para o payload dos chunks no Qdrant.

## Tamanho do trabalho (medido na pasta processada)

| Métrica | Valor |
|---|---|
| Matérias | 7.452 |
| Caracteres no total | ~12,4 milhões |
| Tamanho por matéria | média 1.664, mediana 1.498, p90 3.124, máx 12.835 |
| Tokens de entrada (aprox., chars ÷ 4) | **~3,1 milhões**, sem contar prompt/exemplos repetidos nem a saída |
| "Garimpo do dia" (listas de notas curtas) | 726 matérias |

## Pontos a decidir

1. **Esquema do enriquecimento**: quais campos extrair (empresas, tecnologias, pessoas, tópicos,
   setor, resumo de uma linha?) e se `year` (derivado de `date`) entra. Cada campo extra custa tokens.
2. **Granularidade**: uma extração por matéria; como tratar o "Garimpo do dia" (cada nota é um
   assunto diferente) e matérias muito longas.
3. **Como extrair**: LLM (qual biblioteca), NER local ou híbrido (ver opções abaixo).
4. **Normalização de entidades**: "NVIDIA" / "Nvidia" / "nvidia" devem virar uma forma só; tratar
   aliases ("Google" / "Alphabet").
5. **Entendimento da pergunta** (como o filtro é acionado):
   - LLM com tool calling/saída estruturada converte a pergunta em filtro + busca (também resolve
     contagens);
   - ou casamento da pergunta com o vocabulário de entidades já extraídas (mais simples, só acha o
     que está escrito igual).
6. **Saída do CLI** para perguntas de filtro/contagem: manter "resposta + top 5"? "Notícias" no
   plural pede mais de 5 resultados?
7. **Orçamento**: limites de taxa e de tokens do plano do Groq para o `MODEL` usado.
8. **Retomada e falhas**: gravar por email; reprocessar só o que falta; registrar matérias que
   falharam em vez de descartá-las em silêncio.

## Alternativas

> Descrição de memória (exceto o que está na seção de LangExtract + Groq). Conferir o estado atual
> de cada biblioteca antes de testar.

| Opção | Como funciona | Pontos fortes | Pontos fracos |
|---|---|---|---|
| **LangExtract** | LLM com exemplos few-shot; devolve itens com a posição no texto | Rastreabilidade por trecho; API simples; lida com documentos longos | Provider do Groq não é nativo (ver abaixo); roteamento por nome de modelo; schema estrito; falhas silenciosas; várias opções que multiplicam chamadas |
| **Groq direto com JSON** | Prompt próprio pedindo JSON (com schema, se o modelo suportar) | Sem dependência nova; controle total do prompt e do custo | Validação e retry por conta própria |
| **Instructor / Pydantic AI** | Saída definida como modelo Pydantic; a biblioteca valida e repete | Saída tipada; retry automático; funciona com endpoints compatíveis com OpenAI | Dependência extra; sem posição no texto |
| **NER local (GLiNER, spaCy)** | Modelo de reconhecimento de entidades em CPU. O GLiNER aceita rótulos livres ("empresa", "tecnologia") | Sem API, sem custo, reproduzível, rápido | Só entidades (sem tópicos nem resumo); qualidade em português precisa ser medida |
| **Dicionário de aliases** | Lista de empresas/termos casada por regex | Determinístico, grátis | Só acha o que foi listado; manutenção manual |
| **Híbrido** | NER local para entidades + LLM só para o que exige linguagem (tópico, resumo) | Reduz tokens e dependência de API | Dois mecanismos para manter |

### LangExtract + Groq (verificado em 2026-11)

- O README do [LangExtract](https://github.com/google/langextract) documenta endpoints compatíveis
  com OpenAI via `ModelConfig(provider="openai", provider_kwargs={"api_key", "base_url"})`. O Groq
  **não é citado** no README.
- A [issue #311 "Adding groq provider"](https://github.com/google/langextract/issues/311) está
  **aberta**, sem resposta de mantenedor; um comentário diz que trocar o `base_url` do provider da
  OpenAI para `https://api.groq.com/openai/v1` funciona. Ou seja: **sem provider nativo**, só o
  caminho compatível com OpenAI.
- Nome do provider: o README usa `"openai"`; um [artigo](https://dev.to/amankumar_apiclaw/googles-langextract-on-a-custom-openai-compatible-api-model-ids-that-route-to-ollama-strict-8dd)
  diz que `"OpenAILanguageModel"` também funcionou (o autor vende um gateway concorrente e testou
  com servidor simulado).
- **Não confirmado**: se `reasoning_effort` em `provider_kwargs` chega à requisição; versão atual
  (README cita 1.6.0, o artigo testou 1.7.1).
- Armadilhas a testar: modelos com nome `llama*`/`qwen*`/`gpt-oss*` são roteados para o Ollama sem
  provider explícito; `response_format` com `json_schema` estrito pode dar erro 400 (contornos:
  `use_schema_constraints=False`, `fence_output=True`); chunks com JSON inválido são descartados
  em silêncio (`resolver_params={"suppress_parse_errors": False}` para ver o erro); `extraction_passes`
  e `max_workers` multiplicam chamadas e estouram limite de taxa; o LangExtract não faz retry
  próprio e uma falha derruba o documento.
- Como a matéria média tem ~1,7 mil caracteres, `max_char_buffer` maior que a matéria evita que a
  biblioteca a divida (uma requisição por matéria).

## Desempenho esperado

**Nada disto foi medido**; são ordens de grandeza para orientar o experimento.

- **Volume**: 7.452 chamadas de LLM (uma por matéria) e ~3,1M de tokens de entrada, mais prompt e
  exemplos repetidos em cada chamada e a saída. `extraction_passes=3` triplicaria isso.
- **Tempo**: dominado pelo limite de taxa do Groq (tokens/min e requisições/min do plano), não
  pela CPU. Pode variar de minutos a horas ou dias; **a medir** no experimento.
- **NER local**: sem custo de API; o tempo em CPU (8 núcleos) é **a medir**.
- **Qualidade**: depende do modelo e do prompt; métricas na seção seguinte.

## Experimento antes de implementar (plano original, já executado)

Amostra: ~20 matérias sorteadas de `the-shift-mails-processed/` (incluir 2–3 de "Garimpo do dia" e
1 longa), de anos diferentes.

Comparar, nas mesmas matérias:
1. GLiNER (rótulos: empresa, tecnologia, pessoa);
2. LangExtract com a configuração do Groq (`base_url`), incluindo um teste de fumaça de uma matéria
   para checar `reasoning_effort` e o schema estrito;
3. Groq direto com JSON e schema simples (Pydantic ou à mão).

Medir e registrar:
- **Qualidade**: entidades corretas, perdidas e inventadas (conferência manual); consistência de
  grafia ("Nvidia" vs "NVIDIA").
- **Custo**: tokens de entrada/saída por matéria e extrapolação para as 7.452.
- **Tempo**: segundos por matéria e o gargalo (rede, limite de taxa ou CPU).
- **Robustez**: quantas respostas falharam ou foram descartadas em silêncio.

Critério de decisão: a opção mais barata e simples que acerte as entidades que importam para filtro
(empresas e tecnologias); recursos extras (posição no texto, resumo) só entram se justificarem o custo.

## Resultado do experimento

O código do experimento (scripts, resultados e gabarito) foi apagado depois da decisão; este texto
é o registro. Para reproduzir, a seção "Especificação para a implementação" tem o necessário.

### Como foi feito

- **Amostra:** 30 matérias de `the-shift-mails-processed/`, sorteio com semente fixa (42),
  estratificado por ano (2022: 4, 2023: 7, 2024: 7, 2025: 4, 2026: 8). Inclui 3 "Garimpo do dia",
  1 matéria longa (11,5 mil caracteres) e 1 de conteúdo patrocinado. **Não entrou nenhum email do
  fallback** (sem títulos). Texto enviado: `heading_path` + chunks da matéria juntos.
- **Métodos comparados:**
  - **GLiNER** `urchade/gliner_multi-v2.1`, rótulos `empresa`/`tecnologia`/`pessoa`, limiar 0,5,
    texto em janelas de 1.200 caracteres, CPU. Tópicos por similaridade de cosseno do e5 com a lista.
  - **Groq direto**: `chat.completions` com `response_format` `json_schema` (modelo Pydantic),
    `reasoning_effort="low"`, `temperature=0`, validação com Pydantic e 1 retry em `json_object`.
  - **LangExtract 1.7.1** pelo endpoint compatível com OpenAI do Groq (`provider="openai"`,
    `base_url="https://api.groq.com/openai/v1"`), 2 exemplos few-shot, 1 chamada por matéria
    (`max_char_buffer=15000`, `extraction_passes=1`, `max_workers=1`).
  - Groq direto e LangExtract rodaram com `gpt-oss-120b` e com `gpt-oss-20b`.
- **Gabarito:** os candidatos são a união das empresas e tecnologias dos 3 métodos (GLiNER, Groq
  120b, LangExtract 120b), pré-marcados quando ao menos 2 métodos concordavam. A revisão manual
  corrigiu as marcações e acrescentou as entidades que faltavam. **Só empresas e tecnologias foram
  revisadas**; pessoas e tópicos não têm gabarito.
- **Métrica:** precisão = acertos ÷ (acertos + errados); recall = acertos ÷ (acertos + perdidos).
  Um acerto é um nome igual ao do gabarito após normalizar (sem acento, minúsculas, aliases), por
  matéria e por campo. Não casa por posição no texto.

### Qualidade (contra o gabarito revisado)

| método | campo | acertos | errados | perdidos | precisão | recall |
|---|---|---|---|---|---|---|
| GLiNER | empresas | 73 | 16 | 5 | 0,82 | 0,94 |
| GLiNER | tecnologias | 45 | 36 | 26 | 0,56 | 0,63 |
| **Groq 120b** | empresas | 72 | 2 | 6 | **0,97** | 0,92 |
| **Groq 120b** | tecnologias | 53 | 16 | 18 | 0,77 | **0,75** |
| LangExtract 120b | empresas | 69 | 7 | 9 | 0,91 | 0,88 |
| LangExtract 120b | tecnologias | 48 | 11 | 23 | **0,81** | 0,68 |

Limites desta medição: a amostra é pequena (cerca de 80 itens por campo), então diferenças de 2 a 4
pontos não são significativas; e, como os candidatos vieram da união dos métodos, uma entidade correta
achada por um só método e não anotada em "faltando" aparece como erro dele. Serve para comparação
relativa, não como medida absoluta. O Groq 20b rodou sem falhas, mas não foi pontuado.

### Custo e tempo (30 matérias, extrapolado para as 7.452)

| método | falhas | tokens entrada/matéria | tokens saída/matéria | tokens no corpus |
|---|---|---|---|---|
| GLiNER | 0/30 | - | - | 0 (local, ~0,7 s/matéria em CPU, ~1,5 h) |
| Groq 120b | 0/30 | 965 | 197 | ~8,7 M |
| LangExtract 120b | 0/30 | 1.130 | 455 | ~11,8 M |
| Groq 20b | 0/30 | 965 | 137 | ~8,2 M |
| LangExtract 20b | 1/30 | 1.130 | 35 | (sem valor: não extraiu nada) |

Os segundos por matéria medidos (5,9 s no Groq 120b, 10,4 s no LangExtract 120b) estão **inflados
pela espera do limite de tokens/min** do plano gratuito (o SDK repete a chamada sozinho): as
primeiras chamadas levaram menos de 1 s e depois passaram a 7-12 s. Não representam a latência real.

### O que se concluiu

- **Groq direto ≥ LangExtract** em empresas e recall de tecnologias, com menos tokens (~35%) e sem
  dependência extra. O LangExtract só acrescenta a posição de cada trecho no texto, que o filtro e a
  contagem não usam. A diferença de tokens vem dos exemplos few-shot (+165 de entrada) e do formato
  de saída, um objeto por menção (455 contra 197 tokens de saída); o alinhamento ao texto é local e
  não gasta tokens.
- **LangExtract com o 20b falha em silêncio:** devolveu `{"extractions": []}` em 29 de 29 matérias,
  sem erro. Com `reasoning_effort` médio ou alto o modelo pediu o texto em vez de extrair. Com o 120b
  funcionou.
- **GLiNER** tem bom recall em empresas, mas erra setores e termos genéricos como empresa
  ("empresas", "startups", "varejo", "B2B") e, em tecnologias, "IA" (6 vezes), "AI", "API", "app".
  Os tópicos por similaridade de e5 ficaram enviesados ("cibersegurança" em 19 das 30 matérias).
- **Tecnologias são o ponto fraco de todos os métodos** (precisão 0,56-0,81, recall 0,63-0,75). Parte
  disso é critério ainda indefinido (ver "Pontos em aberto").
- **Dúvidas do to-do resolvidas:** `reasoning_effort` em `provider_kwargs` do LangExtract chega à
  requisição (passá-lo direto em `extract()` dá `TypeError`); `fence_output=True` causa erro 400 no
  Groq porque o provider já envia `json_object`; gpt-oss exige `provider` explícito para não ser
  roteado ao Ollama.
- **Normalização:** as grafias de uma mesma entidade variaram pouco (poucas chaves com mais de uma
  grafia). Ainda assim a normalização determinística é necessária (ver especificação).

### Limites do Groq (informados pelo usuário em 2026-11)

| plano | modelo | req/min | req/dia | tokens/min | tokens/dia |
|---|---|---|---|---|---|
| gratuito | gpt-oss-120b | 30 | 1.000 | 8.000 | 200.000 |
| gratuito | llama-3.3-70b-versatile | 30 | 1.000 | 12.000 | 100.000 |
| gratuito | llama-3.1-8b-instant | 30 | 14.400 | 6.000 | 500.000 |
| desenvolvedor | gpt-oss-120b | 1.000 | - | 250.000 | não informado |

No plano gratuito o limite diário de tokens inviabiliza o corpus inteiro: ~170 matérias por dia no
gpt-oss-120b, cerca de 43 dias para as 7.452. No plano desenvolvedor o limite de tokens/min permite
~215 matérias/min, ou seja, o corpus em torno de 35 min a 1 h com chamadas em paralelo. O custo
estimado é de cerca de US$ 2 pelo preço que se lembrava do gpt-oss-120b (~US$ 0,15/M de entrada e
~US$ 0,60/M de saída), **não conferido**; confirmar na página de preços antes de rodar.

### Decisão

**Groq direto com JSON schema, `openai/gpt-oss-120b`, no plano desenvolvedor.** Motivos: melhor ou
igual qualidade nos dois campos que importam para filtro, menor custo de tokens que o LangExtract,
sem dependência nova (o `groq` e o Pydantic, que vem com ele, já estão no projeto) e controle total do
prompt. GLiNER e LangExtract não entram. Se o plano gratuito for obrigatório, a alternativa é rodar
com retomada ao longo de semanas (ver "Retomada e falhas") ou testar o `llama-3.1-8b-instant`
(~19 dias; qualidade em português **não testada**).

### Especificação para a implementação

- **Campos:** `year` (derivado de `date`, sem LLM), `companies`, `technologies`, `topics` (lista
  fechada). `people` foi extraído no experimento, mas não foi revisado; decidir se entra (custa
  tokens e serve pouco ao filtro).
- **Tópicos (rascunho, ainda sem revisão):** inteligência artificial; cibersegurança; cripto e
  blockchain; fintech e pagamentos; startups e venture capital; big techs; semicondutores e hardware;
  regulação e políticas públicas; sustentabilidade e clima; trabalho e recursos humanos; liderança e
  gestão; marketing e varejo; saúde e biotecnologia; mobilidade e energia; pesquisa e ciência.
  A qualidade dos tópicos do Groq não foi avaliada (não houve gabarito).
- **Esquema Pydantic:**
  `companies: list[str]`, `technologies: list[str]`, `people: list[str]`,
  `topics: list[Literal[<tópicos acima>]]`, todos com `default_factory=list`.
- **Prompt (sistema):** pede metadados de uma matéria da newsletter The Shift em português:
  `companies` (empresas e organizações, nome oficial curto, ex.: "Nvidia", "Google", sem sufixos como
  Inc/S.A.), `technologies` (tecnologias, produtos e modelos, ex.: "ChatGPT", "computação quântica"),
  `people` (pessoas citadas pelo nome) e `topics` (1 a 3, exclusivamente da lista). Termina com
  "Inclua só o que está no texto; não invente. Se não houver, devolva lista vazia." Usuário: título
  completo (`heading_path`) + texto da matéria.
- **Chamada:** `response_format={"type": "json_schema", ...}` com `Enrichment.model_json_schema()`,
  `reasoning_effort="low"`, `temperature=0`; na falha, 1 retry com `{"type": "json_object"}`.
- **Normalização determinística** (aplicada às saídas, não confiar só no LLM): tirar espaços e
  pontuação das pontas; remover sufixos societários (Inc, Corp, Ltd, Ltda, S.A., LLC, GmbH, PLC, Co);
  chave de comparação sem acento e em minúsculas; forma canônica = grafia mais frequente por chave;
  aliases. **Aliases iniciais (precisam de revisão):** Alphabet → Google (confirmado pelo usuário),
  Facebook → Meta, Open AI → OpenAI, Microsoft Corporation → Microsoft, Amazon Web Services → AWS.
- **Status por matéria** (a gravar em `enrichment`): `ok`, `empty` (nenhuma entidade; revisar, porque
  uma resposta sem sentido também passa na validação com tudo vazio), `failed` e `rate_limited`
  (429; resolve-se esperando), mais `error` e `attempts`. O experimento só guardava `error` (texto
  bruto da exceção) e `attempts`.

### Pontos em aberto

- **Critério de "tecnologia":** "IA" genérica conta? órgãos como ANAC e Bacen são empresas? Pix é
  produto? países e cidades entram? Definir antes de rodar o corpus; é a maior fonte de divergência.
- **Aliases:** revisar a lista acima e decidir como tratar controladoras e marcas.
- **Qualidade de pessoas e tópicos:** não revisada.
- **Cobertura do fallback:** os 11 emails sem títulos não entraram na amostra.
- **Limite de tokens por dia no plano desenvolvedor:** não informado.
- **Garimpo do dia:** entrou 3 vezes na amostra, sem análise separada.

## Depois da escolha

1. Fechar o critério de entidade, a lista de tópicos e os aliases (acima).
2. Implementar a extração no pacote (`src/rag_shift/`): Groq direto, chamadas em paralelo (8 a 16),
   por email, com retomada e status; gravar em `enrichment` dos arquivos processados (o
   `build_processed` já preserva por `hash`).
3. Copiar o `enrichment` para o payload dos chunks e criar o índice de payload no Qdrant.
4. Entender a pergunta (filtro e contagem) e ajustar a saída do CLI. Sugestão: LLM com tool calling
   gera `{modo: busca|lista|contagem, empresas, anos, tópicos, consulta}`; empresas casadas contra o
   vocabulário normalizado; contagens calculadas em Python sobre os arquivos processados, sem LLM.
5. Atualizar `README.md` e `AGENTS.md`.
