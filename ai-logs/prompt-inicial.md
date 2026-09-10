## breve descrição do objetivo

Vamos montar um agente, os requisitos desse agent, dataset para testes de evaluation harness e testes no geral estão nesse repositório:

* https://github.com/namastexlabs/namastex-fde-challenge

nossa missão é avaliar o repositório e cumprir todos os requisitos abaixo.

## requisitos técnicos

* circuit breaker na chamada da tool de cotação pra evitar degradar o serviço e o downstream
* retry com backoff pra falhas transitórias
* não realizar retry em erros de entrada ou autorização tipo 400 401 403 e 422, avaliar separado casos tipo 429
* definir timeout pras chamadas externas
* fazer uma etapa de detecção/classificação de prompt injection antes da execução do agente
* inputs suspeitos não podem conseguir alterar system prompts regras de negócio permissões ou comportamento das tools
* regras críticas de segurança e negócio precisam estar garantidas também por código/tools e não só pela detecção de prompt injection
* observabilidade das conversas e chamadas de tools
* salvar trace com pelo menos:
  * conversation/message id
  * tool chamada
  * input sanitizado
  * resultado/status
  * latência
  * erro quando houver
  * skills/regras utilizadas

* avaliar langwatch ou solução equivalente pra tracing/evals
* criar um catálogo de `available_skills` com descrições curtas das capacidades/regras disponíveis
* o modelo deve selecionar as skills relevantes baseado na intenção da conversa e só essas regras entram no contexto
* manter implementação de skills simples, podendo ser arquivo de texto/config pra evitar regra comercial espalhada no código
* conversas podem chegar em raw mas antes de persistência logs ou avaliação precisam passar por sanitização e remoção de pii
* não remover insultos ou conteúdo relevante da conversa durante sanitização, só dados sensíveis
* usar o dataset fornecido pra análise e criação de casos de avaliação, não como fonte de verdade de preço
* usar python como linguagem principal
* evitar banco de dados sem necessidade real, se precisar de persistência avaliar algo simples primeiro


## stack

* Python + Langchain
* Next.JS no frontend
* Docker para subir tudo em apenas um comando simples


fluxo conceitual

```text
user_input
  -> prompt injection / safety check
  -> available skills
  -> skill selection
  -> selected business skills
  -> model
  -> tool calling
  -> tool result
  -> model
  -> response ou handoff
```

exemplos iniciais de skills

```text
quote
- coleta dados necessários e realiza cotação

quote_failure
- define o comportamento quando a api de cotação está indisponível

objection_handling
- define como tratar objeções comerciais

handoff
- define quando encaminhar o atendimento pra um humano
```

as business skills devem poder definir coisas tipo

* o que fazer quando a api de cotação estiver indisponível
* como tratar objeções
* quando realizar handoff

## regras de negócio

* a api de cotação é a única fonte de verdade para preços
* sem uma cotação bem sucedida o agente não pode informar ou estimar preço
* o agente não possui autoridade pra

  * alterar preços
  * conceder descontos
  * criar condições comerciais
  * inventar benefícios ou coberturas
* ao receber uma objeção o agente deve tentar entender o motivo e responder usando só informações conhecidas sobre o produto
* o objetivo ao tratar objeções é demonstrar valor e não negociar preço
* quando a situação exigir negociação exceção comercial ou informação que o agente não possui fazer handoff pra atendimento humano
* também fazer handoff quando

  * o usuário pedir atendimento humano
  * a cotação falhar definitivamente
  * o caso estiver fora do escopo ou das regras disponíveis

## objetivo do discovery

usar o repositório do challenge e os pontos acima pra

1. identificar os requisitos explícitos e implícitos do desafio
2. validar quais dessas ideias realmente fazem sentido pro escopo
3. evitar overengineering pra um challenge de 3 dias
4. propor uma arquitetura mínima
5. definir um plano de implementação priorizado
6. separar claramente

   * must-have
   * nice-to-have
   * coisas que não valem implementar no challenge

não implementar nada ainda

primeiro

* fazer o discovery completo do repositório
* confrontar essas ideias com o que o challenge realmente pede
* identificar riscos e gaps
* propor uma arquitetura mínima
* produzir um implementation plan priorizado

separar uma pasta de plano de implementação em ai_logs, onde vamos salvar os logs de ia com a seguinte estrutura:

* DISCOVERY.MD
* ARCHITECTURE.MD
* tasks

   * US-01-SUBJECT.MD

* claude_logs

insira HITL como wizard para me perguntar eventuais duvidas.

detalhe: esse projeto está no workspace para aproveitar o devos e skills adjacentes, mas ele não pertecen ao contexto dos outros projetos.