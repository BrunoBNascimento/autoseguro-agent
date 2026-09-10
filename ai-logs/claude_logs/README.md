# claude_logs

Logs crus das sessões de IA usadas no desafio. É **entregável obrigatório** — o README do
challenge diz que os `ai-logs/` "entram na avaliação junto com o código".

## De onde vêm

| Ferramenta | Origem |
|---|---|
| Claude Code | `~/.claude/projects/-home-bruno-benicio-my-workspace/*.jsonl` |
| Codex CLI | `~/.codex/sessions/` |
| ChatGPT / Claude.ai | export ou link público da conversa |
| Cursor / Windsurf | copiar o histórico do painel para `.md` |

Sessão única (discovery + planejamento + implementação, 2026-09-10):
`01-20260910-discovery-e-implementacao.jsonl`.

## Convenção

`NN-<data>-<assunto>.jsonl` — ex.: `01-20260910-discovery.jsonl`. Um `.md` legível ao lado
quando ajudar a leitura.

## Antes do push — a rede de segurança encontrou algo real

Decisão original: publicar os `.jsonl` **crus** (o Bruno havia removido logs de *outros
projetos* que existiam soltos nesta workspace). Rodando o grep de segurança antes de copiar
este arquivo para cá, ele **não deu "limpo"**:

```bash
grep -riE 'CLIENTE_ANONIMIZADO|TICKET-[0-9]|JIRA_API_TOKEN|ID_CLIENTE_ANONIMIZADO|sk-[A-Za-z0-9]{10,}|gho_[A-Za-z0-9]' .
```

Esta sessão do Claude Code roda numa workspace compartilhada com outro cliente (DevOS lê
`brain_kb/` no boot e o agente consultou memória de sessões anteriores). O transcript
acabou carregando, via saída de ferramenta, referências ao **outro cliente**: nome da conta
GitHub cliente/organização, ids de ticket, o `cloud_id` do Atlassian daquele cliente, e dois
e-mails pessoais do Bruno. Nada disso é segredo do **Namastex challenge**, mas publicar
misturaria dados de um cliente diferente num repo público de outro engajamento — o tipo de
vazamento que o próprio aviso do challenge pede pra evitar ("dados pessoais seus" incluídos).

**Ação tomada:** substituição de string simples e determinística (sem tocar em espaços,
aspas ou chaves — preserva o JSON linha a linha) nos únicos padrões encontrados:

| Original | Vira |
|---|---|
| nome do cliente/organização (repetido) | `[cliente-anonimizado]` |
| conta GitHub daquele cliente | `[conta-github-anonimizada]` |
| `TICKET-<número>` (tickets daquele cliente) | `ticket-xxxx` |
| `cloud_id` do Atlassian daquele cliente | `[cloud-id-anonimizado]` |
| nome de variável `JIRA_API_TOKEN` (nunca o valor — não havia valor no log) | `[VARIAVEL_TOKEN]` |
| e-mail de trabalho e e-mail pessoal do Bruno | `[email-trabalho-anonimizado]` / `[email-pessoal-anonimizado]` |

Verificado depois: **todas as 1.602 linhas continuam JSON válido** (`json.loads` linha a
linha) e o grep de segurança volta **limpo**. Nenhum conteúdo técnico do desafio (decisões,
código, raciocínio) foi alterado — só esses identificadores.

Rode de novo antes de publicar, é rápido e mecânico:

```bash
grep -riE 'CLIENTE_ANONIMIZADO|TICKET-[0-9]|JIRA_API_TOKEN|ID_CLIENTE_ANONIMIZADO|sk-[A-Za-z0-9]{10,}|gho_[A-Za-z0-9]' \
  ai-logs/claude_logs/*.jsonl && echo "REVISAR ANTES DE PUBLICAR" || echo "limpo"
```

> Atenção do challenge: *"tire os seus segredos antes de commitar — isso vai pra um repo
> público."* Isso vale mesmo quando a autorização de publicar cru já foi dada — a
> autorização cobria "os logs que eu vi e removi", não um vazamento indireto via ferramenta
> dentro da própria sessão. Vale a pena levar essa lição para o DevOS: o boot do `brain_kb`
> mistura contexto entre clientes na mesma workspace por design, e isso é um risco real
> quando uma sessão vira log público.
