# US-08 — Gates de saída (as garantias em código)

**Prioridade:** MUST — **é o coração do projeto** · **Estimativa:** 3,5h · **Dia:** 2
**Depende de:** US-07 · **Habilita:** US-10, US-12

## Contexto
Seu requisito 17: *"regras críticas de segurança e negócio precisam estar garantidas também
por código/tools e não só pela detecção de prompt injection"*.
E o critério E-06/E-07 do challenge: não inventar preço quando a infra cai.

**Se um requisito de segurança só existe no prompt, ele não está implementado.** Esta US é o
que transforma as regras de negócio em invariantes do sistema.

## Objetivo
Quatro funções puras `(draft, state) -> Verdict` que rodam **sobre o texto que o modelo
produziu**, antes de o lead ver.

## Escopo
| Gate | Regra |
|---|---|
| **`price_gate`** | Extrai toda expressão monetária (`R$ 209,90`, `209,90`, `por 209`, numerais escritos pt-BR). Conjunto permitido = `{premio_mensal, franquia, valor_primeiro_pagamento}` da **última cotação `200` desta conversa**. Valor fora do conjunto ⇒ BLOCK. **Sem cotação `200` ⇒ qualquer valor monetário ⇒ BLOCK** | BR-01, BR-02, BR-03 |
| **`coverage_gate`** | Coberturas citadas ⊆ `quote.coberturas`. Vocabulário controlado de 7 termos | BR-06, BR-05 |
| **`authority_gate`** | Compromisso fora de autoridade (`desconto`, `consigo baixar`, `posso ajustar a franquia`, `faço por`, `condição especial`) ⇒ BLOCK **e força handoff** | BR-03, BR-04, BR-05, BR-08 |
| **`handoff_gate`** | Se algum gatilho de handoff está ativo, garante que a resposta seja de handoff em vez de continuar vendendo | BR-08..BR-11 |

- **Ação no BLOCK:** 1 regeneração com instrução corretiva citando o id da regra. Se falhar de
  novo ⇒ **template** da skill correspondente. O texto violador **nunca** é entregue.
- Cada decisão vira evento `guard` no trace com `rule_id` + `verdict`.
- **Zero dependência de LLM** ⇒ testável em milissegundos, no CI, sem chave.

## Critérios de aceitação
- [ ] Sem cotação `200`, rascunho `"fica uns R$ 200"` ⇒ BLOCK com `rules_applied:["BR-02"]`
- [ ] Com cotação `200` de `209.90`, rascunho `"R$ 189,90"` ⇒ BLOCK `BR-03`
- [ ] Com cotação `200` de `209.90`, rascunho `"R$ 209,90"` ⇒ PASS
- [ ] `franquia` e `valor_primeiro_pagamento` da cotação passam (não são "preço inventado")
- [ ] Plano `essencial` + rascunho citando `vidros` ⇒ BLOCK `BR-06` (**o vendedor humano erra isso em 67% das conversas**)
- [ ] `"consigo te dar 10% de desconto"` ⇒ BLOCK `BR-04` **e** handoff forçado
- [ ] `"posso ajustar a franquia pra baixar a parcela"` ⇒ BLOCK `BR-05` (**anti-padrão presente em 30% do dataset**)
- [ ] `"duzentos e nove reais"` sem cotação ⇒ BLOCK (numerais escritos — R-05)
- [ ] Regeneração acontece **no máximo 1 vez**; a 2ª falha cai no template
- [ ] Nenhum gate importa `langchain` nem faz chamada de rede
- [ ] Suíte de gates roda em < 1s

## Riscos
R-05: extração por regex é evadível. Numerais escritos pt-BR cobrem o caso óbvio; o resíduo
fica **documentado honestamente** no README em vez de escondido.
