# US-05 — Trace de conversas e tool calls

**Prioridade:** MUST · **Estimativa:** 2h · **Dia:** 1 · **Depende de:** US-04 · **Habilita:** US-13, US-16

## Contexto
Requisito E-09 do challenge — *"dá pra rastrear o que aconteceu? (cada mensagem/cotação,
com id e status)"* — e os itens 18-27 do seu prompt.
`DISCOVERY.MD §7`: LangWatch self-hosted são **7 serviços e 8 GB RAM**; o trace JSONL próprio
são ~80 linhas e roda offline (D-04).

## Objetivo
Um arquivo por conversa, `data/traces/{conversation_id}.jsonl`, append-only, uma linha por
evento, cobrindo item por item o que você pediu.

## Escopo
Schema completo em `ARCHITECTURE.MD §4`. Mapeamento dos seus requisitos:

| Requisito | Campo |
|---|---|
| conversation/message id | `conversation_id`, `message_id` |
| tool chamada | `tool` |
| input sanitizado | `input_sanitized` (passa por US-04) |
| resultado/status | `status`, `http_status` |
| latência | `latency_ms` |
| erro quando houver | `error{kind, retryable, http_status, message}` |
| skills/regras utilizadas | `skills_used`, `rules_applied` |

- Tipos de evento: `ingress` · `skill_selection` · `llm_call` · `tool_call` · `guard` ·
  `handoff` · `outbound`.
- `span_id` / `parent_span_id` para reconstruir a árvore do turno.
- Escrita append + flush; um arquivo por conversa evita contenção sem precisar de lock.
- Emissão via context manager que **sempre** grava latência, inclusive em exceção.

## Critérios de aceitação
- [ ] Turno feliz produz a sequência `ingress → skill_selection → llm_call → tool_call → guard → outbound`
- [ ] Cada tentativa de retry é seu próprio evento com `attempt` distinto
- [ ] `latency_ms` presente em **todo** `tool_call` e `llm_call`, inclusive nas falhas
- [ ] Todo `guard` com `status:"blocked"` tem `rules_applied` não vazio
- [ ] **Teste anti-vazamento:** regex de CPF/e-mail/telefone/placa contra todos os JSONL gerados pela suíte ⇒ **0 matches**
- [ ] `jq` lê o arquivo sem erro de parse (JSONL válido, uma linha por evento)
- [ ] Escrever trace nunca derruba o turno: falha de I/O é logada e engolida
- [ ] O JSONL de uma conversa completa é o artefato que satisfaz E-04

## Notas
SQLite (stdlib) é o escape hatch declarado se o painel precisar de agregação. Nunca um serviço novo (D-06).
