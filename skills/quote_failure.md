---
id: quote_failure
name: Falha na cotação
activation: event_triggered
triggers: [quote_retries_exhausted, breaker_open]
excludes: [quote]
when_to_use: "A API de cotação falhou após as tentativas ou está temporariamente fora; não há resultado para apresentar."
rules: [BR-02, BR-10]
priority: 900
fallback_template: |
  Nosso sistema de cotação está instável neste momento e não consegui gerar sua cotação.
  Não quero te passar um valor que não seja o oficial. Posso tentar de novo em alguns
  instantes ou, se preferir, já encaminho para um atendente da equipe continuar com você.
  O que prefere?
---
## Comportamento
- **Nunca** estimar, arredondar, dar faixa de preço ou repetir preço de conversa anterior.
  Sem cotação bem-sucedida não existe número para citar.
- Reconheça a falha de forma direta e honesta, sem jargão técnico e sem culpar o lead.
- Ofereça **uma** nova tentativa OU encaminhamento para um atendente humano, deixando a
  escolha com o lead.
- Se esta é a **segunda** vez que a cotação falha nesta conversa, não ofereça terceira
  tentativa: encaminhe para um atendente (handoff).
- Você pode aproveitar para confirmar os dados já coletados, para que a próxima tentativa
  (sua ou do atendente) seja rápida.
