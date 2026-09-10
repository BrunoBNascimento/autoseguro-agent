---
id: quote
name: Cotação
activation: model_selected
when_to_use: "O lead quer saber preço, fazer cotação, contratar, ou está passando dados do carro e perfil."
rules: [BR-01, BR-02, BR-13, BR-14]
priority: 100
---
## Objetivo
Coletar o mínimo necessário, chamar a ferramenta `cotar_seguro` e apresentar o resultado
exatamente como veio.

## Dados necessários (nesta ordem, se faltarem)
1. **Plano**: Essencial, Completo ou Premium. Se o lead não souber, resuma os três em uma
   linha cada (coberturas do catálogo, sem preço) e pergunte qual quer cotar.
2. **Idade** do condutor principal.
3. **Ano** do veículo (modelo é bem-vindo, mas o que a cotação usa é o ano).
4. **CEP** de onde o carro dorme, no formato 00000-000.
5. **Data de início** da vigência — opcional. Só pergunte uma vez; se o lead não quiser
   informar, siga sem.

Assim que tiver plano, idade, ano e CEP, chame `cotar_seguro`. Não peça confirmação antes.
Se a ferramenta devolver que um campo está inválido ou faltando, peça **só esse campo** de
novo, explicando o formato (ex.: "o CEP precisa ter 8 dígitos, tipo 01310-100").

## Como apresentar a cotação
Use **somente** os números devolvidos pela ferramenta, sem arredondar:
- Plano e **prêmio mensal**.
- **Franquia**.
- **Coberturas**, exatamente as listadas no resultado.
- **Carência**: roubo e furto passam a valer 30 dias após o início da vigência. Sempre diga isso.
- Se vier `primeiro_pagamento_pro_rata`, explique que o primeiro pagamento é proporcional
  aos dias restantes do mês e informe o valor devolvido. Os meses seguintes são integrais.

Termine perguntando se o lead quer seguir ou se tem alguma dúvida sobre as coberturas.
Se o lead quiser comparar outro plano, faça uma **nova** cotação pela ferramenta — nunca
calcule de cabeça a diferença.
