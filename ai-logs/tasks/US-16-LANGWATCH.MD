# US-16 — Exportador LangWatch (opcional)

**Prioridade:** SHOULD · **Estimativa:** 1h · **Dia:** 3 (se sobrar) · **Depende de:** US-05

## Contexto
Seu requisito 28: *"avaliar langwatch ou solução equivalente pra tracing/evals"*.
A **avaliação** está feita em `DISCOVERY.MD §7`, com fatos verificados em 2026-09-10 contra
o repo oficial (Apache-2.0, 3.530 stars) e a doc de self-hosting — não de memória.

| Opção | Custo | Veredito |
|---|---|---|
| Self-hosted | **7 serviços** (`app`, `workers`, `langwatch_nlp`, `langevals`, `postgres:16`, `redis`, `clickhouse`), **4 vCPU / 8 GB RAM / 20 GB** | **WON'T** |
| Cloud (grátis) | 1 env var + `langwatch.setup()` + callback no `RunnableConfig` | **SHOULD** |
| JSONL próprio | ~80 linhas, zero infra | **MUST** (feito em US-05) |

O requisito é "**avaliar**", e a avaliação com números é a entrega. A adoção é opcional.

## Escopo
- `agent/tracing/langwatch.py`: se `LANGWATCH_API_KEY` estiver ausente ⇒ **no-op silencioso**.
- Espelha o **mesmo dict já sanitizado** de US-05. Nunca payload cru.
- Callback do LangChain injetado no `RunnableConfig` do agente.
- Documentar no README: opcional, desligado por default, e **por quê** — o avaliador precisa
  conseguir rodar o repo sem criar conta em SaaS nenhum.

## Critérios de aceitação
- [ ] Sem `LANGWATCH_API_KEY`, tudo funciona e nada é enviado (asserção: 0 chamadas de rede)
- [ ] Com a chave, o trace aparece no dashboard
- [ ] O payload enviado passa pelo sanitizador de US-04 — **teste explícito de que nenhum CPF sai da máquina**
- [ ] Falha do exportador **não** derruba o turno (best-effort, erro logado)
- [ ] Nenhuma dependência nova quando a feature está desligada (import lazy)

## Notas
Se o tempo apertar, esta US cai inteira sem prejuízo: o requisito 28 pede avaliação, e ela
está em `DISCOVERY.MD §7` com os números de infraestrutura.
