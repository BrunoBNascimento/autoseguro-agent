# Relatório do dataset — `conversations.parquet`

Gerado por `scripts/analyze_dataset.py --ref-date 2026-09-10`. Determinístico: os números
abaixo são reproduzíveis por quem avalia. A data de referência fixa a idade do veículo.

## 1. Volumetria

- 2500 conversas · 26470 mensagens · 10.59 msgs/conversa
- desfechos: {'em_negociacao': 757, 'ganho': 712, 'perdido': 538, 'sem_resposta': 493}
- papéis: {'lead': 16470, 'vendedor': 10000} · tipos: {'text': 24681, 'document': 774, 'image': 550, 'audio': 465}
- **timestamps não monótonos: 2495 de 2500 (99.8%)** → ordenar sempre por `message_index`

## 2. O dataset NÃO é fonte de preço

Preço dito pelo vendedor × preço que a API devolve para o mesmo perfil (1749 conversas cotáveis):

- **0 de 1749 batem** (0.0%)
- razão API/dataset: mín 0.31x · mediana 1.45x · máx 7.89x
- o vendedor **subestima** em 70.8% dos casos
- o vendedor cotou preço para **751** leads que a API **recusa**

Conclusão: usar o dataset como few-shot de preço ensinaria o agente a errar. Ele serve para
análise de padrões e para casos de avaliação — nunca como fonte de verdade de preço (BR-01).

## 3. Elegibilidade de recusa (regras do `plans.json`)

- idade > 75: 280 (11.2%)
- veículo > 20 anos em 2026: 531 (21.2%)
- **qualquer: 751 (30.0%)** → skill `underwriting_refusal` (BR-12)
- CEP em região de agravo (prefixos 07/08/21/26/59): 895 (35.8%)

## 4. Anti-padrões do vendedor humano (o que o agente NÃO pode imitar)

- "Posso ajustar a franquia pra baixar a parcela": 757 conversas (30.3%) → BR-05
- "Consigo rever, posso te ligar?": 538 (21.5%) → BR-03/BR-07
- cobertura anunciada sempre como "colisao, roubo e furto": 2500 (100.0%); em 1677 delas o plano era Completo/Premium, que cobre mais → BR-06

## 5. PII

- mensagens com ao menos uma PII: 4718 de 26470 (17.8%)
- ocorrências por entidade (mensagens): {'cpf': 2500, 'cep': 2500, 'email': 1379, 'telefone': 1379, 'placa': 839}
- conversas com a entidade no texto do lead: {'cpf': 2500, 'email': 1379, 'telefone': 1379, 'placa': 839}

## 6. Temas ausentes (0 = não existe exemplo para imitar; regras são autorais por necessidade)

- carência: 0
- pro-rata/proporcional: 0
- coberturas superiores (vidros/terceiros/carro reserva/assistência): 0
- agravo/região: 0
- handoff (atendente/humano/supervisor): 0
- injection (ignore/esqueça/system prompt): 0

## 7. Casos de avaliação gerados

`evals/cases/dataset_cases.json`: 24 casos, até 3 por estrato desfecho × elegibilidade de recusa (seed 42). Estratos: em_negociacao/cotável=507, em_negociacao/recusa=250, ganho/cotável=509, ganho/recusa=203, perdido/cotável=387, perdido/recusa=151, sem_resposta/cotável=346, sem_resposta/recusa=147.
Turnos do lead já sanitizados (CPF/e-mail/telefone/placa mascarados, CEP só prefixo).
