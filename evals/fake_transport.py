"""Transportes determinísticos para testes e evals.

- `FakeQuoteTransport`: programa a sequência exata de respostas da `/quote`.
- `LocalLogicTransport`: executa a lógica real de cotação do serviço vendorizado, em
  processo, com data de referência congelada. Serve para caminhos felizes realistas
  sem HTTP e sem aleatoriedade.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from agent.tools.quote_client import (
    TransportConnectionError,
    TransportResponse,
    TransportTimeout,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR_QUOTE_SERVICE = REPO_ROOT / "vendor" / "namastex-fde-challenge" / "quote-service"
PLANS_PATH = VENDOR_QUOTE_SERVICE / "data" / "plans.json"

Step = TransportResponse | Exception | str | int | Callable[[Mapping[str, Any]], TransportResponse]


def load_plans() -> dict[str, Any]:
    return json.loads(PLANS_PATH.read_text(encoding="utf-8"))


def planos_response() -> TransportResponse:
    return TransportResponse(200, load_plans())


def ok_body(
    plano_id: str = "completo",
    premio_mensal: float = 209.90,
    franquia: float | None = None,
    coberturas: Sequence[str] | None = None,
    pro_rata: dict[str, Any] | None = None,
    multiplicadores: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    plans = load_plans()
    plano = next(p for p in plans["planos"] if p["id"] == plano_id)
    body: dict[str, Any] = {
        "plano_id": plano["id"],
        "plano_nome": plano["nome"],
        "premio_mensal": premio_mensal,
        "franquia": franquia if franquia is not None else plano["franquia"],
        "coberturas": list(coberturas) if coberturas is not None else list(plano["coberturas"]),
        "multiplicadores": dict(
            multiplicadores or {"faixa_etaria": 1.0, "idade_veiculo": 1.0, "regiao": 1.0}
        ),
        "carencia": {"coberturas": ["roubo", "furto"], "dias": 30, "observacao": ""},
        "moeda": "BRL",
    }
    if pro_rata:
        body["primeiro_pagamento_pro_rata"] = pro_rata
    return body


def ok(**kwargs: Any) -> TransportResponse:
    return TransportResponse(200, ok_body(**kwargs))


def unavailable(status: int = 503) -> TransportResponse:
    return TransportResponse(
        status,
        {
            "error": "upstream_unavailable",
            "message": "Servico de cotacao temporariamente indisponivel. Tente novamente.",
        },
    )


def refused(motivo: str = "Idade acima do limite de aceitacao (75 anos).") -> TransportResponse:
    return TransportResponse(422, {"error": "cotacao_recusada", "motivo": motivo})


def refused_vehicle() -> TransportResponse:
    return refused("Veiculo com mais de 20 anos nao e aceito.")


def plan_inexistente(plano: str = "turbo") -> TransportResponse:
    return refused(f"Plano '{plano}' inexistente. Opcoes: essencial, completo, premium")


def schema_error() -> TransportResponse:
    return TransportResponse(
        422,
        {"detail": [{"loc": ["body", "idade"], "msg": "Input should be a valid integer"}]},
    )


def payload_invalido(detalhe: str = "Invalid isoformat string: '15/07/2026'") -> TransportResponse:
    return TransportResponse(400, {"error": "payload_invalido", "detalhe": detalhe})


def rate_limited(retry_after: float | None = 1) -> TransportResponse:
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    return TransportResponse(429, {"error": "rate_limited"}, headers=headers)


TIMEOUT = "timeout"
CONNECTION_ERROR = "connection"


class FakeQuoteTransport:
    """Cada item do roteiro é consumido por uma chamada à /quote.

    Atalhos: `"timeout"`, `"connection"`, um `int` (status de indisponibilidade), uma
    exceção (levantada), um callable(payload) ou um `TransportResponse` pronto.
    """

    def __init__(
        self,
        script: Sequence[Step] = (),
        *,
        default: Step | None = None,
        planos: TransportResponse | Exception | None = None,
        simulated_latency_s: float = 0.0,
        on_call: Callable[[], None] | None = None,
    ):
        self._script = list(script)
        self._default = default
        self._planos = planos if planos is not None else planos_response()
        self.simulated_latency_s = simulated_latency_s
        self.calls: list[dict[str, Any]] = []
        self.planos_calls = 0
        self._on_call = on_call

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def push(self, *steps: Step) -> None:
        self._script.extend(steps)

    def post_quote(self, payload: Mapping[str, Any], timeout_s: float) -> TransportResponse:
        self.calls.append(dict(payload))
        if self._on_call:
            self._on_call()
        if self._script:
            step = self._script.pop(0)
        elif self._default is not None:
            step = self._default
        else:
            raise AssertionError("FakeQuoteTransport: roteiro esgotado — chamada não prevista")
        return self._resolve(step, payload, timeout_s)

    def _resolve(
        self, step: Step, payload: Mapping[str, Any], timeout_s: float
    ) -> TransportResponse:
        if isinstance(step, TransportResponse):
            return step
        if isinstance(step, Exception):
            raise step
        if step == TIMEOUT:
            raise TransportTimeout(f"read timeout after {timeout_s}s")
        if step == CONNECTION_ERROR:
            raise TransportConnectionError("connection refused")
        if isinstance(step, int):
            return unavailable(step)
        if callable(step):
            return step(payload)
        raise TypeError(f"passo de roteiro não suportado: {step!r}")

    def get_planos(self, timeout_s: float) -> TransportResponse:
        self.planos_calls += 1
        if isinstance(self._planos, Exception):
            raise self._planos
        return self._planos


def _load_vendored_quote_logic(today: dt.date) -> Any:
    """Importa `quote_logic.py` do serviço vendorizado com `date.today()` congelado."""
    path = VENDOR_QUOTE_SERVICE / "app" / "quote_logic.py"
    spec = importlib.util.spec_from_file_location("vendored_quote_logic", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    class FrozenDate(dt.date):
        @classmethod
        def today(cls) -> FrozenDate:
            return cls(today.year, today.month, today.day)

    class FrozenDatetimeModule:
        date = FrozenDate
        datetime = dt.datetime
        timedelta = dt.timedelta

    setattr(module, "dt", FrozenDatetimeModule)  # noqa: B010 — módulo carregado dinamicamente
    return module


class LocalLogicTransport:
    """Roda `cotar()` do serviço vendorizado em processo, reproduzindo o mapeamento de
    status do `main.py` (422 recusa, 400 payload inválido). Sem instabilidade, sem rede."""

    def __init__(self, today: dt.date = dt.date(2026, 9, 10)):
        self._logic = _load_vendored_quote_logic(today)
        self.calls: list[dict[str, Any]] = []
        self.planos_calls = 0

    def post_quote(self, payload: Mapping[str, Any], timeout_s: float) -> TransportResponse:
        self.calls.append(dict(payload))
        body = dict(payload)
        body.setdefault("plano_id", "essencial")
        try:
            return TransportResponse(200, self._logic.cotar(body))
        except self._logic.CotacaoRecusada as exc:
            return TransportResponse(422, {"error": "cotacao_recusada", "motivo": exc.motivo})
        except (KeyError, ValueError, TypeError) as exc:
            return TransportResponse(400, {"error": "payload_invalido", "detalhe": str(exc)})

    def get_planos(self, timeout_s: float) -> TransportResponse:
        self.planos_calls += 1
        return TransportResponse(200, self._logic.load_plans())
