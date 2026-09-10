# US-01 — Bootstrap do projeto e subida em um comando

**Prioridade:** MUST · **Estimativa:** 2h · **Dia:** 1 · **Depende de:** — · **Habilita:** todas

## Contexto
`DISCOVERY.MD` R-01: a máquina **não tem** `docker`, e `pip3`/`uv`/`ensurepip` estavam
ausentes (`python3 -m venv` falhava com *"ensurepip is not available"*).
`uv 0.12.12` já foi instalado durante o discovery e o `quote-service` já foi validado
rodando via `uv run uvicorn` na porta 8000. **Falta o Docker.**

## Objetivo
`git clone && cp .env.example .env && docker compose up` sobe os 3 serviços num clone limpo.

## Escopo
- Instalar Docker: `sudo apt install docker.io docker-compose-v2` (ou habilitar integração
  WSL2 do Docker Desktop). **Exige sudo — rodar via `!` no prompt.**
- Estrutura de diretórios conforme `ARCHITECTURE.MD §11`.
- `vendor/quote-service/` — cópia do `quote-service/` do challenge (commit `52a006c`), com
  `vendor/README.md` de atribuição e link da origem (D-11).
- `docker-compose.yml` com 3 serviços: `quote-api:8000`, `agent-api:8080`, `web:3000`.
  `agent-api` e `web` com `depends_on` + healthcheck no `quote-api`.
- `pyproject.toml` (uv), `.env.example`, `.gitignore` (inclui `data/traces/` **exceto** o log
  da demo), `Makefile`: `up`, `down`, `test`, `eval`, `demo`, `analyze`.
- `QUOTE_FAILURE_RATE`/`QUOTE_SLOW_RATE`/`QUOTE_SEED` expostos como env do compose (os evals
  dependem deles).

## Critérios de aceitação
- [ ] `docker compose up` sobe os 3 serviços; `curl :8000/health`, `:8080/health` e `:3000` respondem
- [ ] `docker compose down && docker compose up` funciona sem estado residual
- [ ] Nenhum serviço de banco no compose (D-06)
- [ ] `make test` roda a suíte sem rede e sem `OPENAI_API_KEY`
- [ ] `.env.example` lista toda variável, sem nenhum segredo real
- [ ] `vendor/README.md` cita origem, commit e licença

## Riscos
R-01 (bloqueio de sudo para Docker). Se o Docker não subir hoje, seguir com
`uv run uvicorn` e tratar o compose como pendência **de Dia 1**, não de Dia 3 —
"sobe em um comando" é requisito da stack.
