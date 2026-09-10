# DISCOVERY — Desafio FDE Namastex (agente de cotação AutoSeguro)

**Data:** 2026-09-10
**Fonte primária:** `https://github.com/namastexlabs/namastex-fde-challenge` @ `52a006c`
**Clone local:** `agent/reference/namastex-fde-challenge/` (LOCAL-FIRST: todo o discovery foi feito em disco, não via API)
**Insumo secundário:** `agent/prompt-inicial.md` (36 requisitos técnicos/negócio definidos por você)

> Este documento é o resultado do confronto entre **o que o challenge realmente pede** e
> **as ideias do prompt inicial**. Não há implementação aqui. Números marcados como
> *[medido]* foram calculados executando código sobre os artefatos do repo, não estimados.

---

## 1. O que o repositório realmente contém

Repo minúsculo (668 KB, 14 arquivos versionados). Nada de esqueleto de agente — o
candidato começa do zero.

| Caminho | O que é | Relevância |
|---|---|---|
| `README.md` | Brief do desafio | Fonte dos requisitos explícitos |
| `quote-service/app/main.py` | FastAPI: `/health`, `/planos`, `POST /quote` | **A instabilidade vive aqui** |
| `quote-service/app/quote_logic.py` | Regras de cálculo (faixa etária, idade do veículo, região, carência, pro-rata) | **As regras de negócio reais** |
| `quote-service/data/plans.json` | 3 planos + tabela de regras | Única fonte de verdade de preço |
| `dataset/conversations.parquet` | 26.470 mensagens / 2.500 conversas *[medido]* | Análise e evals — **não** fonte de preço |
| `dataset/DICIONARIO.md` | Esquema do dataset | Contém 1 imprecisão (ver §5.4) |
| `scripts/generate_dataset.py` | Gerador procedural do dataset | **Achado-chave: revela o ground truth** |
| `docker-compose.yml` | 1 serviço (`quote-api`), porta 8000 | Base do nosso compose |

### 1.1 O gerador do dataset é reproduzível bit-a-bit *[medido]*

`gen_conversation(0, seed=42)` reproduz `dataset/sample.jsonl` **campo por campo, exato**.
Isso foi verificado antes de qualquer conclusão. Consequência prática: consegui calcular
estatísticas exatas do dataset **sem pandas/pyarrow instalados**, e — mais importante —
consigo gerar casos de avaliação rotulados com ground truth conhecido.

---

## 2. Requisitos EXPLÍCITOS do challenge

Do `README.md`, seção "O que entregar" e "Como a gente vai olhar":

| # | Requisito | Fonte |
|---|---|---|
| E-01 | Agente que atende um lead ponta a ponta: conversa → qualifica → cota → decide | "O que entregar" 1 |
| E-02 | Repositório **público** no GitHub | "O que entregar" 2 |
| E-03 | README com **como rodar** e **as decisões tomadas e por quê** | "O que entregar" 3 |
| E-04 | **Log de uma execução completa** (uma conversa do início ao fim, com a cotação saindo) | "O que entregar" 4 |
| E-05 | Conversas com IAs exportadas na pasta **`ai-logs/`** | "Transparência" (obrigatório) |
| E-06 | Funciona ponta a ponta no caminho feliz | "Como a gente vai olhar" |
| E-07 | **O que faz quando a `/quote` falha** — *"esse é o ponto que mais separa"* | idem |
| E-08 | Critério de passar pro humano **explícito e defensável** | idem |
| E-09 | **Rastreabilidade**: "cada mensagem/cotação, com id e status" | idem |
| E-10 | Cuidado com dados sensíveis ("o histórico tem informação pessoal") | idem |
| E-11 | Qualidade: outro engenheiro entende suas decisões | idem |
| E-12 | Avisar quando começar | "Entrega" |

Prazo: **~3 dias de relógio**. Uso de AI coding tools é **esperado** ("isso é a régua aqui").

---

## 3. Requisitos IMPLÍCITOS (só aparecem lendo o código)

Estes não estão no README. Foram extraídos de `quote_logic.py` + `plans.json`. O README
sinaliza a pegadinha: *"`GET /planos` — tabela de planos **e as regras de cotação** (leia com atenção)"*.

| # | Requisito implícito | Evidência |
|---|---|---|
| I-01 | **Recusa de subscrição é um desfecho de primeira classe, não erro.** Idade > 75 e veículo > 20 anos retornam **422 `cotacao_recusada`** | `plans.json: faixa_etaria[4].recusar`, `idade_veiculo[3].recusar` |
| I-02 | **Carência de 30 dias** para `roubo` e `furto`, contada da vigência — vem no payload da cotação e precisa ser comunicada | `plans.json: regras.carencia`; `cotar()` retorna `carencia` |
| I-03 | **Pro-rata do primeiro mês** quando a vigência não começa no dia 1º | `plans.json: entrada_meio_mes`; `_pro_rata_primeiro_mes()` |
| I-04 | **Agravo de 1,30x** por CEP de alto risco (prefixos `07 08 21 26 59`) | `plans.json: regiao_cep` |
| I-05 | Coberturas **variam por plano** (3 / 5 / 7 itens) — não são iguais | `plans.json: planos[*].coberturas` |
| I-06 | Idade do veículo é `ano_atual - ano_veiculo` (diferença de ano-calendário, não idade exata) | `_idade_veiculo_mult()` |
| I-07 | **`/quote` é idempotente** (cálculo puro, sem efeito colateral) → retry é seguro sem chave de idempotência | `cotar()` não escreve nada |
| I-08 | **A falha é sorteada ANTES da validação** → um 422 legítimo pode chegar como 503 | `main.py:53-60` roda antes do `try: cotar()` |
| I-09 | `/health` é sempre estável → **não serve** como sinal de saúde do `/quote` | docstring: "health check (sempre estavel)" |
| I-10 | Não existe autenticação, nem 401/403, nem 429 no mock | `main.py` inteiro |

> **I-08 é sutil e importante.** Você não pode concluir "recusado" a partir de um 5xx, nem
> concluir "indisponível" sem esgotar retries. E o mesmo payload pode dar 503 na 1ª tentativa
> e 422 na 2ª. O agente precisa de uma máquina de estados que trate os dois desfechos sem
> se contradizer com o lead.

### 3.1 Validação empírica — subi o serviço e medi *[medido]*

`uv run uvicorn app.main:app --port 8000`, **250 chamadas** com timeout de 3s, payload fixo
(`completo, 35 anos, 2022, CEP 01310-100, início 2026-07-15`):

| Resultado | Ocorrências | % |
|---|---|---|
| `200` | 174 | **69,6%** |
| `502` | 19 | 7,6% |
| `503` | 17 | 6,8% |
| `500` | 8 | 3,2% |
| `TIMEOUT` (caminho lento de 8s) | 32 | 12,8% |
| **p_falha_por_tentativa medido** | | **0,304** (previsto 0,30 ✓) |

**Latência do caminho de sucesso: p50 = 0,9 ms, máximo = 25,5 ms** (n=174).

> Esse último número muda uma decisão. O serviço, quando responde, responde em **menos de
> 1 ms**. E como o caminho lento é um `sleep(8)` fixo, **qualquer timeout entre ~100 ms e 8 s
> classifica exatamente igual** — o valor do timeout só decide *quanto tempo desperdiçamos
> no caminho lento*. Logo: minimize. Timeout de **1,5 s** dá ~60x de folga sobre o pior
> caso observado e derruba o pior caso de parede de uma cotação de **10,2 s para 5,7 s**,
> sem trocar nada de confiabilidade. Ver ARCHITECTURE §6.

Confirmado no payload de sucesso: `carencia` (roubo/furto, 30 dias) e
`primeiro_pagamento_pro_rata` (`2026-07-15` → 17 de 31 dias → **R$ 115,11**) vêm na resposta.
E `CEP 07123-456` → prêmio **272,87** vs `01310-100` → **209,90** (agravo 1,30x confirmado).

### 3.2 Taxonomia de erro real — corrigida pela medição

O status HTTP **não basta**. É preciso ler o corpo.

| Status | Corpo | Natureza | Retry? |
|---|---|---|---|
| 500 / 502 / 503 | `{"error":"upstream_unavailable"}` | Transitória (sorteada) | **Sim** |
| timeout (8s) | — | Transitória (sorteada) | **Sim** |
| **422** | `{"error":"cotacao_recusada","motivo":"Idade acima do limite..."}` | **Recusa de subscrição** — desfecho de negócio | **Nunca** |
| **422** | `{"error":"cotacao_recusada","motivo":"Plano 'turbo' inexistente..."}` | **Bug NOSSO** disfarçado de recusa | **Nunca** |
| **422** | `{"detail":[{"type":"int_parsing",...}]}` | **Bug NOSSO** (schema Pydantic) | **Nunca** |
| **400** | `{"error":"payload_invalido","detalhe":"Invalid isoformat string: '15/07/2026'"}` | **Bug NOSSO** (data fora do ISO) | **Nunca** |
| 401 / 403 / 429 | *não existem no mock* | — | Política por realismo |

### 3.3 Três armadilhas que só aparecem chamando o serviço *[medido]*

**(a) `422` tem TRÊS significados diferentes.** Mapear `422 → "recusamos seu perfil"` faria o
agente dizer ao lead que ele foi recusado quando, na verdade, **nós** mandamos um `plano_id`
com typo. O cliente precisa discriminar pelo corpo: `error == "cotacao_recusada"` **e** o
`motivo` falando de idade/veículo é recusa real; `motivo` falando de plano inexistente, ou
um corpo com `detail`, é defeito nosso — que deve virar erro interno e handoff, nunca uma
recusa comunicada ao lead.

**(b) CEP inválido NÃO dá erro — ele sub-cota silenciosamente.** `cep: "abc"` retorna
**`200`** com `m_regiao = 1.0`. Ou seja: um CEP mal extraído da conversa produz um preço
**válido, confiante e 30% mais barato** para os 35,8% de leads em região de agravo, sem
nenhum sinal de erro. É a pior classe de falha do desafio inteiro — silenciosa e com
consequência comercial.
→ **O CEP tem de ser validado por nós (`^\d{5}-?\d{3}$`) antes da chamada**, e um CEP que
não casa vira nova pergunta ao lead, não uma cotação. (`07123456` sem hífen funciona: o
`_regiao_mult` faz `replace("-","")[:2]`.)

**(c) `data_inicio` em formato brasileiro derruba a chamada.** `"15/07/2026"` → **`400`**
(`Invalid isoformat string`). Num WhatsApp o lead vai dizer "dia 15/07" — então a
normalização para ISO é obrigatória **antes** da tool. Curiosidade: `data_inicio: ""`
retorna `200` **sem pro-rata** (o `if di:` é falsy), silenciosamente diferente de omitir.

Coisas que são toleradas sem erro: `idade: "35"` (string, Pydantic coage),
`plano_id: "COMPLETO"` (o `cotar()` faz `.lower()`), `cep` sem hífen.

Configuração default (`docker-compose.yml`): `QUOTE_FAILURE_RATE=0.20`,
`QUOTE_SLOW_RATE=0.10`, `QUOTE_SLOW_SECONDS=8`, `QUOTE_SEED` para reproduzir.
Como `roll` é sorteado **uma vez**, falha e lentidão são mutuamente exclusivas.

---

## 4. Matemática da instabilidade — a decisão de resiliência é calculável *[medido]*

Este é o requisito E-07 ("o ponto que mais separa"). Ele não deve ser resolvido por intuição.

Com timeout **abaixo** de 8s, lentidão conta como falha → `p_falha_por_tentativa = 0,30`.
Com timeout **acima** de 8s, `p = 0,20` mas você paga 8s de latência em 1 de cada 10 chamadas.

| Tentativas | Sucesso (p=0,30) | Falha definitiva |
|---|---|---|
| 1 | 70,00% | 30,00% |
| 2 | 91,00% | 9,00% |
| **3** | **97,30%** | **2,70%** |
| 4 | 99,19% | 0,81% |

**Decisão:** timeout **1,5s** (justificado pela medição em §3.1) + 3 tentativas. Falha rápido
em vez de esperar 8s, e chega a 97,3% de sucesso. Isso significa que o caminho de degradação (skill `quote_failure`) é exercitado em
~1 de cada 37 cotações — frequente o suficiente para ser real, raro o suficiente para não
dominar a experiência.

### 4.1 O circuit breaker mal calibrado é pior que a falha *[medido]*

Este é o achado mais contraintuitivo do discovery. Probabilidade de o breaker abrir **com o
serviço operando normalmente** (ou seja, falso positivo auto-infligido):

| Política de breaker | P(abrir) com p=0,30 | Veredito |
|---|---|---|
| Janela deslizante 30% em 10 chamadas | **61,7%** | Catastrófico |
| Janela deslizante 50% em 10 chamadas | **15,0%** | Inaceitável |
| Janela deslizante 50% em 20 chamadas | 4,8% | Ainda ruim |
| **5 falhas consecutivas** | **0,24%** | **Escolhido** |
| 3 falhas consecutivas | 2,70% | Aceitável, mas ruidoso |

Um breaker de "50% em 10" — o default de metade dos tutoriais — derrubaria nosso próprio
serviço em 15% das janelas **sem que a `/quote` estivesse pior do que o normal**. Já um
breaker por **falhas consecutivas** distingue ruído de queda real: durante uma indisponibilidade
verdadeira (100% de falha) ele abre em menos de 2 cotações lógicas.

**Isso valida seu requisito de circuit breaker, mas rejeita a calibragem óbvia.**

---

## 5. O dataset: o que ele é e o que ele NÃO é *[medido]*

2.500 conversas, 26.470 mensagens, 10,59 msgs/conversa (min 8, max 14).
Desfechos: `em_negociacao` 757 · `ganho` 712 · `perdido` 538 · `sem_resposta` 493.
Papéis: 16.470 mensagens do lead vs 10.000 do vendedor → **o lead manda rajadas**, várias
mensagens seguidas sem turno do vendedor. O agente precisa lidar com isso.

### 5.1 O dataset NÃO é fonte de verdade de preço — prova numérica

Comparei o preço que o vendedor anuncia em cada conversa com o preço que a `/quote` calcularia
para aquele mesmo perfil (idade + ano do veículo + CEP), usando o `quote_logic.py` real:

- **0 de 1.749 conversas cotáveis batem** com o preço da API. **Zero. 0,00%.**
- Razão `preço_real / preço_dataset`: mínimo **0,31x**, mediana **1,45x**, máximo **7,89x**.
- Em 71% dos casos o dataset **subestima** o preço real.
- Os preços do dataset saem de uma lista fixa de 8 valores
  (`129,90 · 159,90 · 189,90 · 219,90 · 259,90 · 299,90 · 349,90 · 389,90`) —
  `random.choice`, sem nenhuma relação com `base_mensal × multiplicadores`.

Seu requisito *"usar o dataset para análise e criação de casos de avaliação, não como fonte
de verdade de preço"* está **confirmado com números**. Vale para o README da entrega.

### 5.2 O vendedor humano do dataset viola as regras de negócio que você definiu

Este é o achado mais perigoso para quem for de few-shot ingênuo:

| Anti-padrão no dataset | Ocorrência | Regra violada |
|---|---|---|
| `"Posso ajustar a franquia pra baixar a parcela"` | **757 conversas (30%)** | Criar condições comerciais |
| `"Entendo! Consigo rever, posso te ligar?"` | **538 conversas (22%)** | Negociar preço |
| `"Cobre colisao, roubo e furto"` anunciado para **qualquer** plano | **2.500 (100%)**, das quais **1.677 (67%)** são Completo/Premium | Descrever cobertura errada |
| Preço anunciado para perfil que a API **recusa** | **751 conversas (30%)** | Cotar sem cotação válida |

> **Consequência de arquitetura:** o dataset é **material de anti-padrão**, não de few-shot.
> Fazer RAG ou fine-tune sobre ele ensinaria o agente a dar desconto, mexer na franquia,
> errar cobertura e cotar perfil recusado. Ele entra no projeto como **fonte de casos de
> teste e de linguagem/tom**, com no máximo 3-5 exemplos **curados manualmente**.

### 5.3 O que o dataset não tem — e portanto precisamos autorar *[medido]*

Busca literal em todas as 26.470 mensagens:

| Tema | Ocorrências |
|---|---|
| `carencia` / `carência` | **0** |
| `pro-rata` / `proporcional` | **0** |
| `vidros`, `terceiros`, `carro reserva`, `assistencia 24h` | **0** |
| `agravo` / `cep de alto risco` | **0** |
| `atendente` / `humano` / `supervisor` | **0** |
| `recusa` / `recusado` | **0** |
| `desconto` / `cupom` | **0** |
| `ignore` / `esqueca` / `system prompt` (injection) | **0** |

Duas conclusões:
1. **Nenhum exemplo de handoff existe no dataset.** O critério de E-08 é 100% autoral — não
   há nada para imitar. Isso reforça que ele precisa ser escrito como regra, não aprendido.
2. **As suítes de injection, de insulto-preservado e de recusa/carência são autorais.** Não
   dá para "extrair do dataset" o que não está lá.

Do lado positivo: **comunicar carência, pro-rata e cobertura correta por plano é um
diferenciador imediato**, porque nenhum dos 2.500 atendimentos humanos faz isso.

### 5.4 Duas armadilhas de dados

**(a) Timestamps não são monótonos — 2.495 de 2.500 conversas (99,8%)** *[medido]*.
O gerador faz `ts = base_ts + timedelta(minutes=idx * random.randint(1,9))`, então a mensagem
7 pode ter horário anterior à mensagem 6. Ordenar por `timestamp` embaralha a conversa.
**Ordenar sempre por `message_index`**, como o dicionário manda.

**(b) O `DICIONARIO.md` exagera a variedade de formato.** Ele afirma que a PII aparece
"em formatos variados". Na prática o gerador emite **um formato fixo por entidade**:
CPF `###.###.###-##` (com dígitos verificadores válidos), CEP `#####-###`,
telefone `+55 DD 9####-####`, placa Mercosul `ABC1D23`. O que varia é a **ordem** dos campos
(6 permutações) e a **capitalização** do rótulo (`Cpf` / `cpf`, `Cep` / `cep`), por causa de
um `.capitalize()` na linha 113 do gerador.
→ Regex case-insensitive resolve ~100% **neste** dataset. Mas o mundo real é mais sujo, então
a suíte de PII deve incluir variantes sem pontuação (`38908386343`, `(11) 98765-4321`).

### 5.5 Distribuições que importam para os evals *[medido]*

| Dimensão | Distribuição |
|---|---|
| Faixa etária | 30-59: 1.133 · 60-75: 655 · **76+ (RECUSA): 280 (11,2%)** · 18-24: 236 · 25-29: 196 |
| Idade do veículo | 11-20a: 1.062 · 6-10a: 504 · 0-5a: 403 · **21+ (RECUSA): 531 (21,2%)** |
| **Qualquer recusa** | **751 conversas — 30,0%** |
| CEP de alto risco | 895 de 2.500 — **35,8%** (agravo 1,30x) |
| Tipos de mídia sem transcrição | 774 documento · 550 imagem · 465 áudio = 1.789 (6,8%) |

**30% dos leads são recusáveis.** Isso torna a skill de recusa de subscrição (I-01) tão
importante quanto a de falha de cotação — e ela não está na sua lista de skills iniciais.

### 5.6 PII presente *[medido]*

| Entidade | Conversas | Necessária para cotar? |
|---|---|---|
| CPF | 2.500 (100%) | **Não** |
| CEP | 2.500 (100%) | **Sim** (agravo de região) |
| Idade | 2.500 (100%) | **Sim** (faixa etária) |
| E-mail | 1.379 (55%) | **Não** |
| Telefone | 1.379 (55%) | **Não** |
| Placa | 839 (34%) | **Não** |

4.718 das 26.470 mensagens (17,8%) contêm ao menos uma PII.

> **Decisão que cai de graça daqui:** a `/quote` aceita exatamente 5 campos
> (`plano_id, idade, veiculo_ano, cep, data_inicio`). **CPF, e-mail, telefone e placa nunca
> são necessários** em nenhum ponto do fluxo. Então podemos mascará-los **na entrada, antes
> do modelo ver** — e não só antes de persistir. O LLM nunca recebe o que não precisa, o que
> elimina a classe inteira de vazamento por prompt, por trace e por export.

---

## 6. Confronto: suas 36 ideias × o que o challenge pede

Legenda: **MUST** = entra · **SHOULD** = entra se sobrar tempo · **WON'T** = não vale no challenge.

| Sua ideia (prompt-inicial) | Veredito | Justificativa |
|---|---|---|
| Circuit breaker na tool de cotação | **MUST** | Pedido implicitamente por E-07. **Mas** calibrar por falhas consecutivas, não por janela (§4.1) |
| Retry com backoff | **MUST** | 3 tentativas → 97,3%. Núcleo de E-07 |
| Não retry em 400/401/403/422 | **MUST (parcial)** | 400 e 422 existem de verdade. **401/403 não existem** no mock — política escrita, testada só com fake |
| Avaliar 429 separado | **SHOULD** | Não existe no mock (I-10). Vale como política + 1 teste com fake. Não construir rate-limiter elaborado |
| Timeout em chamadas externas | **MUST** | 3s, calculado contra o `SLOW_SECONDS=8` |
| Detecção/classificação de prompt injection antes do agente | **MUST (enxuto)** | **Não é pedido pelo challenge.** É seu requisito. Vale como camada fina (heurística + 1 chamada barata); o esforço real vai para os gates em código |
| Input suspeito não altera system prompt / regras / tools | **MUST** | Garantido por **arquitetura** (prompt congelado, conteúdo do usuário sempre em `role: user` delimitado), não por detecção |
| Regras críticas garantidas por código/tools, não só por detecção | **MUST — é o coração do projeto** | Se você entregar só isso e o trace, já ataca E-06, E-07, E-08 e E-09. Ver ARCHITECTURE §3 |
| Observabilidade de conversas e tool calls | **MUST** | É literalmente E-09 |
| Trace com id/tool/input sanitizado/status/latência/erro/skills | **MUST** | Vira o schema em ARCHITECTURE §4 |
| Avaliar LangWatch ou equivalente | **MUST avaliar / SHOULD adotar** | Avaliação feita em §7. Veredito: JSONL próprio como fonte de verdade + LangWatch **cloud opcional** |
| Catálogo `available_skills` com descrições curtas | **MUST** | Barato e ataca E-08 e E-11 diretamente |
| Modelo seleciona skills pela intenção; só essas entram no contexto | **MUST (híbrido)** | Seleção 100% pelo modelo é frágil: `quote_failure` **precisa** entrar quando o breaker abre, independente da opinião do modelo. Ver ARCHITECTURE §5 |
| Skills como arquivo de texto/config | **MUST** | Markdown com front-matter. Zero regra comercial em código Python |
| Sanitização + remoção de PII antes de persistir/logar/avaliar | **MUST (mais forte)** | Vamos além: mascarar **na entrada**, antes do modelo (§5.6) |
| Não remover insultos nem conteúdo relevante | **MUST** | Sanitizador é **por entidade**, não moderador de conteúdo. Vira caso de teste explícito |
| Dataset para análise/evals, não como fonte de preço | **MUST** | Confirmado com números em §5.1 |
| Python como linguagem principal | **MUST** | Alinhado com o `quote-service` |
| Evitar banco sem necessidade real | **MUST** | JSONL append-only. SQLite (stdlib) só se o painel precisar de query |
| Python + LangChain | **MUST (com ressalva)** | Ver risco R-07 |
| Next.js no frontend | **MUST (escopado)** | **O challenge não pede frontend.** Você pediu. Entra como chat + painel de trace, porque o painel ataca E-09 e produz o E-04 de graça |
| Docker, tudo em um comando | **MUST** | 3 serviços, sem banco |
| Fluxo conceitual (injection → skills → modelo → tool → resposta/handoff) | **MUST** | Adotado como está, com 2 acréscimos: máscara de PII na entrada e **gate de saída** antes de responder |
| Skills `quote`, `quote_failure`, `objection_handling`, `handoff` | **MUST + 2** | Faltam `underwriting_refusal` (30% dos leads!) e `coverage_explanation` (carência/pro-rata: 0% do dataset) |
| Regras de negócio (14 itens) | **MUST** | Viram BR-01..BR-14 com id rastreável no trace. 3 delas (BR-12/13/14) foram **derivadas do código**, não do seu prompt |

### 6.1 Onde suas ideias vão além do challenge (e o que fazer)

Você especificou um sistema de produção. O challenge pede um protótipo defensável em 3 dias.
Três itens seus são **overengineering se levados ao limite**:

1. **Prompt injection como pipeline completo.** O challenge nunca menciona injection.
   → Camada fina (heurística + classificador barato), e o **esforço real nos gates de código**.
   Um gate de preço em Python vale mais que um classificador de 95% de acurácia.
2. **429 / 401 / 403.** Não existem no mock.
   → Política escrita + 1 teste com transporte fake cada. Zero infraestrutura nova.
3. **LangWatch.** Self-hosted são 7 serviços (§7).
   → Exportador opcional, desligado por default.

E dois itens **faltavam** na sua lista, ambos derivados do código:
4. **Recusa de subscrição** (30% dos leads) — precisa de skill própria.
5. **Carência e pro-rata** — vêm no payload da cotação e nenhum humano do dataset comunica.

---

## 7. Avaliação de LangWatch (requisito seu, item 28) — feita com fatos, não de memória

Verificado em 2026-09-10 contra `github.com/langwatch/langwatch` (Apache-2.0, 3.530 stars,
último push no mesmo dia) e a doc oficial de self-hosting.

**Self-hosted via Docker Compose** — `docs/self-hosting/deployment/docker-compose.mdx`:

- **7 serviços:** `app`, `workers`, `langwatch_nlp`, `langevals`, `postgres:16`, `redis:alpine`, `clickhouse`
- **Requisito de hardware declarado: 4 vCPU, 8 GB RAM, 20 GB disco**
- 3 segredos obrigatórios (`API_TOKEN_JWT_SECRET`, `CREDENTIALS_SECRET`, `NEXTAUTH_SECRET`)

**Cloud (tier grátis)** — `app.langwatch.ai`: 1 variável (`LANGWATCH_API_KEY`),
`langwatch.setup()`, e o callback do LangChain em `RunnableConfig(callbacks=[...])`. ~5 linhas.

| Opção | Custo de adoção | Veredito |
|---|---|---|
| LangWatch self-hosted no nosso compose | +7 serviços, +8 GB RAM, +3 segredos | **WON'T.** Contradiz "um comando simples" e "evitar banco sem necessidade real". Multiplicaria por ~8 o footprint de um desafio cujo requisito de trace (E-09) é um registro plano |
| LangWatch cloud (grátis) | ~5 linhas + 1 env var | **SHOULD.** Barato. **Mas** exige que a sanitização seja *upstream* do exportador, senão manda PII pra terceiro |
| **Trace JSONL próprio** | ~80 linhas, zero infra | **MUST — fonte de verdade.** Roda offline, o avaliador dá `cat` no arquivo, não precisa de conta, e alimenta o painel de trace |
| LangSmith / Langfuse | equivalentes ao LangWatch cloud | Considerados, mesma conclusão |

**Decisão:** trace JSONL append-only é a fonte de verdade. Exportador LangWatch cloud atrás
de flag, **desligado por default** (`LANGWATCH_API_KEY` ausente = no-op), alimentado **só com
payload já sanitizado**. Assim o requisito é cumprido, o avaliador consegue rodar o repo sem
cadastro, e ninguém vaza CPF para SaaS.

---

## 8. Riscos e gaps

| ID | Risco | Sev | Mitigação |
|---|---|---|---|
| **R-01** | **Ambiente incompleto.** `docker` **não instalado**; `pip3`, `uv` e `ensurepip` **ausentes** (`python3 -m venv` falha: "ensurepip is not available"). Sem isso não roda nem o `quote-service` | **Alta** | Aprovado por você: instalar `uv` via curl (sem sudo) + Docker via `sudo apt install docker.io`. **Bloqueio de Dia 1, US-01** |
| **R-02** | **3 dias × 36 requisitos.** Risco real de entregar tudo pela metade | **Alta** | Corte MUST/SHOULD/WON'T em §6 + linha de corte explícita no plano (ARCHITECTURE §8) |
| **R-03** | **Few-shot ingênuo no dataset envenena o agente** (30% ensinam a mexer na franquia, 100% erram cobertura) | **Alta** | Dataset só para evals e tom; máx. 3-5 exemplos curados à mão |
| **R-04** | **Breaker mal calibrado auto-degrada o serviço** (15% de falso positivo com 50%/10) | **Média** | Falhas consecutivas = 5, cooldown 30s, half-open 1 sonda (§4.1) |
| **R-05** | **Gate de preço por regex é evadível** ("duzentos e nove reais") | **Média** | Adicionar numerais escritos pt-BR ao detector; **documentar o resíduo honestamente** no README |
| **R-06** | **5xx mascara 422** (I-08): agente pode se contradizer com o lead | **Média** | Máquina de estados: só conclui "indisponível" após esgotar tentativas; 422 é autoritativo em qualquer tentativa |
| **R-07** | **LangChain esconde recursos atuais do provider** (structured outputs, `strict` em tools, params novos) e adiciona indireção que dificulta auditar o gate | **Média** | LangChain **só** para orquestração de mensagens e tool binding. Resiliência, sanitização, gates e trace ficam em Python puro, testáveis sem LLM |
| **R-08** | **Provider = OpenAI (sua escolha).** Perde o canal de *mid-conversation system message*; isolamento de contexto passa a depender de delimitadores + gates | **Média** | Aceito. Gates em código já são a garantia real (seu requisito 17). Model ID via env var — **confirmar o ID vigente no Dia 1**, não chutar |
| **R-09** | **Ordenar dataset por `timestamp` embaralha 99,8% das conversas** | **Média** | `message_index` é a única ordem válida. Vira asserção no script de análise |
| **R-10** | **`dt.date.today()` na regra de idade do veículo** → teste que passa hoje quebra em 01/01/2027 | Baixa | Congelar a data nos testes; nunca depender de `today()` nas asserções |
| **R-11** | **Repo público + `ai-logs` cru.** Você confirmou que já removeu os logs de outros projetos e autorizou publicar cru | Baixa (aceito) | Rede de segurança mecânica antes do push: `grep -riE 'CLIENTE_ANONIMIZADO\|TICKET-[0-9]\|JIRA_API_TOKEN\|ID_CLIENTE_ANONIMIZADO\|sk-\|gho_' ai-logs/`. Custa 5s |
| **R-12** | **Nome da pasta.** O challenge exige **`ai-logs/`** (hífen). Nosso plano está em `ai_logs/` (underscore) | Baixa | No repo de entrega a pasta se chama `ai-logs/`. Item de checklist na US-15 |
| **R-15** | **CEP inválido retorna `200` e sub-cota 30%** silenciosamente (§3.3b). Pior classe de falha: silenciosa e com consequência comercial | **Alta** | Validar CEP por regex **antes** da tool; CEP que não casa vira nova pergunta ao lead, nunca uma cotação |
| **R-16** | **`422` é ambíguo** (recusa real vs bug nosso, §3.3a) → agente pode "recusar" um lead por causa de um typo nosso | **Alta** | Discriminar pelo corpo (`error` + `motivo`), não pelo status. Bug nosso ⇒ erro interno + handoff, jamais recusa comunicada |
| **R-17** | **`data_inicio` em formato BR dá `400`** (§3.3c) e o lead vai escrever "15/07" | Média | Normalizar para ISO antes da tool; pré-validar os 5 campos |
| **R-13** | Mídia sem transcrição (6,8% das mensagens) | Baixa | Skill instrui a pedir o dado em texto. Não construir STT |
| **R-14** | Vendorizar o `quote-service` no nosso repo (para `docker compose up` funcionar sozinho) | Baixa | Copiar sob `vendor/quote-service/` com atribuição e link do commit de origem (`52a006c`) |

### 8.1 Gaps de informação ainda abertos

| Gap | Impacto | Resolução |
|---|---|---|
| Model ID exato do provider OpenAI vigente em set/2026 | Bloqueia US-07 | Confirmar no Dia 1; `LLM_MODEL` / `LLM_MODEL_CHEAP` por env var, sem hardcode |
| `OPENAI_API_KEY` disponível? | Bloqueia US-07 | Confirmar antes do Dia 1 |
| Formato de saída do agente | Nenhum — *"não existe formato de saída certo definido de propósito"* (README) | Decisão nossa, documentada no README |
| Quantos turnos antes de desistir da cotação | Critério de handoff | Definido em `handoff.md`: 2 ciclos de retry esgotados |

---

## 9. Conclusão do discovery

O challenge é mais estreito e mais profundo do que o prompt inicial sugere. Ele pede **um
agente que não minta sobre preço quando a infra cai**, com rastro auditável e critério de
handoff defensável. Tudo o mais é acessório.

Três coisas decidem a nota, e todas as três são resolvidas por **código determinístico**, não
por prompt:

1. **Gate de preço/cobertura em código** — o agente fica mecanicamente incapaz de informar
   um preço que não veio de um `200` da `/quote`. Ataca E-06, E-07 e o seu requisito 17.
2. **Retry + breaker calibrados com a matemática de §4** — e a decisão documentada com os
   números, não com "boas práticas".
3. **Trace JSONL + painel** — E-09 e E-04 pelo preço de um.

E dois diferenciadores que só aparecem para quem leu o `plans.json`:
**recusa de subscrição** (30% dos leads) e **carência + pro-rata** (0% do dataset humano).

Detalhamento em `ARCHITECTURE.MD`; execução em `tasks/`.
