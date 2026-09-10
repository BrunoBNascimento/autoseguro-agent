# vendor/

## `namastex-fde-challenge/`

Cópia literal de <https://github.com/namastexlabs/namastex-fde-challenge>, commit
`52a006c` (*"docs: deixar explicito que os ai-logs entram na avaliacao"*), copiada em
2026-09-10 **sem modificações**. Contém:

| Pasta | O que é |
|---|---|
| `quote-service/` | Mock da API de cotação (`POST /quote`, `GET /planos`, `GET /health`) com instabilidade simulada |
| `dataset/` | 2.500 conversas sintéticas lead↔vendedor (`conversations.parquet`) + dicionário |
| `scripts/generate_dataset.py` | Gerador do dataset (reprodutível com `--seed 42`) |

**Por que vendorizar em vez de submodule:** `git clone && docker compose up` precisa funcionar
num clone limpo, sem passo manual. O `docker-compose.yml` da raiz aponta o serviço `quote-api`
para `vendor/namastex-fde-challenge/quote-service`.

**Licença:** o repositório de origem não declara arquivo de licença. O conteúdo é material do
desafio técnico da Namastex e é redistribuído aqui exclusivamente para a entrega desse desafio.
