# US-02 — Cliente da API de cotação com taxonomia de erro

**Prioridade:** MUST · **Estimativa:** 2,5h · **Dia:** 1 · **Depende de:** US-01 · **Habilita:** US-03, US-07

## Contexto
`DISCOVERY.MD §3.2/§3.3` — medido em 250 chamadas: 69,6% `200`, 17,6% `5xx`, 12,8% timeout.
**Três armadilhas confirmadas empiricamente**, e as três são responsabilidade do cliente:
- `422` tem **3 significados** (recusa real · plano inexistente · schema Pydantic). Dois são bug nosso.
- **CEP inválido retorna `200`** com `m_regiao=1.0` → sub-cota 30% em silêncio.
- `data_inicio: "15/07/2026"` → `400 Invalid isoformat`.

## Objetivo
`QuoteClient.quote(params) -> QuoteOutcome` — um resultado tipado, nunca uma exceção crua,
com o erro **classificado pelo corpo** e não pelo status.

## Escopo
```python
QuoteOutcome = Ok(quote)                      # 200
             | Refused(motivo, kind)          # 422 cotacao_recusada + motivo de idade/veiculo
             | InternalDefect(detail)         # 422 plano inexistente | 422 detail[] | 400
             | Transient(http_status, detail)  # 5xx | 408 | timeout | conexão
             | RateLimited(retry_after)        # 429 (não existe no mock; política + fake)
```
- **Pré-validação obrigatória** dos 5 campos (`ARCHITECTURE.MD §6.3`), com **CEP por regex
  `^\d{5}-?\d{3}$`**. Campo inválido ⇒ `NeedsInput(campo)`, não chamada.
- Normalizar `data_inicio` para ISO; **omitir** quando ausente (nunca `""`, que muda o comportamento).
- `plano_id` validado contra `/planos` (buscado uma vez e cacheado em memória).
- `httpx` com `timeout=1.5s` (US-03 define retry/breaker por fora).
- **Injeção de transporte** por construtor → `FakeQuoteTransport` dos evals entra aqui.
- Retorno inclui `latency_ms` e `attempt` para o trace.

## Critérios de aceitação
- [ ] `422 "Idade acima do limite"` ⇒ `Refused(kind="idade")`; `422 "Veiculo com mais de 20 anos"` ⇒ `Refused(kind="veiculo")`
- [ ] `422 "Plano 'turbo' inexistente"` ⇒ **`InternalDefect`**, nunca `Refused`
- [ ] `422 {"detail":[...]}` ⇒ `InternalDefect`
- [ ] `400 Invalid isoformat` ⇒ `InternalDefect`
- [ ] `cep="abc"` ⇒ `NeedsInput("cep")` **sem tocar a rede** (asserção: 0 chamadas no fake)
- [ ] `cep="07123456"` (sem hífen) é aceito e produz `m_regiao=1.3`
- [ ] `data_inicio="15/07/2026"` é normalizado para `2026-07-15` antes de sair
- [ ] `/planos` é buscado **uma** vez por processo
- [ ] Zero regra de negócio aqui: o cliente não decide o que dizer ao lead

## Notas
`/quote` é cálculo puro (I-07) ⇒ **retry é seguro sem chave de idempotência**. Registrar isso
em comentário: se um dia virar emissão de apólice, essa premissa cai.
