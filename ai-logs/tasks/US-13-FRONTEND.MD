# US-13 — Frontend Next.js: chat + painel de trace

**Prioridade:** MUST (escopado) · **Estimativa:** 5h · **Dia:** 3 · **Depende de:** US-11

## Contexto
**O challenge não pede frontend** — é requisito da sua stack. Ele entra porque o **painel de
trace** ataca diretamente E-09 (*"dá pra rastrear o que aconteceu?"*) e produz E-04 (*"log de
uma execução completa"*) de graça (D-14). Layout aprovado no wizard de HITL.

## Escopo
Duas colunas: chat à esquerda, trace ao vivo à direita.

```
┌─────────────────────┬───────────────────────────┐
│  CHAT (WhatsApp-ish)│  TRACE  conv_a1b2         │
│                     │  ─────────────────────────│
│  lead: quanto fica  │ ✓ injection_scan  benign  │
│        o seguro?    │   12ms                    │
│                     │ ✓ pii_mask   cpf,email    │
│  bot: Pra cotar eu  │ ✓ skills  quote           │
│  preciso de idade,  │ ✗ quote_api  503  1.2s    │
│  ano do carro e CEP │ ↻ retry 1/3  backoff 0.5s │
│                     │ ✓ quote_api  200  340ms   │
│  lead: 35, 2022,    │   premio R$ 209,90        │
│        01310-100    │ ✓ price_gate  PASS        │
│                     │   skills: quote           │
│  bot: Completo por  │ ─────────────────────────│
│  R$ 209,90/mes      │  breaker: CLOSED  0/5     │
└─────────────────────┴───────────────────────────┘
```

- Next.js (App Router), uma página. Sem lib de estado, sem design system.
- Chat: envia para `POST /conversations/{id}/messages`.
- Painel: faz poll em `GET /conversations/{id}/trace`. Sem WebSocket (WON'T).
- Cada evento mostra ícone de status, tipo, latência e, quando houver, `rules_applied`.
- Rodapé com estado do breaker e contador de falhas consecutivas.
- Badge de handoff/recusa quando o desfecho não é resposta normal.
- Botão "exportar trace" ⇒ baixa o JSONL. **É o artefato de E-04.**

## Critérios de aceitação
- [ ] `docker compose up` e o chat funciona em `localhost:3000` sem passo manual
- [ ] Conversa completa pela UI, com a cotação saindo
- [ ] Retry aparece no painel como **eventos separados** com latência
- [ ] Com `QUOTE_FAILURE_RATE=1.0`, a UI mostra a degradação e **nenhum preço**
- [ ] Breaker abrindo é visível no rodapé
- [ ] Painel **não** exibe PII (consome o trace já sanitizado)
- [ ] Exportar trace baixa um JSONL válido
- [ ] Zero chave de API no bundle do cliente

## Linha de corte (Dia 3, 12h)
Se o painel não estiver de pé: vira **dump JSON estático** da rota de trace (~30 min) e o
tempo vai para o README de decisões e o log da execução completa. E-03 e E-04 são
entregáveis **nomeados**; painel bonito não é.
