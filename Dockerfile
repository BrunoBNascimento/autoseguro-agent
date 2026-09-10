FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY agent ./agent
COPY skills ./skills
COPY evals ./evals

RUN mkdir -p /app/data/traces
EXPOSE 8080
CMD ["/app/.venv/bin/uvicorn", "agent.api:app", "--host", "0.0.0.0", "--port", "8080"]
