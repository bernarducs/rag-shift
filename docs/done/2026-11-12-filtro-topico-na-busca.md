# Filtro por tópico na busca, com relaxamento em cascata

> **Status: feito (2026-11-18), na branch `feat/eval-retrieval`, ainda sem merge na `master`.**
> Depende da busca híbrida já mesclada na `master`
> (`2026-11-05-migrar-embeddings-para-fastembed.md`). Entregue: avaliação versionada
> (`scripts/eval_retrieval.py`), regra do tópico no prompt do plano e relaxamento em cascata
> (`filters.relax_plan` + `retriever.retrieve_with_plan`). "chatgpt na educação" foi de 9º para 2º.
> Em aberto: perguntas 4, 9 e 10 (ver "Avaliação antes e depois") e a qualidade dos 13 tópicos.

## Motivação

Perguntas curtas sobre um assunto dentro de uma entidade, como "chatgpt na educação", devolvem
resultados dominados pela entidade e ignoram o assunto. O enrichment já tem o que falta (o tópico
da matéria), mas o plano da pergunta o usa de forma instável.

## O que foi medido (2026-11-12)

Pergunta de referência: "chatgpt na educação". A matéria esperada é "Um tutor digital para cada
pessoa" (11/12/2025), marcada com `ChatGPT` e com o tópico "sociedade, educação e cultura".

| Busca | Posição da matéria esperada |
|---|---|
| denso, sem filtro | 79ª |
| híbrido, sem filtro | 8ª |
| denso, `ChatGPT` + tópico educação | 4ª |
| híbrido, `ChatGPT` + tópico educação | **2ª** |
| híbrido, só tópico educação | 2ª |

Quantas matérias sobrevivem a cada filtro (matérias / emails):

| Filtro | Matérias | Emails |
|---|---|---|
| `ChatGPT` | 439 | 298 |
| `ChatGPT` + ano 2026 | 93 | 74 |
| `ChatGPT` + tópico educação | 18 | 18 |
| `ChatGPT` + tópico educação + 2026 | **2** | 2 |

- **A busca híbrida sozinha não resolve:** nos dois modos a palavra "ChatGPT" domina e "educação" pesa
  pouco. No placar aproximado das 10 perguntas de referência, denso 38 e híbrido 37 de 50.
- **O plano é instável:** "chatgpt na educação" gerou só `tecnologia=ChatGPT`; "o que foi dito sobre
  ChatGPT na educação?" gerou `ChatGPT` + tópico educação, e o resultado foi melhor (entrou "Um tutor
  digital", e as fontes passaram de só 2023 para 2023 a 2025).
- **Filtros somados esvaziam o resultado:** com o ano, restam 2 matérias, nenhuma sobre o assunto, e a
  resposta é "Não encontrei".
- **O ano filtra pela data do email.** "Em 2026" pode querer dizer "publicado em 2026" ou "sobre 2026".
  A matéria esperada saiu em dezembro de 2025 e fala de 2026, então o filtro de ano a exclui.

## Decisões propostas

1. **Quando o tópico entra no filtro:** se a pergunta nomear um assunto que corresponda a um dos 13
   tópicos, ele entra junto com a entidade nomeada. A regra vai explícita no prompt do plano, para
   frases quase iguais gerarem o mesmo plano. Em lista e contagem o comportamento atual continua.
2. **Relaxamento em cascata:** se o filtro deixar menos de `--limit` emails, solta primeiro o tópico,
   depois a entidade e por último o ano (é o que o usuário escreveu de forma explícita). O CLI imprime
   o que soltou. A contagem de emails por combinação sai de `filters.matching_sections` em Python,
   antes de consultar o Qdrant.
3. **Ano:** continua filtrando pela data do email, e a linha de interpretação do CLI avisa isso.

## Passos

1. Versionar a avaliação: `scripts/eval_retrieval.py`, com as 10 perguntas de referência, o rótulo
   esperado de cada uma (tópico ou tecnologia do enrichment) e a posição da matéria esperada para
   "chatgpt na educação". Hoje o script existe só na pasta temporária da sessão.
2. `query_plan.py`: regra do tópico no prompt e exemplos.
3. `filters.py` + `cli.py`: função de relaxamento e mensagem do que foi solto.
4. Rodar a avaliação antes e depois e anotar os números aqui.
5. Atualizar `README.md` e `AGENTS.md` (regras de filtro e relaxamento) e mover este doc de `docs/todo/` para `docs/done/`.

## Avaliação antes e depois (2026-11-18)

Avaliação: `uv run python scripts/eval_retrieval.py`. 10 perguntas, cada uma com uma lista de emails
esperados (vale o primeiro que aparecer); mede a posição entre os 30 primeiros emails. Escolhi as
perguntas e os emails esperados lendo o texto das matérias; o gabarito é meu e pode ser discutido.
Na 8 (fadiga de IA) e na 9 (comida com biotecnologia) aceitei um segundo email.

O "sem filtro" é a busca híbrida pura e é determinístico. O "com plano" usa o Groq e varia entre
execuções (as perguntas 2 e 4 trocaram o rótulo entre duas rodadas do mesmo código).

| # | Pergunta | Sem filtro | Com plano antes | Com plano depois |
|---|---|---|---|---|
| 1 | chatgpt na educação | 8 | 9 | **2** |
| 2 | o que mudou no framework de cibersegurança do NIST? | 1 | 1 | 1 |
| 3 | o que a Meta anunciou com a Microsoft sobre o Llama 2? | 1 | 1 | 1 |
| 4 | por que os preços de celulares e PCs vão subir em 2026? | 1 | 1 | 1 |
| 5 | executivos usando ferramentas de IA sem aprovação da empresa | 3 | - | 3 |
| 6 | IA e drones no agronegócio | 1 | 1 | 1 |
| 7 | taxação de compras em sites internacionais como a Shein | 1 | 1 | 1 |
| 8 | cansaço mental por usar IA o tempo todo | 2 | 2 | 2 |
| 9 | como estão as startups que fazem comida com biotecnologia? | 6 | - | - |
| 10 | TOTVS lançou um modelo de IA brasileiro para empresas | 2 | 1 | 2 |

`-` = fora dos 30 primeiros emails.

| | hit@1 | hit@5 | MRR |
|---|---|---|---|
| Sem filtro | 5/10 | 8/10 | 0,662 |
| Com plano, antes | 6/10 | 7/10 | 0,661 |
| Com plano, depois (rodada 1) | 5/10 | 9/10 | 0,683 |
| Com plano, depois (rodada 2) | 5/10 | 9/10 | 0,683 |

Rótulo esperado no plano: 6/10 antes; 5/10 e 6/10 depois.

- **Ganho:** a pergunta de referência saiu de 9º para 2º, e o hit@5 subiu de 7/10 para 9/10. A 5 deixou
  de cair fora do top 30 (o plano agora vem sem filtro e o resultado é o da busca pura, 3º).
- **Perda:** a 10 passou de 1º para 2º. O plano agora inclui o tópico "inteligência artificial e dados"
  (a pergunta fala de "modelo de IA"), que é largo e deixa entrar mais matérias concorrentes. É o risco
  do ponto em aberto sobre a qualidade dos tópicos.
- **Sem efeito:** a 9 continua fora do top 30 com plano. O plano filtra por `biotecnologia` e pelo
  tópico "saúde e biotecnologia", que não é onde está a matéria de FoodTech. O relaxamento não age
  porque o filtro ainda deixa emails suficientes.
- **Plano ainda instável:** o plano segue variando entre execuções, e o rótulo esperado só aparece em
  5 ou 6 de 10 perguntas. O prompt melhorou o caso de referência, não a estabilidade em geral.
- **Perguntas que dependem do ano:** com "chatgpt na educação em 2026" o filtro de tópico cai (sobram
  74 emails só com `ChatGPT` + 2026), o CLI avisa o que soltou, e a resposta diz que não achou nada
  sobre educação em 2026. É coerente com os dados: a matéria esperada é de dezembro de 2025.

### Verificação no CLI

- "chatgpt na educação" e "o que foi dito sobre ChatGPT na educação?" geram o mesmo plano
  (`ChatGPT` + tópico "sociedade, educação e cultura") e "Um tutor digital para cada pessoa" fica no
  top 5 (2º e 3º).
- "chatgpt na educação em 2026" imprime `Poucos emails com os filtros (menos de 5); soltei tópicos e
  sobraram 74.` e a linha de interpretação mostra `anos (data do email): 2026`.

## Verificação

- "chatgpt na educação" e "o que foi dito sobre ChatGPT na educação?" geram o mesmo plano e a matéria
  "Um tutor digital para cada pessoa" fica no top 5.
- "chatgpt na educação em 2026" não devolve "Não encontrei" por excesso de filtros: o CLI informa o que
  relaxou ou, se mantiver o ano, que ele filtra pela data do email.
- As 8 perguntas que já acertavam no placar aproximado não pioram.

## Pontos em aberto

- O limiar do relaxamento (`--limit` emails) é o certo? Com `--limit 5` o filtro de 18 emails passa; um
  filtro de 4 relaxa. Ele só olha a quantidade de emails, não se são os certos (caso da pergunta 9).
- Tópicos têm só 13 valores e cobrem assuntos largos ("sociedade, educação e cultura" inclui mídia e
  entretenimento). Vale medir quantas matérias trazem um tópico errado antes de confiar nele como
  filtro duro.
