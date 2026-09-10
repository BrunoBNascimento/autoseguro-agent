"""Circuit breaker por falhas CONSECUTIVAS.

Com a `/quote` operando no normal (~30% de falha por tentativa), uma janela deslizante de
50% em 10 chamadas abriria por engano em ~15% das janelas. Cinco falhas consecutivas abrem
em 0,24%. Uma queda real (100% de falha) abre em 5 chamadas. Ver README para a conta.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        threshold: int = 5,
        cooldown_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        name: str = "quote",
    ):
        if threshold < 1:
            raise ValueError("threshold deve ser >= 1")
        self.name = name
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self._clock = clock
        self.state = BreakerState.CLOSED
        self.consecutive_failures = 0
        self.opened_at: float | None = None
        self.open_count = 0
        self._probe_in_flight = False

    def allow(self) -> bool:
        """Decide se uma chamada pode sair. Em half-open, libera exatamente uma sonda."""
        if self.state is BreakerState.CLOSED:
            return True
        if self.state is BreakerState.OPEN:
            if self.retry_in_s() > 0:
                return False
            self.state = BreakerState.HALF_OPEN
            self._probe_in_flight = False
        if self._probe_in_flight:
            return False
        self._probe_in_flight = True
        return True

    def record_success(self) -> None:
        self.state = BreakerState.CLOSED
        self.consecutive_failures = 0
        self.opened_at = None
        self._probe_in_flight = False

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.state is BreakerState.HALF_OPEN or self.consecutive_failures >= self.threshold:
            self._open()

    def _open(self) -> None:
        if self.state is not BreakerState.OPEN:
            self.open_count += 1
        self.state = BreakerState.OPEN
        self.opened_at = self._clock()
        self._probe_in_flight = False

    def allow_more(self) -> bool:
        """Retry dentro da mesma cotação: só se o breaker continua fechado."""
        return self.state is BreakerState.CLOSED

    def retry_in_s(self) -> float:
        if self.state is BreakerState.CLOSED or self.opened_at is None:
            return 0.0
        return max(0.0, self.cooldown_s - (self._clock() - self.opened_at))

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "threshold": self.threshold,
            "retry_in_s": round(self.retry_in_s(), 3),
            "open_count": self.open_count,
        }
