# US-12 — Eval harness

**Prioridade:** MUST · **Estimativa:** 4h · **Dia:** 3 · **Depende de:** US-03, US-08, US-10, US-14

## Contexto
O serviço real é **aleatório** — medido: 69,6% `200`, 17,6% `5xx`, 12,8% timeout
(`DISCOVERY §3.1`). **Não se testa resiliência contra um dado.** Daí o transporte fake.

E seu requisito 34: dataset para análise e criação de casos de avaliação, **não** como fonte
de verdade de preço — o que `DISCOVERY §5.1` prova: **0 de 1.749** conversas cotáveis batem
com o preço da API.

## Escopo

### `FakeQuoteTransport` — programa a sequência exata de respostas
| Cenário | Programa | Verifica |
|---|---|---|
| Caminho feliz | `[200]` | Cota certo, cita carência (BR-13) |
| Falha transitória | `[503,503,200]` | 3 eventos, backoff, cota no fim |
| Timeout | `[timeout,200]` | Timeout é retry, `latency_ms ≈ 1500` |
| Falha definitiva | `[503,503,503]` | **Zero preço** (BR-02), `quote_failure`, handoff |
| Recusa real | `[422 idade]` | **Zero retry**, `underwriting_refusal`, sem preço |
| `422` ambíguo (plano) | `[422 "Plano 'turbo' inexistente"]` | **Não** vira recusa ao lead: handoff interno (R-16) |
| `422` ambíguo (schema) | `[422 {"detail":[...]}]` | Idem |
| `400` data BR | `[400 Invalid isoformat]` | Zero retry, normalização antes (R-17) |
| CEP inválido | — | **Nem chama**: pré-validação repergunta (R-15) |
| Rate limit | `[429 Retry-After:1, 200]` | 1 retry, contador separado |
| Breaker | `[503]×5` depois `[200]` | Abre em 5, próxima é `skipped` sem rede, half-open após cooldown |
| `5xx` mascarando `422` | `[503,422]` | Conclui recusa, não indisponibilidade (R-06) |

### Suítes
1. **Derivada do dataset** — amostra estratificada por desfecho **e** por elegibilidade de
   recusa. As **751 conversas recusáveis (30%)** viram suíte própria. Replay dos turnos do
   lead. **Ordenar por `message_index`** — 99,8% das conversas têm timestamp não monótono (R-09).
2. **Injection (~20 casos autorais)** — ver US-09. Asserção no **efeito**, não no veredito.
3. **PII** — com e sem pontuação; trace limpo **e** `[CPF]` no contexto.
4. **Insulto preservado** — sai idêntico exceto PII (req 33).
5. **Regras derivadas** — carência presente (BR-13); pro-rata quando `data_inicio.day != 1`
   (BR-14); agravo conferível pelo prefixo de CEP no trace.

### Grading
**Determinístico primeiro.** BR-01..BR-06 e BR-12..BR-14 são asserções em Python, sem LLM.
LLM-judge (`LLM_MODEL_CHEAP`) **só** para tom e qualidade de objeção — onde não há gabarito — e é SHOULD.

### Relatório (`evals/REPORT.md`)
Violação de invariante (**meta: 0**) · taxa de sucesso de cotação · precisão/recall de handoff
contra cenários rotulados · p50/p95 de latência · distribuição de tentativas · aberturas de
breaker · cobertura de campos do trace.

## Critérios de aceitação
- [ ] `make eval` roda **sem rede e sem `OPENAI_API_KEY`** para toda a suíte determinística
- [ ] Suíte determinística completa em < 30s
- [ ] **0 violações de invariante** — e uma violação injetada de propósito é detectada (teste do teste)
- [ ] Todo cenário da tabela acima tem um caso executável
- [ ] Casos do dataset são reproduzíveis (seed fixa) e ordenados por `message_index`
- [ ] Datas congeladas nos testes — nada depende de `date.today()` (R-10)
- [ ] `REPORT.md` é gerado, versionado e legível por humano
- [ ] Smoke contra o serviço **real**: `QUOTE_FAILURE_RATE=0.0` (feliz) e `=1.0` (degradação garantida)
