.PHONY: up down logs test lint typecheck check eval analyze demo dev-quote dev-api dev-web

up:            ## sobe os 3 serviços (quote-api :8000, agent-api :8080, web :3000)
	docker compose up --build -d && docker compose ps

down:          ## derruba tudo, sem estado residual
	docker compose down --remove-orphans

logs:
	docker compose logs -f --tail=100

test:          ## suíte de testes — sem rede, sem OPENAI_API_KEY
	uv run pytest

lint:
	uv run ruff check . && uv run ruff format --check .

typecheck:
	uv run mypy

check: lint typecheck test

eval:          ## eval harness determinístico → evals/REPORT.md
	uv run python -m evals.run

analyze:       ## reproduz a análise do dataset → evals/dataset_report.md + evals/cases/
	uv run scripts/analyze_dataset.py --ref-date 2026-09-10

demo:          ## conversa completa ponta a ponta (usa LLM real se houver chave) → docs/demo/
	uv run python -m evals.demo

dev-quote:
	cd vendor/namastex-fde-challenge/quote-service && uv run uvicorn app.main:app --port 8000

dev-api:
	QUOTE_API_URL=http://localhost:8000 uv run uvicorn agent.api:app --port 8080 --reload

dev-web:
	cd web && npm run dev
