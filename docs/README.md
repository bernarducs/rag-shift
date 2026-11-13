# docs

Registro das tarefas do projeto: o que fazer (`docs/todo/`) e o que já foi feito (`docs/done/`).

## Nome do arquivo

```
aaaa-mm-dd-tarefa-a-ser-feita.md
```

- `aaaa-mm-dd`: dia em que o doc foi criado. O nome não muda quando a tarefa termina, então a data
  continua sendo a da criação.
- `tarefa-a-ser-feita`: a tarefa em poucas palavras, em minúsculas, sem acento, separadas por hífen.
- Exemplo: `2026-11-05-migrar-embeddings-para-fastembed.md`.

## Fluxo

1. A tarefa nasce como doc em `docs/todo/`.
2. Ao terminar (mesclada na `master`), o doc vai de `docs/todo/` para `docs/done/` com `git mv`, sem renomear, e a
   linha de **Status** no topo passa a dizer o que foi feito e o que ficou em aberto.

## Conteúdo sugerido

Um doc começa com `# Título` e uma linha `> **Status: ...**`. Depois, o que fizer sentido para a
tarefa: contexto e motivação, o que foi medido, decisões e alternativas descartadas, passos,
arquivos afetados e como verificar.
