# US-07 — Agente conversacional

**Prioridade:** MUST · **Estimativa:** 4h · **Dia:** 2 · **Depende de:** US-03, US-05, US-06, US-09 · **Habilita:** US-08

## Contexto
Requisito E-01: atende o lead ponta a ponta — conversa → qualifica → cota → decide.
Provider escolhido: **OpenAI** via `langchain-openai`.
`DISCOVERY.MD` R-08: sem o canal de *mid-conversation system message*, o isolamento de
contexto depende de delimitadores **e** dos gates de US-08 — que são a garantia real.
R-07: LangChain **só** para orquestração; resiliência, gates e trace ficam em Python puro.

## Objetivo
O pipeline de turno de `ARCHITECTURE.MD §3`, do ingress ao rascunho de resposta.

## Escopo
- `orchestrator.py`: ingress (US-04 + US-09) → seleção de skills (US-06) → modelo → tool → modelo.
- **System prompt é constante.** Nenhum caminho de código concatena texto do lead nele.
  Conteúdo do lead sempre em `role:"user"`, dentro de delimitador explícito de conteúdo não confiável.
- Tool `cotar_seguro` com schema **estrito de 5 campos**. **Não existe parâmetro de preço nem
  de desconto** — o modelo é incapaz de setar um, injetado ou não.
- Estado da conversa: campos coletados, tentativas de cotação, última cotação `200`,
  contadores de handoff. Em memória, keyed por `conversation_id` (D-06).
- Coleta incremental: pedir só o que falta, aceitando **rajadas** do lead
  (`DISCOVERY.MD §5`: 16.470 mensagens do lead vs 10.000 do vendedor).
- Mídia (`[documento]`, `[imagem]`, `[audio]` — 6,8% das mensagens): pedir o dado em texto.
  Sem STT (WON'T).
- `LLM_MODEL` / `LLM_MODEL_CHEAP` por env var (D-12) — **confirmar o ID vigente, não chutar**.
- Timeout e retry próprios do LLM, independentes da cotação, e também tracados (§6.4).

## Critérios de aceitação
- [ ] Conversa feliz completa: saudação → coleta → cotação `200` → apresentação com prêmio, franquia, coberturas, **carência** e **pro-rata quando aplicável**
- [ ] O agente pede o CEP de novo quando a pré-validação de US-02 devolve `NeedsInput` (R-15)
- [ ] Lead manda 3 mensagens seguidas: o agente responde uma vez, considerando as três
- [ ] "dia 15/07" é normalizado para `2026-07-15` antes da tool (R-17)
- [ ] Nenhum teste consegue fazer o texto do lead entrar no system prompt (asserção no payload montado)
- [ ] Sem `OPENAI_API_KEY`, a suíte de invariantes ainda roda (LLM fake)
- [ ] Turno completo emite todos os eventos de trace de US-05

## Notas
Máx. **3-5 exemplos curados à mão** para tom (D-10). **Nada** de few-shot em massa: 30% das
conversas do dataset ensinam a mexer na franquia e 100% erram a cobertura (`DISCOVERY §5.2`).
