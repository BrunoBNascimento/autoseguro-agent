# US-06 — Catálogo de skills e seleção híbrida

**Prioridade:** MUST · **Estimativa:** 3h · **Dia:** 2 · **Depende de:** US-01 · **Habilita:** US-07, US-08

## Contexto
Seus requisitos 29-31. `DISCOVERY.MD §5.3` *[medido]*: o dataset tem **0** menções a
carência, pro-rata, coberturas de plano superior, agravo, recusa e atendimento humano.
Ou seja: **não existe nada para imitar** — as regras são autorais por necessidade, o que
reforça manter cada uma num arquivo de texto versionado (req 31).

## Objetivo
Regras de negócio em markdown, catálogo curto sempre em contexto, corpos só quando selecionados.

## Escopo
`skills/*.md` com front-matter YAML (`ARCHITECTURE.MD §5.1`):
`id · name · activation · triggers · when_to_use · rules · priority`.

**8 skills** — 4 do seu prompt, 2 derivadas do `plans.json`, 2 de suporte:

| Skill | `activation` | Origem |
|---|---|---|
| `identity_and_scope` | `always_on` | suporte |
| `quote` | `model_selected` | seu prompt |
| `quote_failure` | **`event_triggered`** (`breaker_open`, `quote_retries_exhausted`) | seu prompt |
| `objection_handling` | `model_selected` | seu prompt |
| `handoff` | **`event_triggered`** (gate disparou) | seu prompt |
| **`underwriting_refusal`** | **`event_triggered`** (`422` recusa real) | **derivada — 30% dos leads** |
| **`coverage_explanation`** | `model_selected` | **derivada — carência/pro-rata: 0% do dataset** |
| `out_of_scope` | `model_selected` | seu prompt (regra 11) |

**Seleção híbrida (D-08).** Seu requisito 30 diz que o modelo seleciona; seu requisito 17 diz
que o código garante. Os dois convivem assim: `always_on` e `event_triggered` são decididos
por **código** e o modelo não tem voto. Se o breaker está aberto, `quote_failure` **entra**.
`model_selected` é escolhido pela intenção, com o catálogo como menu.

## Critérios de aceitação
- [ ] `available_skills` é montado só do front-matter, sem ler nenhum corpo
- [ ] Só os corpos selecionados entram no prompt (asserção no texto final)
- [ ] `breaker_open` ⇒ `quote_failure` presente **mesmo** que o modelo tenha escolhido só `quote`
- [ ] `Refused(kind="idade")` ⇒ `underwriting_refusal` presente e `quote` ausente
- [ ] Adicionar um `.md` novo aparece no catálogo **sem tocar em código Python**
- [ ] `grep -rE 'desconto|franquia|carência|R\$' agent/**/*.py` ⇒ 0 regra comercial em código (só nos gates, como vocabulário)
- [ ] Front-matter inválido falha no boot com mensagem clara, não silenciosamente
- [ ] `rules` de cada skill referencia ids BR-xx existentes

## Notas
Anti-overengineering: sem embeddings, sem vector store, sem router treinado. 8 arquivos e um
`if`. O catálogo inteiro cabe em poucas centenas de tokens.
