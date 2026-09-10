"""Tracer de uma conversa. Emite eventos e mede latência — inclusive quando a operação
levanta exceção. Gravar trace nunca derruba o turno: falha de I/O é logada e engolida."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from agent.resilience.retry import AttemptRecord
from agent.security.pii import Policy, sanitize_obj
from agent.tools.quote_client import (
    CircuitOpen,
    InternalDefect,
    Ok,
    QuoteParams,
    RateLimited,
    Refused,
    Transient,
)
from agent.tracing.schema import TraceEvent, new_id
from agent.tracing.sink import TraceSink

log = logging.getLogger(__name__)


class Span:
    def __init__(self, event: TraceEvent):
        self.event = event

    def set(self, **fields: Any) -> None:
        for key, value in fields.items():
            if key == "detail":
                self.event.detail.update(value)
            else:
                setattr(self.event, key, value)


class Tracer:
    def __init__(
        self,
        sink: TraceSink,
        conversation_id: str,
        clock: Callable[[], float] = time.perf_counter,
    ):
        self.sink = sink
        self.conversation_id = conversation_id
        self._clock = clock
        self.turn = 0
        self.message_id: str | None = None
        self._span_stack: list[str] = []

    # ----------------------------------------------------------------- turnos e spans
    def begin_turn(self, message_id: str | None = None) -> str:
        self.turn += 1
        self.message_id = message_id or new_id("msg")
        self._span_stack = []
        return self.message_id

    @property
    def current_span_id(self) -> str | None:
        return self._span_stack[-1] if self._span_stack else None

    def _new_event(self, event_type: str, status: str, **fields: Any) -> TraceEvent:
        detail = fields.pop("detail", None) or {}
        ev = TraceEvent(
            conversation_id=self.conversation_id,
            event=event_type,
            status=status,
            message_id=self.message_id,
            turn=self.turn or None,
            parent_span_id=self.current_span_id,
            detail=dict(detail),
        )
        for key, value in fields.items():
            setattr(ev, key, value)
        return ev

    def emit(self, event_type: str, status: str = "ok", **fields: Any) -> dict[str, Any]:
        ev = self._new_event(event_type, status, **fields)
        return self._write(ev)

    @contextmanager
    def span(self, event_type: str, status: str = "ok", **fields: Any) -> Iterator[Span]:
        ev = self._new_event(event_type, status, **fields)
        handle = Span(ev)
        self._span_stack.append(ev.span_id)
        started = self._clock()
        try:
            yield handle
        except Exception as exc:
            ev.status = "error"
            ev.error = {"kind": type(exc).__name__, "message": str(exc)[:500], "retryable": False}
            raise
        finally:
            ev.latency_ms = round((self._clock() - started) * 1000.0, 3)
            self._span_stack.pop()
            self._write(ev)

    def _write(self, ev: TraceEvent) -> dict[str, Any]:
        data = ev.to_dict()
        try:
            self.sink.write(data)
        except Exception:
            log.exception("falha ao gravar trace (evento %s)", ev.event)
        return data

    # ----------------------------------------------------------------- helpers de domínio
    def quote_attempt(
        self, record: AttemptRecord, params: QuoteParams, attempts_total: int
    ) -> None:
        """Uma tentativa da /quote = um evento `tool_call`, inclusive as que falham."""
        out = record.outcome
        fields: dict[str, Any] = {
            "tool": "quote_api",
            "input_sanitized": sanitize_obj(params.payload(), Policy.PERSISTENCE),
            "latency_ms": out.latency_ms,
            "attempt": record.attempt,
            "attempts_total": attempts_total,
            "breaker": record.breaker,
            "http_status": getattr(out, "http_status", None),
            "detail": {"will_retry": record.will_retry, "wait_s": round(record.wait_s, 3)},
        }
        if isinstance(out, Ok):
            fields["detail"].update(
                {
                    "plano_id": out.quote.plano_id,
                    "premio_mensal": out.quote.premio_mensal,
                    "multiplicadores": out.quote.multiplicadores,
                }
            )
            self.emit("tool_call", "ok", **fields)
        elif isinstance(out, Refused):
            fields["error"] = {
                "kind": f"refused_{out.kind}",
                "retryable": False,
                "message": out.motivo,
            }
            self.emit("tool_call", "refused", **fields)
        else:
            fields["error"] = outcome_error(out)
            self.emit("tool_call", "error", **fields)

    def quote_skipped(
        self, outcome: CircuitOpen, params: QuoteParams, breaker: dict[str, Any]
    ) -> None:
        self.emit(
            "tool_call",
            "skipped",
            tool="quote_api",
            input_sanitized=sanitize_obj(params.payload(), Policy.PERSISTENCE),
            latency_ms=0.0,
            breaker=breaker,
            error={
                "kind": f"circuit_open_{outcome.scope}",
                "retryable": True,
                "message": f"breaker aberto; nova tentativa em {outcome.retry_in_s:.1f}s",
            },
        )


def outcome_error(out: Any) -> dict[str, Any]:
    if isinstance(out, Transient):
        return {
            "kind": out.kind,
            "retryable": True,
            "http_status": out.http_status,
            "message": out.detail[:300],
        }
    if isinstance(out, RateLimited):
        return {
            "kind": "rate_limited",
            "retryable": True,
            "http_status": 429,
            "retry_after_s": out.retry_after_s,
        }
    if isinstance(out, InternalDefect):
        return {
            "kind": f"internal_{out.kind}",
            "retryable": False,
            "http_status": out.http_status,
            "message": out.detail[:300],
        }
    return {"kind": type(out).__name__, "retryable": False}
