# US-11 — API HTTP do agente

**Prioridade:** MUST · **Estimativa:** 2h · **Dia:** 2 · **Depende de:** US-10 · **Habilita:** US-13

## Objetivo
Expor o agente e o trace por HTTP, para o frontend (US-13) e para o eval harness (US-12).

## Escopo
| Rota | Descrição |
|---|---|
| `POST /conversations` | cria conversa, devolve `conversation_id` |
| `POST /conversations/{id}/messages` | envia mensagem do lead; devolve resposta, `message_id`, `status` (`answered` \| `handoff` \| `refused`) |
| `GET /conversations/{id}/trace` | eventos do JSONL, já sanitizados |
| `GET /conversations/{id}` | estado: campos coletados, última cotação, breaker |
| `GET /health` | inclui estado do breaker e alcançabilidade do `quote-api` |

- FastAPI. Validação com Pydantic na borda.
- Erro sempre com shape consistente (`{error, message, conversation_id}`), sem stacktrace.
- **`GET /health` não deve chamar `/quote`**: o `/health` do mock é "sempre estavel" (I-09) e
  não diz nada sobre a saúde real. Reportar o **estado do breaker**, que é o sinal honesto.
- Sem autenticação (WON'T) — declarado no README como decisão de escopo, não omissão.

## Critérios de aceitação
- [ ] Conversa completa via `curl`, do zero à cotação
- [ ] `GET /trace` devolve JSON válido e **sem PII** (mesma asserção de US-05)
- [ ] `conversation_id` inexistente ⇒ 404 com shape consistente
- [ ] Exceção não tratada ⇒ 500 sem stacktrace, com evento de trace registrado
- [ ] `/health` reflete `breaker: open` quando o breaker está aberto
- [ ] Duas conversas simultâneas não misturam estado nem arquivo de trace
- [ ] Mensagem vazia ou gigante (>10k chars) é rejeitada na borda
