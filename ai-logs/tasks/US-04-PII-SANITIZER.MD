# US-04 — Sanitização de PII em duas camadas

**Prioridade:** MUST · **Estimativa:** 2,5h · **Dia:** 1 · **Depende de:** US-01 · **Habilita:** US-05, US-09

## Contexto
`DISCOVERY.MD §5.6` *[medido]* — no dataset: CPF em **100%** das conversas, CEP 100%,
e-mail 55%, telefone 55%, placa 34%. 4.718 de 26.470 mensagens (17,8%) têm ao menos uma PII.

**A observação que simplifica tudo:** a `/quote` aceita exatamente 5 campos. **CPF, e-mail,
telefone e placa não estão entre eles** — não são necessários em ponto nenhum do fluxo.
Logo podem ser mascarados **na entrada, antes do modelo ver** (D-07), e não só antes de gravar.

`DISCOVERY.MD §5.4b`: o `DICIONARIO.md` exagera a variedade de formato — o gerador emite
formato fixo por entidade; o que varia é a **ordem** (6 permutações) e a **capitalização** do
rótulo. Regex case-insensitive cobre ~100% *deste* dataset, mas a suíte deve incluir variantes
sem pontuação, porque o mundo real é mais sujo.

## Objetivo
`sanitize(text, policy) -> (texto, entidades_encontradas)` — mascarador **por entidade**,
não moderador de conteúdo.

## Escopo
| Entidade | Contexto do LLM | Trace |
|---|---|---|
| CPF | `[CPF]` | `[CPF]` |
| E-mail | `[EMAIL]` | `[EMAIL]` |
| Telefone | `[TELEFONE]` | `[TELEFONE]` |
| Placa | `[PLACA]` | `[PLACA]` |
| **CEP** | **em claro** (entrada da cotação) | **prefixo:** `01***-***` |
| **Idade** | **em claro** | em claro |
| Nome | primeiro nome | pseudônimo estável `lead_7f3a` |

- Regex com e sem pontuação. CPF valida **dígito verificador** (reduz falso positivo em
  qualquer número de 11 dígitos). Placa Mercosul **e** formato antigo.
- Ordem de aplicação: CPF → telefone → CEP (evita sobreposição de padrões numéricos).
- **Camada 1 (ingress):** roda antes de montar o prompt.
- **Camada 2 (persistência):** todo dict que vai para JSONL/LangWatch passa pela mesma função.
  Defesa em profundidade — falha na camada 1 não vira vazamento em disco.
- Prefixo do CEP no trace é deliberado: os 2 primeiros dígitos determinam o agravo de 1,30x,
  então o trace continua **auditável** sem guardar o CEP completo.

## Critérios de aceitação
- [ ] `"Cpf 389.083.863-43, tenho 35 anos, cep 26703-384"` ⇒ `"Cpf [CPF], tenho 35 anos, cep 26703-384"`
- [ ] Mesmo resultado nas 6 permutações de ordem e nas duas capitalizações (`Cpf`/`cpf`)
- [ ] `"38908386343"` (sem pontuação) é mascarado
- [ ] `"(11) 98765-4321"` e `"+55 11 98765-4321"` são mascarados
- [ ] `2022` (ano de veículo) e `35` (idade) **nunca** são mascarados
- [ ] **`"seu sistema é uma porcaria, vocês são uns ladrões"` sai byte-a-byte idêntico** (req 33)
- [ ] Objeção (`"o preco ta salgado"`) sai intacta
- [ ] No trace, CEP aparece só como prefixo; no contexto do LLM, completo
- [ ] Rodar o sanitizador nas 26.470 mensagens do dataset: **0** CPF/e-mail/telefone/placa remanescentes
- [ ] Pseudônimo de nome é estável na mesma conversa e diferente entre conversas

## Notas
Sem vault reversível (WON'T): não precisamos desmascarar — o humano do handoff tem a thread
original do WhatsApp.
