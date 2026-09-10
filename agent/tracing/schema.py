"""Schema do trace: um evento por linha, um arquivo JSONL por conversa.

Cobre o que foi pedido: conversation/message id, tool chamada, input sanitizado,
resultado/status, latência, erro quando houver, skills e regras utilizadas.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EventType = Literal[
    "ingress",
    "skill_selection",
    "llm_call",
    "tool_call",
    "guard",
    "handoff",
    "outbound",
    "error",
]
Status = Literal["ok", "error", "refused", "blocked", "degraded", "skipped", "pass"]


_DIGIT_RUN = re.compile(r"\d{4}")


def new_id(prefix: str, size: int = 12) -> str:
    """Id aleatório sem sequências longas de dígitos, para nunca parecer CPF, CEP ou
    telefone ao sanitizador de persistência."""
    while True:
        candidate = uuid.uuid4().hex[:size]
        if not _DIGIT_RUN.search(candidate):
            return f"{prefix}_{candidate}"


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class TraceEvent:
    conversation_id: str
    event: str
    status: str
    ts: str = field(default_factory=utc_now_iso)
    message_id: str | None = None
    turn: int | None = None
    span_id: str = field(default_factory=lambda: new_id("sp", 8))
    parent_span_id: str | None = None
    latency_ms: float | None = None
    tool: str | None = None
    input_sanitized: Any = None
    http_status: int | None = None
    attempt: int | None = None
    attempts_total: int | None = None
    error: dict[str, Any] | None = None
    skills_used: list[str] = field(default_factory=list)
    rules_applied: list[str] = field(default_factory=list)
    breaker: dict[str, Any] | None = None
    pii_masked: list[str] | None = None
    injection_verdict: str | None = None
    model: str | None = None
    tokens: dict[str, int] | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None and v != [] and v != {}}
