"""Exportador opcional para o LangWatch cloud. Sem `LANGWATCH_API_KEY` é no-op: nada é
importado, nada é enviado. Com a chave, espelha o MESMO dict já sanitizado do trace local,
best-effort — falha do exportador nunca derruba o turno."""

from __future__ import annotations

import logging
from typing import Any

from agent.config import Settings
from agent.tracing.sink import TraceSink, sanitize_event

log = logging.getLogger(__name__)


class LangWatchSink:
    def __init__(self, api_key: str, endpoint: str = "https://app.langwatch.ai"):
        import httpx  # lazy: só quando a feature está ligada

        self._client = httpx.Client(
            base_url=endpoint, headers={"X-Auth-Token": api_key}, timeout=2.0
        )
        self.sent = 0
        self.failed = 0

    def write(self, event: dict[str, Any]) -> None:
        clean = sanitize_event(event)  # defesa em profundidade: nunca payload cru
        payload = {
            "trace_id": str(clean.get("conversation_id")),
            "spans": [
                {
                    "type": "span",
                    "span_id": str(clean.get("span_id") or clean.get("message_id") or "sp"),
                    "parent_id": clean.get("parent_span_id"),
                    "name": str(clean.get("event")),
                    "input": {"type": "json", "value": clean.get("input_sanitized")},
                    "output": {
                        "type": "json",
                        "value": {k: v for k, v in clean.items() if k not in ("input_sanitized",)},
                    },
                    "timestamps": {"started_at": clean.get("ts"), "finished_at": clean.get("ts")},
                    "metrics": {"latency_ms": clean.get("latency_ms")},
                }
            ],
            "metadata": {
                "status": clean.get("status"),
                "skills_used": clean.get("skills_used"),
                "rules_applied": clean.get("rules_applied"),
            },
        }
        try:
            resp = self._client.post("/api/collector", json=payload)
            if resp.status_code >= 400:
                self.failed += 1
                log.warning("langwatch respondeu %s", resp.status_code)
            else:
                self.sent += 1
        except Exception as exc:  # best-effort
            self.failed += 1
            log.warning("langwatch indisponível: %s", exc)


def build_langwatch_sink(settings: Settings) -> TraceSink | None:
    if not settings.langwatch_api_key:
        return None
    return LangWatchSink(settings.langwatch_api_key)
