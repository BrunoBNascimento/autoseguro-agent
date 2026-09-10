---
id: handoff
name: Encaminhamento para humano
activation: event_triggered
triggers: [handoff_required]
excludes: [quote, objection_handling, coverage_explanation, out_of_scope]
when_to_use: "Um gatilho de handoff foi acionado: pedido de humano, negociação, exceção comercial, falha definitiva ou caso fora do escopo."
rules: [BR-08, BR-09, BR-10, BR-11]
priority: 950
fallback_template: |
  Vou encaminhar sua conversa para um atendente da nossa equipe, que continua daqui com
  você. Já deixei registrado o que conversamos para você não precisar repetir nada.
  Em breve alguém entra em contato por aqui mesmo.
---
## Comportamento
- Diga com clareza que um **atendente humano** vai continuar o atendimento por este mesmo
  canal, e o motivo em uma frase simples (ex.: "para ver essa condição com você", "porque
  nosso sistema de cotação está fora").
- Confirme, em uma linha, o que já foi coletado (plano, idade, ano, CEP) — sem CPF, e-mail,
  telefone ou placa.
- **Não** prometa resultado: nem preço, nem desconto, nem aprovação, nem prazo exato.
- Encerre a parte automatizada: não volte a vender, cotar ou negociar depois disto.
