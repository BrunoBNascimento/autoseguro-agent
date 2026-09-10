"""Destinos do trace. Todo dict passa pelo sanitizador de persistência antes de sair."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from agent.security.pii import Policy, sanitize_obj

log = logging.getLogger(__name__)


class TraceSink(Protocol):
    def write(self, event: dict[str, Any]) -> None: ...


def sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    return sanitize_obj(event, Policy.PERSISTENCE)


class JsonlSink:
    """Append-only, um arquivo por conversa. Sem lock entre processos: um arquivo por
    conversa evita contenção, e um lock em memória cobre threads do mesmo processo."""

    def __init__(self, directory: Path | str):
        self.directory = Path(directory)
        self._lock = threading.Lock()

    def path_for(self, conversation_id: str) -> Path:
        safe = "".join(ch for ch in conversation_id if ch.isalnum() or ch in "_-") or "unknown"
        return self.directory / f"{safe}.jsonl"

    def write(self, event: dict[str, Any]) -> None:
        clean = sanitize_event(event)
        line = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
        path = self.path_for(str(event.get("conversation_id", "unknown")))
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()

    def read(self, conversation_id: str) -> list[dict[str, Any]]:
        path = self.path_for(conversation_id)
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if raw:
                    events.append(json.loads(raw))
        return events

    def conversations(self) -> list[str]:
        if not self.directory.exists():
            return []
        return sorted(p.stem for p in self.directory.glob("*.jsonl"))


class MemorySink:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def write(self, event: dict[str, Any]) -> None:
        self.events.append(sanitize_event(event))

    def read(self, conversation_id: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e.get("conversation_id") == conversation_id]

    def of_type(self, event_type: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e.get("event") == event_type]


class MultiSink:
    """Fan-out best-effort: a falha de um destino não impede os outros nem o turno."""

    def __init__(self, sinks: Iterable[TraceSink]):
        self.sinks = list(sinks)

    def write(self, event: dict[str, Any]) -> None:
        for sink in self.sinks:
            try:
                sink.write(event)
            except Exception:
                log.exception("trace sink %s falhou", type(sink).__name__)
