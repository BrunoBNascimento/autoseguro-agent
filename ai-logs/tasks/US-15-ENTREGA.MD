# US-15 — Entrega

**Prioridade:** MUST · **Estimativa:** 2h · **Dia:** 3 · **Depende de:** todas

## Contexto
Cinco entregáveis nomeados no README do challenge (E-01..E-05). Um deles — `ai-logs/` — é
**obrigatório** e entra na avaliação junto com o código.

## Escopo

### README.md — o entregável mais subestimado (E-03)
*"as decisões que você tomou (e por quê)"*. Levar os números, não adjetivos:
- Como rodar: um comando.
- **Por que timeout 1,5s:** p50 do sucesso medido = 0,9 ms, e o caminho lento é `sleep(8)` fixo.
- **Por que 3 tentativas:** 97,3% com `p=0,304` medido.
- **Por que breaker por falhas consecutivas:** janela 50%/10 abre por falso positivo em 15%
  das janelas; consecutivas-5 em 0,24%.
- **Por que gates em código:** requisito 17 — prompt não é garantia.
- **Por que o dataset não é fonte de preço:** 0 de 1.749 batem, mediana 1,45x.
- **Por que não LangWatch self-hosted:** 7 serviços, 8 GB RAM.
- **Por que sem banco.**
- Tabela de gatilhos de handoff (E-08 pede critério **explícito**).
- **Limitações declaradas:** gate de preço por regex é evadível (R-05); sem auth; 401/403/429
  não existem no mock e a política deles é testada só com fake.

### Log de uma execução completa (E-04)
Conversa do início ao fim com a cotação saindo: transcript + JSONL de trace, versionados em
`docs/demo/`. Bônus barato: uma segunda execução com `QUOTE_FAILURE_RATE=1.0` mostrando a
degradação sem preço — é o cenário que o challenge diz separar mais.

### `ai-logs/` — **com hífen** (R-12)
No repo de entrega a pasta é `ai-logs/`, não `ai_logs/`. Contém `DISCOVERY.MD`,
`ARCHITECTURE.MD`, `tasks/` e `claude_logs/`.

Você confirmou que já removeu os logs de outros projetos e autorizou publicar os `.jsonl` crus.
Fica só a rede de segurança mecânica antes do push — custa 5 segundos:
```bash
grep -riE 'CLIENTE_ANONIMIZADO|TICKET-[0-9]|JIRA_API_TOKEN|ID_CLIENTE_ANONIMIZADO|sk-[A-Za-z0-9]|gho_' ai-logs/ && echo "REVISAR" || echo "limpo"
```

### Checklist final
- [ ] Repo **público** no GitHub (E-02)
- [ ] `git clone && cp .env.example .env && docker compose up` funciona num clone limpo
- [ ] Nenhum segredo versionado (`.env`, chaves, tokens)
- [ ] `make test` e `make eval` verdes; `evals/REPORT.md` versionado
- [ ] `ai-logs/` **com hífen**, com plano e logs
- [ ] Grep de segurança acima executado
- [ ] `vendor/quote-service/` com atribuição e commit de origem (`52a006c`)
- [ ] README responde às 7 perguntas de "Como a gente vai olhar"
- [ ] **Avisar que começou** (E-12) e mandar o link
