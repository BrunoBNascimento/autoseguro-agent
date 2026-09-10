# Execução completa — cenário `degraded`

- data: 2026-09-10T13:36:31+00:00
- conversa: `conv_1ae34d648e0f`
- LLM: modelo determinístico (sem chave)
- cotação: FakeQuoteTransport com 503 em toda chamada (equivale a QUOTE_FAILURE_RATE=1.0)
- trace completo: `degraded-trace.jsonl` (um evento por linha, já sanitizado)

Mensagens do lead aparecem aqui já sanitizadas (mesma máscara que o modelo recebeu).

**lead:** Boa tarde, quero uma cotacao

**agente:** Oi! Vou te ajudar com a cotação. Qual plano você quer cotar: Essencial (colisão, roubo, furto), Completo (colisão, roubo, furto, danos a terceiros, vidros) ou Premium (colisão, roubo, furto, danos a terceiros, vidros, carro reserva, assistência 24h)?

<sub>status=`answered` · skills=['identity_and_scope', 'quote'] · regras=['BR-01', 'BR-02', 'BR-06', 'BR-13', 'BR-14'] · breaker=closed</sub>

**lead:** completo, tenho 35 anos, onix 2022, cep 01***-***

**agente:** Nosso sistema de cotação está instável agora e não consegui gerar sua cotação. Não quero te passar um valor que não seja o oficial. Quer que eu tente de novo em instantes ou prefere que um atendente continue com você?

<sub>status=`degraded` · skills=['identity_and_scope', 'quote_failure'] · regras=['BR-01', 'BR-02', 'BR-06', 'BR-10'] · breaker=closed</sub>

**lead:** tenta de novo por favor

**agente:** Vou encaminhar sua conversa para um atendente da nossa equipe (cotação falhou definitivamente), que continua daqui com você por este mesmo canal. Já deixei registrado o que conversamos para você não precisar repetir nada.

<sub>status=`handoff` · skills=['identity_and_scope', 'handoff', 'quote_failure'] · regras=['BR-01', 'BR-02', 'BR-06', 'BR-08', 'BR-09', 'BR-10', 'BR-11'] · breaker=open · handoff=BR-10</sub>

## Resumo do trace

- 37 eventos · 5 chamadas à /quote: error/503@0ms, error/503@0ms, error/503@0ms, error/503@0ms, error/503@0ms
- gates: 15 verificações, 0 bloqueios
