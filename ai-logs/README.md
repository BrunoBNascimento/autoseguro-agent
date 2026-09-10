# Plano de implementação — Desafio FDE Namastex

Discovery e planejamento do agente de cotação **AutoSeguro**.
Challenge: `https://github.com/namastexlabs/namastex-fde-challenge` @ `52a006c`.
**Nada implementado ainda** — este diretório é só o plano.

| Documento | O que responde |
|---|---|
| [`DISCOVERY.MD`](DISCOVERY.MD) | O que o repo realmente contém · requisitos explícitos (E-01..E-12) e implícitos (I-01..I-10) · a matemática da instabilidade *medida* · o que o dataset é e não é · confronto das suas 36 ideias × o challenge · avaliação do LangWatch · 17 riscos |
| [`ARCHITECTURE.MD`](ARCHITECTURE.MD) | Arquitetura mínima: 3 serviços, zero banco · pipeline do turno · os 4 gates de saída · schema de trace · formato das skills · parâmetros de resiliência · BR-01..BR-14 · 16 decisões (ADR) · MUST/SHOULD/WON'T · DAG |
| [`tasks/`](tasks/) | 16 user stories com critérios de aceitação verificáveis |
| [`claude_logs/`](claude_logs/) | Logs crus das sessões de IA (entregável E-05) |

## Os cinco números que decidem o projeto

| Número | O que significa |
|---|---|
| **0,304** | Taxa de falha por tentativa, **medida** em 250 chamadas. Bate com o previsto (0,30) |
| **0,9 ms** | p50 de latência do caminho de sucesso → timeout de 1,5s, não 3s. Pior caso cai de 10,2s para 5,7s |
| **15% vs 0,24%** | Falso positivo do breaker: janela 50%/10 vs 5 falhas consecutivas. Por isso não usamos janela |
| **0 de 1.749** | Conversas do dataset cujo preço bate com a API. Zero. O dataset não é fonte de preço |
| **751 (30%)** | Leads que a API **recusa** (idade > 75 ou veículo > 20a) — e para os quais o vendedor humano cotou preço |

## Decisões pendentes de você

1. **Model ID do OpenAI** vigente em set/2026 — `LLM_MODEL` / `LLM_MODEL_CHEAP` por env var, sem hardcode (D-12, R-08).
2. **`OPENAI_API_KEY`** disponível? Bloqueia US-07.
3. **Docker** precisa de `sudo` (R-01) — `uv` já está instalado e o `quote-service` já foi validado rodando.

## Ordem de execução

`Dia 1` US-01 · US-02 · US-03 · US-04 · US-05 · US-14 → *cotação resiliente e rastreada, sem LLM*
`Dia 2` US-06 · US-07 · US-08 · US-09 · US-10 · US-11 → *agente completo com invariantes garantidos*
`Dia 3` US-12 · US-13 · US-15 (+US-16) → *evals, painel e entrega*

Caminho crítico e linha de corte do Dia 3 em `ARCHITECTURE.MD §12.1` e `§13`.
