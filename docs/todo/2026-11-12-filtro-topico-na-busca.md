# Filtro por tópico na busca, com relaxamento em cascata

> **Status: a fazer (2026-11-12).** Depende da busca híbrida já mesclada na `master`
> (`2026-11-05-migrar-embeddings-para-fastembed.md`). Decisões abaixo ainda não confirmadas.

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

## Verificação

- "chatgpt na educação" e "o que foi dito sobre ChatGPT na educação?" geram o mesmo plano e a matéria
  "Um tutor digital para cada pessoa" fica no top 5.
- "chatgpt na educação em 2026" não devolve "Não encontrei" por excesso de filtros: o CLI informa o que
  relaxou ou, se mantiver o ano, que ele filtra pela data do email.
- As 8 perguntas que já acertavam no placar aproximado não pioram.

## Pontos em aberto

- O limiar do relaxamento (`--limit` emails) é o certo? Com `--limit 5` o filtro de 18 emails passa; um
  filtro de 4 relaxa.
- Tópicos têm só 13 valores e cobrem assuntos largos ("sociedade, educação e cultura" inclui mídia e
  entretenimento). Vale medir quantas matérias trazem um tópico errado antes de confiar nele como
  filtro duro.
