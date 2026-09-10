# US-10 — Handoff para atendimento humano

**Prioridade:** MUST · **Estimativa:** 1,5h · **Dia:** 2 · **Depende de:** US-08 · **Habilita:** US-11, US-12

## Contexto
Requisito E-08 do challenge: *"o critério de passar pro humano é explícito e defensável?"*
`DISCOVERY.MD §5.3` *[medido]*: **0 ocorrências** de `atendente`/`humano`/`supervisor` nas
26.470 mensagens. **Não existe um único exemplo de handoff no dataset** — o critério é
inteiramente autoral, o que reforça escrevê-lo como regra explícita e não deixar o modelo inferir.

## Objetivo
Gatilhos determinísticos, decisão rastreável e payload útil para o humano que assume.

## Escopo
| Gatilho | Regra | Detecção |
|---|---|---|
| Lead pede humano | BR-09 | intenção + palavras-chave |
| Cotação falhou definitivamente | BR-10 | evento `quote_retries_exhausted` (2º ciclo) ou `breaker_open` |
| Exige negociação / exceção comercial | BR-08 | `authority_gate` |
| Fora de escopo ou das regras | BR-11 | skill `out_of_scope` |
| Defeito interno (`422` ambíguo, `400`) | BR-08 | `InternalDefect` de US-02 — **jamais comunicado como recusa** (R-16) |

**Recusa de subscrição NÃO é handoff (BR-12).** Idade > 75 ou veículo > 20 anos é regra dura
da seguradora — não há o que negociar. Vira `underwriting_refusal`: comunicar com clareza,
sem preço, sem prometer revisão. **30% dos leads do dataset caem aqui**, e o vendedor humano
cotou preço para todos eles.

**Payload do handoff:** `conversation_id`, motivo + `rule_id`, campos coletados
(**sanitizados**), histórico de tentativas de cotação com status e latência, skills usadas,
resumo em uma frase. Persistido no trace como evento `handoff`.

## Critérios de aceitação
- [ ] `"quero falar com um atendente"` ⇒ handoff `BR-09` em 1 turno
- [ ] 2 ciclos de retry esgotados ⇒ handoff `BR-10`, **sem nenhum preço na conversa**
- [ ] Breaker aberto ⇒ `quote_failure` e, na insistência, handoff — não uma 3ª tentativa
- [ ] `"me dá um desconto"` ⇒ `authority_gate` + handoff `BR-08`
- [ ] Idade 80 ⇒ `underwriting_refusal`, **não** handoff, sem preço, motivo explícito
- [ ] Veículo 2001 ⇒ idem
- [ ] `422 "Plano 'turbo' inexistente"` ⇒ handoff por defeito interno, e o lead **não** ouve que foi recusado
- [ ] Payload de handoff não contém CPF, e-mail, telefone nem placa
- [ ] Após handoff, o agente não volta a vender na mesma conversa
- [ ] Cada handoff tem `rule_id` no trace — o critério é auditável, não implícito

## Notas
Documentar os gatilhos numa tabela no README: E-08 pede que o critério seja **explícito**, e
uma tabela é mais defensável que um parágrafo.
