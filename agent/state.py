"""Estado de conversa em memória (sem banco) e payload de handoff."""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from langchain_core.messages import BaseMessage

from agent.security.pii import Policy, cep_prefix, sanitize_obj
from agent.tools.quote_client import Quote, QuoteParams
from agent.tracing.schema import new_id, utc_now_iso

ConversationStatus = Literal["active", "handoff"]

# Eventos que o código levanta e que decidem skills por conta própria (o modelo não vota).
EVENT_BREAKER_OPEN = "breaker_open"
EVENT_RETRIES_EXHAUSTED = "quote_retries_exhausted"
EVENT_REFUSED = "quote_refused"
EVENT_HANDOFF = "handoff_required"


@dataclass
class HandoffPayload:
    conversation_id: str
    rule_id: str
    reason: str
    summary: str
    collected: dict[str, Any]
    quote_attempts: list[dict[str, Any]]
    skills_used: list[str]
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return sanitize_obj(asdict(self), Policy.PERSISTENCE)


@dataclass
class ConversationState:
    conversation_id: str
    created_at: str = field(default_factory=utc_now_iso)
    turn: int = 0
    status: ConversationStatus = "active"
    history: list[BaseMessage] = field(default_factory=list)
    collected: dict[str, Any] = field(default_factory=dict)
    last_quote: Quote | None = None
    last_quote_params: QuoteParams | None = None
    last_quote_status: str | None = None
    quote_cycles_failed: int = 0
    refusal: dict[str, str] | None = None
    handoff: HandoffPayload | None = None
    handoff_rule: str | None = None
    handoff_reason: str | None = None
    injection_strikes: int = 0
    sticky_events: set[str] = field(default_factory=set)
    quote_attempt_log: list[dict[str, Any]] = field(default_factory=list)
    skills_used_last: list[str] = field(default_factory=list)
    last_reply: str | None = None

    @property
    def handoff_required(self) -> bool:
        return EVENT_HANDOFF in self.sticky_events

    def require_handoff(self, rule_id: str, reason: str) -> None:
        if not self.handoff_required:
            self.handoff_rule = rule_id
            self.handoff_reason = reason
        self.sticky_events.add(EVENT_HANDOFF)

    def record_quote_params(self, params: QuoteParams) -> None:
        self.collected.update(
            {
                "plano_id": params.plano_id,
                "idade": params.idade,
                "veiculo_ano": params.veiculo_ano,
                "cep": params.cep,
                "data_inicio": params.data_inicio,
            }
        )
        self.last_quote_params = params

    def public_view(self) -> dict[str, Any]:
        collected = dict(self.collected)
        if collected.get("cep"):
            collected["cep"] = cep_prefix(collected["cep"])
        quote = None
        if self.last_quote:
            quote = {
                "plano_id": self.last_quote.plano_id,
                "premio_mensal": self.last_quote.premio_mensal,
                "franquia": self.last_quote.franquia,
                "coberturas": list(self.last_quote.coberturas),
                "valor_primeiro_pagamento": self.last_quote.valor_primeiro_pagamento,
                "multiplicadores": self.last_quote.multiplicadores,
            }
        return {
            "conversation_id": self.conversation_id,
            "created_at": self.created_at,
            "turn": self.turn,
            "status": self.status,
            "collected": collected,
            "last_quote": quote,
            "last_quote_status": self.last_quote_status,
            "quote_cycles_failed": self.quote_cycles_failed,
            "refusal": self.refusal,
            "handoff": self.handoff.to_dict() if self.handoff else None,
            "injection_strikes": self.injection_strikes,
            "skills_used_last": list(self.skills_used_last),
        }


class ConversationStore:
    def __init__(self) -> None:
        self._items: dict[str, ConversationState] = {}
        self._locks: dict[str, threading.RLock] = {}
        self._lock = threading.RLock()

    def create(self, conversation_id: str | None = None) -> ConversationState:
        with self._lock:
            cid = conversation_id or new_id("conv")
            if cid in self._items:
                raise KeyError(f"conversa {cid} já existe")
            state = ConversationState(cid)
            self._items[cid] = state
            return state

    def get(self, conversation_id: str) -> ConversationState | None:
        with self._lock:
            return self._items.get(conversation_id)

    def get_or_create(self, conversation_id: str) -> ConversationState:
        with self._lock:
            return self._items.get(conversation_id) or self.create(conversation_id)

    def ids(self) -> list[str]:
        with self._lock:
            return list(self._items)

    def lock_for(self, conversation_id: str) -> threading.RLock:
        """Um lock por conversa: turnos da mesma conversa são serializados, conversas
        diferentes correm em paralelo."""
        with self._lock:
            return self._locks.setdefault(conversation_id, threading.RLock())
