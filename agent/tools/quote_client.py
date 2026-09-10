"""Cliente da API de cotação (`POST /quote`).

Duas regras que este módulo existe para garantir:

1. O erro é classificado pelo CORPO da resposta, não pelo status. A `/quote` devolve `422`
   para três coisas diferentes: recusa de subscrição (desfecho de negócio), `plano_id`
   inexistente (bug do chamador) e erro de schema (bug do chamador). Só a primeira pode
   virar "recusamos seu perfil" para o lead.
2. Os cinco campos são validados ANTES da chamada. A API aceita CEP inválido em silêncio
   (responde 200 com região neutra, sub-cotando quem mora em área de agravo) e rejeita
   data fora do ISO com 400. Campo inválido vira `NeedsInput`, sem tocar a rede.

Retry, breaker e trace ficam em `agent.resilience` — aqui cada chamada é uma tentativa.
"""

from __future__ import annotations

import datetime as dt
import re
import time
import unicodedata
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx

PLANOS_FALLBACK: tuple[str, ...] = ("essencial", "completo", "premium")

_CEP_RE = re.compile(r"^\d{5}-?\d{3}$")
_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_BR_RE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?$")


# --------------------------------------------------------------------------- parâmetros


@dataclass(frozen=True)
class QuoteParams:
    plano_id: str
    idade: int
    veiculo_ano: int
    cep: str
    data_inicio: str | None = None  # ISO YYYY-MM-DD; nunca "" (muda o comportamento da API)

    def payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "plano_id": self.plano_id,
            "idade": self.idade,
            "veiculo_ano": self.veiculo_ano,
            "cep": self.cep,
        }
        if self.data_inicio:
            body["data_inicio"] = self.data_inicio
        return body


@dataclass(frozen=True)
class NeedsInput:
    """Campo ausente ou inválido. Não houve chamada de rede."""

    field: str
    reason: str
    options: tuple[str, ...] = ()


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def normalize_cep(value: Any) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"[\s.]", "", str(value).strip())
    if not _CEP_RE.match(digits):
        return None
    digits = digits.replace("-", "")
    return f"{digits[:5]}-{digits[5:]}"


def normalize_date(value: Any, today: dt.date) -> str | None | Literal[False]:
    """ISO ou formato brasileiro -> ISO. `None` quando ausente, `False` quando inválido."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("", "null", "none", "nao", "não", "n/a"):
        return None
    m = _ISO_RE.match(text)
    if m:
        try:
            return dt.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        except ValueError:
            return False
    m = _BR_RE.match(text)
    if not m:
        return False
    day, month = int(m[1]), int(m[2])
    if m[3]:
        year = int(m[3])
        if year < 100:
            year += 2000
    else:
        year = today.year
    try:
        parsed = dt.date(year, month, day)
    except ValueError:
        return False
    if not m[3] and parsed < today:
        parsed = dt.date(year + 1, month, day)
    return parsed.isoformat()


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        digits = re.sub(r"\D", "", value)
        return int(digits) if digits else None
    return None


def validate_quote_input(
    raw: Mapping[str, Any], planos: Collection[str], today: dt.date | None = None
) -> QuoteParams | NeedsInput:
    today = today or dt.date.today()
    options = tuple(planos)

    plano = _strip_accents(str(raw.get("plano_id") or "")).strip().lower()
    if plano not in options:
        return NeedsInput("plano_id", f"plano {plano!r} não existe", options)

    idade = _to_int(raw.get("idade"))
    if idade is None or not 0 <= idade <= 200:
        return NeedsInput("idade", "idade ausente ou fora de 0..200")

    ano = _to_int(raw.get("veiculo_ano"))
    if ano is None or not 1950 <= ano <= 2100:
        return NeedsInput("veiculo_ano", "ano do veículo ausente ou fora de 1950..2100")

    cep = normalize_cep(raw.get("cep"))
    if cep is None:
        return NeedsInput("cep", "CEP ausente ou fora do formato 00000-000")

    data = normalize_date(raw.get("data_inicio"), today)
    if data is False:
        return NeedsInput("data_inicio", "data de início não reconhecida (use DD/MM/AAAA)")

    return QuoteParams(plano_id=plano, idade=idade, veiculo_ano=ano, cep=cep, data_inicio=data)


# --------------------------------------------------------------------------- resultados


@dataclass(frozen=True)
class Quote:
    plano_id: str
    plano_nome: str
    premio_mensal: float
    franquia: float
    coberturas: tuple[str, ...]
    multiplicadores: dict[str, float]
    carencia: dict[str, Any]
    primeiro_pagamento_pro_rata: dict[str, Any] | None
    moeda: str
    raw: dict[str, Any] = field(repr=False, compare=False)

    @property
    def valor_primeiro_pagamento(self) -> float | None:
        if not self.primeiro_pagamento_pro_rata:
            return None
        return float(self.primeiro_pagamento_pro_rata["valor_primeiro_pagamento"])

    @property
    def allowed_amounts(self) -> frozenset[float]:
        """Os únicos valores monetários que o agente pode pronunciar após esta cotação."""
        values = {round(self.premio_mensal, 2), round(self.franquia, 2)}
        if self.valor_primeiro_pagamento is not None:
            values.add(round(self.valor_primeiro_pagamento, 2))
        return frozenset(values)

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> Quote:
        return cls(
            plano_id=str(body["plano_id"]),
            plano_nome=str(body.get("plano_nome", body["plano_id"])),
            premio_mensal=float(body["premio_mensal"]),
            franquia=float(body["franquia"]),
            coberturas=tuple(str(c) for c in body["coberturas"]),
            multiplicadores={k: float(v) for k, v in (body.get("multiplicadores") or {}).items()},
            carencia=dict(body.get("carencia") or {}),
            primeiro_pagamento_pro_rata=body.get("primeiro_pagamento_pro_rata"),
            moeda=str(body.get("moeda", "BRL")),
            raw=dict(body),
        )


@dataclass(frozen=True)
class Ok:
    quote: Quote
    latency_ms: float
    http_status: int = 200


@dataclass(frozen=True)
class Refused:
    """422 `cotacao_recusada` com motivo de subscrição. Desfecho de negócio, não erro."""

    motivo: str
    kind: Literal["idade", "veiculo", "outro"]
    latency_ms: float
    http_status: int = 422


@dataclass(frozen=True)
class InternalDefect:
    """Bug nosso ou resposta inesperada. Nunca retenta, nunca é comunicado como recusa."""

    detail: str
    kind: Literal["plano", "schema", "payload", "auth", "body", "unexpected"]
    latency_ms: float
    http_status: int | None


@dataclass(frozen=True)
class Transient:
    kind: Literal["http", "timeout", "connection"]
    detail: str
    latency_ms: float
    http_status: int | None


@dataclass(frozen=True)
class RateLimited:
    retry_after_s: float | None
    latency_ms: float
    http_status: int = 429


@dataclass(frozen=True)
class CircuitOpen:
    """O breaker impediu a chamada. Zero rede."""

    scope: Literal["quote", "rate_limit"]
    retry_in_s: float


AttemptOutcome = Ok | Refused | InternalDefect | Transient | RateLimited
QuoteOutcome = AttemptOutcome | NeedsInput | CircuitOpen

RETRYABLE: tuple[type, ...] = (Transient, RateLimited)


# --------------------------------------------------------------------------- transporte


class TransportTimeout(Exception):
    pass


class TransportConnectionError(Exception):
    pass


@dataclass
class TransportResponse:
    status: int
    body: Any
    text: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)


class QuoteTransport(Protocol):
    def post_quote(self, payload: Mapping[str, Any], timeout_s: float) -> TransportResponse: ...

    def get_planos(self, timeout_s: float) -> TransportResponse: ...


class HttpxTransport:
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"))

    def _wrap(self, response: httpx.Response) -> TransportResponse:
        try:
            body = response.json()
        except ValueError:
            body = None
        return TransportResponse(response.status_code, body, response.text, response.headers)

    def post_quote(self, payload: Mapping[str, Any], timeout_s: float) -> TransportResponse:
        try:
            return self._wrap(self._client.post("/quote", json=dict(payload), timeout=timeout_s))
        except httpx.TimeoutException as exc:
            raise TransportTimeout(str(exc)) from exc
        except httpx.TransportError as exc:
            raise TransportConnectionError(str(exc)) from exc

    def get_planos(self, timeout_s: float) -> TransportResponse:
        try:
            return self._wrap(self._client.get("/planos", timeout=timeout_s))
        except httpx.TimeoutException as exc:
            raise TransportTimeout(str(exc)) from exc
        except httpx.TransportError as exc:
            raise TransportConnectionError(str(exc)) from exc


# --------------------------------------------------------------------------- cliente


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = headers.get("Retry-After") or headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def classify_response(resp: TransportResponse, latency_ms: float) -> AttemptOutcome:
    status, body = resp.status, resp.body
    body_dict = body if isinstance(body, dict) else {}

    if status == 200:
        try:
            return Ok(Quote.from_body(body_dict), latency_ms)
        except (KeyError, TypeError, ValueError) as exc:
            return InternalDefect(f"corpo 200 inesperado: {exc}", "body", latency_ms, status)

    if status == 422:
        if body_dict.get("error") == "cotacao_recusada":
            motivo = str(body_dict.get("motivo", ""))
            low = _strip_accents(motivo).lower()
            if "plano" in low and "inexistente" in low:
                return InternalDefect(motivo, "plano", latency_ms, status)
            if "veiculo" in low:
                return Refused(motivo, "veiculo", latency_ms)
            if "idade" in low:
                return Refused(motivo, "idade", latency_ms)
            return Refused(motivo, "outro", latency_ms)
        if "detail" in body_dict:
            return InternalDefect(f"schema: {body_dict['detail']}", "schema", latency_ms, status)
        return InternalDefect(
            resp.text or "422 sem corpo reconhecível", "unexpected", latency_ms, status
        )

    if status == 400:
        detail = body_dict.get("detalhe") or body_dict.get("message") or resp.text
        return InternalDefect(str(detail), "payload", latency_ms, status)

    if status in (401, 403):
        return InternalDefect(f"HTTP {status}", "auth", latency_ms, status)

    if status == 429:
        return RateLimited(_retry_after(resp.headers), latency_ms)

    if status == 408 or 500 <= status <= 599:
        detail = body_dict.get("message") or body_dict.get("error") or resp.text or f"HTTP {status}"
        return Transient("http", str(detail), latency_ms, status)

    return InternalDefect(f"HTTP {status} inesperado", "unexpected", latency_ms, status)


class QuoteClient:
    """Uma chamada = uma tentativa. Sem retry, sem breaker, sem regra de negócio."""

    def __init__(
        self,
        transport: QuoteTransport,
        timeout_s: float = 1.5,
        planos_timeout_s: float = 3.0,
        clock: Callable[[], float] = time.perf_counter,
    ):
        self._transport = transport
        self.timeout_s = timeout_s
        self._planos_timeout_s = planos_timeout_s
        self._clock = clock
        self._catalog: dict[str, Any] | None = None
        self._planos: tuple[str, ...] | None = None

    # /planos é estável e é cálculo puro: busca uma vez por processo e cacheia.
    def catalog(self) -> dict[str, Any] | None:
        if self._planos is None:
            self._load_planos()
        return self._catalog

    def planos(self) -> tuple[str, ...]:
        if self._planos is None:
            self._load_planos()
        assert self._planos is not None
        return self._planos

    def _load_planos(self) -> None:
        try:
            resp = self._transport.get_planos(self._planos_timeout_s)
            ids = tuple(str(p["id"]).lower() for p in resp.body["planos"])
            if not ids:
                raise ValueError("catálogo vazio")
            self._catalog = dict(resp.body)
            self._planos = ids
        except Exception:
            self._catalog = None
            self._planos = PLANOS_FALLBACK

    def validate(
        self, raw: Mapping[str, Any], today: dt.date | None = None
    ) -> QuoteParams | NeedsInput:
        return validate_quote_input(raw, self.planos(), today)

    def quote(self, params: QuoteParams) -> AttemptOutcome:
        started = self._clock()
        try:
            resp = self._transport.post_quote(params.payload(), self.timeout_s)
        except TransportTimeout as exc:
            return Transient("timeout", str(exc) or "timeout", self._elapsed_ms(started), None)
        except TransportConnectionError as exc:
            return Transient("connection", str(exc) or "conexão", self._elapsed_ms(started), None)
        return classify_response(resp, self._elapsed_ms(started))

    def _elapsed_ms(self, started: float) -> float:
        return round((self._clock() - started) * 1000.0, 3)
