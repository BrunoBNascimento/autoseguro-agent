"""API HTTP do agente. Validação na borda, erro sempre no mesmo shape, sem stacktrace.

`GET /health` não chama a `/quote`: o `/health` do mock é "sempre estável" e não diz nada
sobre a saúde real. O sinal honesto é o estado do breaker, então é ele que aparece.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from agent.runtime import Runtime, build_runtime
from agent.tracing.schema import utc_now_iso

log = logging.getLogger(__name__)


class MessageIn(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    texts: list[str] | None = Field(default=None, min_length=1, max_length=10)

    @model_validator(mode="after")
    def _one_of(self) -> MessageIn:
        if (self.text is None) == (self.texts is None):
            raise ValueError("envie `text` ou `texts` (rajada), não ambos")
        return self

    def content(self) -> str | list[str]:
        return self.text if self.text is not None else list(self.texts or [])


def error_body(error: str, message: str, conversation_id: str | None = None) -> dict[str, Any]:
    return {"error": error, "message": message, "conversation_id": conversation_id}


def create_app(runtime: Runtime | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = runtime or build_runtime()
        rt: Runtime = app.state.runtime
        rt.quote_client.planos()  # aquece o catálogo (1 chamada por processo)
        log.info("agent-api pronta: llm=%s quote=%s", rt.llm_mode, rt.settings.quote_api_url)
        yield

    app = FastAPI(title="AutoSeguro Agent API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    def rt() -> Runtime:
        return app.state.runtime

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        msg = str(first.get("msg", "requisição inválida"))
        return JSONResponse(
            status_code=422,
            content=error_body("invalid_request", msg, request.path_params.get("cid")),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        cid = request.path_params.get("cid")
        log.exception("erro não tratado em %s", request.url.path)
        try:
            rt().sink.write(
                {
                    "ts": utc_now_iso(),
                    "conversation_id": cid or "api",
                    "event": "error",
                    "status": "error",
                    "error": {"kind": type(exc).__name__, "message": str(exc)[:300]},
                    "detail": {"path": request.url.path},
                }
            )
        except Exception:
            pass
        return JSONResponse(
            status_code=500, content=error_body("internal_error", "erro interno", cid)
        )

    @app.get("/health")
    def health() -> dict[str, Any]:
        r = rt()
        return {
            "status": "ok",
            "ts": utc_now_iso(),
            "llm": {"mode": r.llm_mode, "model": getattr(r.llm, "name", None)},
            "quote_api": {
                "url": r.settings.quote_api_url,
                "catalog_loaded": r.quote_client.catalog() is not None,
                "breaker": r.quotes.breaker.snapshot(),
                "rate_limit_breaker": r.quotes.rate_limit_breaker.snapshot(),
            },
            "conversations": len(r.store.ids()),
        }

    @app.post("/conversations", status_code=201)
    def create_conversation() -> dict[str, Any]:
        state = rt().store.create()
        return {"conversation_id": state.conversation_id, "created_at": state.created_at}

    @app.post("/conversations/{cid}/messages")
    def post_message(cid: str, body: MessageIn) -> Any:
        r = rt()
        if r.store.get(cid) is None:
            return JSONResponse(
                status_code=404, content=error_body("not_found", "conversa não encontrada", cid)
            )
        content = body.content()
        texts = content if isinstance(content, list) else [content]
        if any(len(t) > r.settings.max_message_chars for t in texts) or all(
            not t.strip() for t in texts
        ):
            return JSONResponse(
                status_code=422,
                content=error_body(
                    "invalid_request",
                    f"mensagem vazia ou acima de {r.settings.max_message_chars} caracteres",
                    cid,
                ),
            )
        result = r.orchestrator.handle(cid, content)
        return {
            "conversation_id": result.conversation_id,
            "message_id": result.message_id,
            "reply": result.reply,
            "status": result.status,
            "skills_used": result.skills_used,
            "rules_applied": result.rules_applied,
            "handoff": result.handoff,
            "breaker": result.breaker,
        }

    @app.get("/conversations/{cid}")
    def get_conversation(cid: str) -> Any:
        state = rt().store.get(cid)
        if state is None:
            return JSONResponse(
                status_code=404, content=error_body("not_found", "conversa não encontrada", cid)
            )
        return state.public_view()

    @app.get("/conversations/{cid}/trace")
    def get_trace(cid: str) -> Any:
        r = rt()
        if r.store.get(cid) is None:
            return JSONResponse(
                status_code=404, content=error_body("not_found", "conversa não encontrada", cid)
            )
        reader = getattr(r.sink, "read", None)
        if reader is None and hasattr(r.sink, "sinks"):
            for s in r.sink.sinks:
                if hasattr(s, "read"):
                    reader = s.read
                    break
        events = reader(cid) if reader else []
        return {"conversation_id": cid, "count": len(events), "events": events}

    return app


app = create_app()
