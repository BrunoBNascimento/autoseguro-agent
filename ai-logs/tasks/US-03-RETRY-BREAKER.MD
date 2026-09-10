# US-03 — Retry com backoff e circuit breaker

**Prioridade:** MUST · **Estimativa:** 2,5h · **Dia:** 1 · **Depende de:** US-02 · **Habilita:** US-07, US-12

## Contexto
Este é o requisito E-07 do challenge — *"o que ele faz quando a `/quote` falha? esse é o ponto
que mais separa"*. `DISCOVERY.MD §4` resolve por cálculo, não por intuição.

Com `p_falha_por_tentativa = 0,304` **(medido)**: 1 tentativa = 70%, 2 = 91%, **3 = 97,3%**.

E a descoberta contraintuitiva (§4.1): um breaker de **janela deslizante 50%/10** — default de
metade dos tutoriais — abre por **falso positivo em 15% das janelas** com o serviço operando
normal. Por **falhas consecutivas (5)**, o falso positivo cai para **0,24%**.

## Objetivo
Envelopar `QuoteClient` de forma que ~97% das cotações tenham sucesso, que nenhuma classe
terminal seja retentada, e que o breaker **não** cause o apagão que deveria prevenir.

## Escopo
```python
QUOTE_TIMEOUT_S      = 1.5   # medido: p50 do sucesso = 0,9ms, max = 25,5ms
QUOTE_MAX_ATTEMPTS   = 3     # 97,3%
QUOTE_BACKOFF_BASE_S = 0.4   # 0,4 → 0,8 com full jitter (±50%)
BREAKER_CONSECUTIVE  = 5     # falhas CONSECUTIVAS, não janela
BREAKER_COOLDOWN_S   = 30.0
BREAKER_HALF_OPEN    = 1     # uma sonda
```
- Retry **só** em `Transient` e `RateLimited`. `Refused`, `InternalDefect` e `NeedsInput`
  retornam na 1ª tentativa (`ARCHITECTURE.MD §6.1`).
- `429`: 1 retry honrando `Retry-After`, em **contador separado** (abre em 3 consecutivos).
  Nunca alimenta o streak do breaker geral — transformar throttling em apagão é auto-sabotagem.
- Breaker aberto ⇒ **não espera, não chama**: retorna `CircuitOpen` na hora e emite o evento
  `breaker_open`, que força a skill `quote_failure` (US-06).
- Cada tentativa é seu **próprio** evento de trace (`attempt: 1,2,3`), inclusive as que falham.

## Critérios de aceitação
- [ ] `[503,503,200]` ⇒ sucesso, 3 eventos de trace, backoff observável entre eles
- [ ] `[422 idade]` ⇒ **1** chamada de rede. Asserção no contador do fake
- [ ] `[400]` ⇒ 1 chamada, e o streak do breaker **não** incrementa
- [ ] `[timeout, 200]` ⇒ timeout tratado como transitório, `latency_ms ≈ 1500` no evento de falha
- [ ] `[503]×5` ⇒ breaker `open`; a 6ª cotação retorna `CircuitOpen` com **0 chamadas de rede**
- [ ] Após `BREAKER_COOLDOWN_S`, half-open envia **exatamente 1** sonda; `200` fecha, falha reabre
- [ ] `[429 Retry-After:1, 200]` ⇒ 1 retry, espera respeitada, streak geral inalterado
- [ ] Teste de calibragem: 10.000 tentativas simuladas com `p=0,30` ⇒ **< 1%** de aberturas espúrias
- [ ] Backoff tem jitter (duas execuções não produzem a mesma sequência de esperas)

## Notas
Pior caso de parede: `1,5 + 0,4 + 1,5 + 0,8 + 1,5 ≈ 5,7s`. Mensagem interina após 2s é SHOULD.
`/health` **não** serve de sinal de saúde: a docstring do mock diz "sempre estavel" (I-09).
