"""Retry com backoff exponencial + jitter, por cima do `QuoteClient`.

Só `Transient` e `RateLimited` são retentados. `Refused`, `InternalDefect` e `NeedsInput`
voltam na primeira tentativa: retentar um 400 ou um 422 só amplifica o erro. O 429 tem
contador e breaker próprios — throttling não é o downstream fora do ar, e abrir o breaker
geral por causa dele transformaria backpressure em apagão.

Uma tentativa = um `AttemptRecord`, entregue ao observador (o tracer) na hora.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agent.resilience.breaker import CircuitBreaker
from agent.tools.quote_client import (
    AttemptOutcome,
    CircuitOpen,
    InternalDefect,
    Ok,
    QuoteClient,
    QuoteParams,
    RateLimited,
    Refused,
    Transient,
)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_base_s: float = 0.4
    jitter: tuple[float, float] = (0.5, 1.5)
    max_backoff_s: float = 5.0
    rate_limit_max_retries: int = 1
    rate_limit_default_wait_s: float = 1.0
    rate_limit_max_wait_s: float = 5.0

    def backoff_delay(self, attempt: int, rng: random.Random) -> float:
        base = self.backoff_base_s * (2 ** (attempt - 1))
        return min(self.max_backoff_s, base * rng.uniform(*self.jitter))


@dataclass(frozen=True)
class AttemptRecord:
    attempt: int
    outcome: AttemptOutcome
    breaker: dict[str, Any]
    will_retry: bool
    wait_s: float  # espera aplicada DEPOIS desta tentativa (0 quando não há retry)

    @property
    def status(self) -> str:
        return outcome_status(self.outcome)


def outcome_status(outcome: AttemptOutcome | CircuitOpen) -> str:
    if isinstance(outcome, Ok):
        return "ok"
    if isinstance(outcome, Refused):
        return "refused"
    if isinstance(outcome, CircuitOpen):
        return "skipped"
    return "error"


@dataclass
class QuoteResult:
    outcome: AttemptOutcome | CircuitOpen
    attempts: list[AttemptRecord] = field(default_factory=list)
    breaker: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return isinstance(self.outcome, Ok)

    @property
    def exhausted(self) -> bool:
        """Falhou por transitório/rate limit depois de esgotar as tentativas."""
        return isinstance(self.outcome, Transient | RateLimited)

    @property
    def circuit_open(self) -> bool:
        return isinstance(self.outcome, CircuitOpen)

    @property
    def network_calls(self) -> int:
        return len(self.attempts)

    @property
    def total_latency_ms(self) -> float:
        return round(sum(a.outcome.latency_ms for a in self.attempts), 3)


class ResilientQuoteClient:
    def __init__(
        self,
        client: QuoteClient,
        policy: RetryPolicy | None = None,
        breaker: CircuitBreaker | None = None,
        rate_limit_breaker: CircuitBreaker | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        on_attempt: Callable[[AttemptRecord], None] | None = None,
    ):
        self.client = client
        self.policy = policy or RetryPolicy()
        self.breaker = breaker or CircuitBreaker(name="quote")
        self.rate_limit_breaker = rate_limit_breaker or CircuitBreaker(
            threshold=3, cooldown_s=30.0, name="rate_limit"
        )
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._on_attempt = on_attempt

    def quote(
        self, params: QuoteParams, on_attempt: Callable[[AttemptRecord], None] | None = None
    ) -> QuoteResult:
        observer = on_attempt or self._on_attempt
        if not self.breaker.allow():
            return QuoteResult(
                CircuitOpen("quote", self.breaker.retry_in_s()), [], self.breaker.snapshot()
            )
        if not self.rate_limit_breaker.allow():
            return QuoteResult(
                CircuitOpen("rate_limit", self.rate_limit_breaker.retry_in_s()),
                [],
                self.breaker.snapshot(),
            )

        attempts: list[AttemptRecord] = []
        attempt = 1
        rate_limit_retries = 0
        while True:
            outcome = self.client.quote(params)
            wait_s = 0.0
            will_retry = False

            if isinstance(outcome, Ok | Refused | InternalDefect):
                # Resposta bem formada (mesmo 4xx) = serviço de pé: zera os dois streaks.
                self.breaker.record_success()
                self.rate_limit_breaker.record_success()
            elif isinstance(outcome, Transient):
                self.breaker.record_failure()
                if attempt < self.policy.max_attempts and self.breaker.allow_more():
                    will_retry = True
                    wait_s = self.policy.backoff_delay(attempt, self._rng)
            elif isinstance(outcome, RateLimited):
                self.rate_limit_breaker.record_failure()
                if (
                    rate_limit_retries < self.policy.rate_limit_max_retries
                    and self.rate_limit_breaker.allow_more()
                ):
                    will_retry = True
                    rate_limit_retries += 1
                    wait_s = min(
                        self.policy.rate_limit_max_wait_s,
                        outcome.retry_after_s
                        if outcome.retry_after_s is not None
                        else self.policy.rate_limit_default_wait_s,
                    )

            record = AttemptRecord(attempt, outcome, self.breaker.snapshot(), will_retry, wait_s)
            attempts.append(record)
            if observer:
                observer(record)

            if not will_retry:
                return QuoteResult(outcome, attempts, self.breaker.snapshot())
            if wait_s > 0:
                self._sleep(wait_s)
            attempt += 1
