import random

from agent.resilience.breaker import BreakerState, CircuitBreaker
from agent.resilience.retry import AttemptRecord, ResilientQuoteClient, RetryPolicy
from agent.tools.quote_client import (
    CircuitOpen,
    InternalDefect,
    QuoteClient,
    QuoteParams,
    RateLimited,
    Refused,
    Transient,
)
from evals import fake_transport as ft

PARAMS = QuoteParams("completo", 35, 2022, "01310-100")


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, s: float) -> None:
        self.now += s


def build(*script: ft.Step, policy: RetryPolicy | None = None, clock: FakeClock | None = None):
    clock = clock or FakeClock()
    transport = ft.FakeQuoteTransport(list(script))
    breaker = CircuitBreaker(threshold=5, cooldown_s=30.0, clock=clock)
    rl = CircuitBreaker(threshold=3, cooldown_s=30.0, clock=clock, name="rate_limit")
    waits: list[float] = []
    records: list[AttemptRecord] = []
    client = ResilientQuoteClient(
        QuoteClient(transport, timeout_s=1.5),
        policy=policy or RetryPolicy(),
        breaker=breaker,
        rate_limit_breaker=rl,
        sleep=waits.append,
        rng=random.Random(7),
        on_attempt=records.append,
    )
    return client, transport, breaker, rl, waits, records


def test_503_503_200_sucesso_com_tres_eventos_e_backoff():
    client, transport, breaker, _, waits, records = build(503, 503, ft.ok())
    result = client.quote(PARAMS)
    assert result.ok and transport.call_count == 3
    assert [r.attempt for r in records] == [1, 2, 3]
    assert [r.status for r in records] == ["error", "error", "ok"]
    assert len(waits) == 2 and 0.2 <= waits[0] <= 0.6 and 0.4 <= waits[1] <= 1.2
    assert waits[1] > waits[0] * 1.0  # cresce com a tentativa (base dobra)
    assert breaker.consecutive_failures == 0 and breaker.state is BreakerState.CLOSED


def test_backoff_tem_jitter():
    p = RetryPolicy()
    a = [p.backoff_delay(i, random.Random(1)) for i in (1, 2)]
    b = [p.backoff_delay(i, random.Random(2)) for i in (1, 2)]
    assert a != b


def test_422_recusa_faz_uma_unica_chamada():
    client, transport, breaker, _, waits, _ = build(ft.refused())
    result = client.quote(PARAMS)
    assert isinstance(result.outcome, Refused) and transport.call_count == 1 and waits == []
    assert breaker.consecutive_failures == 0


def test_400_faz_uma_chamada_e_nao_incrementa_o_streak():
    client, transport, breaker, _, _, _ = build(ft.payload_invalido())
    breaker.consecutive_failures = 2
    result = client.quote(PARAMS)
    assert isinstance(result.outcome, InternalDefect) and transport.call_count == 1
    assert breaker.consecutive_failures == 0  # resposta bem formada = serviço de pé


def test_timeout_e_transitorio_e_retentado():
    client, transport, _, _, waits, records = build(ft.TIMEOUT, ft.ok())
    result = client.quote(PARAMS)
    assert result.ok and transport.call_count == 2 and len(waits) == 1
    assert isinstance(records[0].outcome, Transient) and records[0].outcome.kind == "timeout"
    assert records[0].outcome.latency_ms >= 0


def test_tres_falhas_esgotam_e_retornam_transitorio():
    client, transport, breaker, _, _, _ = build(503, 502, 500)
    result = client.quote(PARAMS)
    assert result.exhausted and isinstance(result.outcome, Transient)
    assert transport.call_count == 3 and breaker.consecutive_failures == 3
    assert breaker.state is BreakerState.CLOSED


def test_breaker_abre_em_cinco_e_a_proxima_cotacao_nao_toca_a_rede():
    clock = FakeClock()
    client, transport, breaker, _, _, _ = build(*([503] * 6), ft.ok(), clock=clock)
    r1 = client.quote(PARAMS)  # 3 falhas
    assert r1.exhausted and breaker.consecutive_failures == 3
    r2 = client.quote(PARAMS)  # 4ª e 5ª falha → abre no meio da cotação, sem 3ª tentativa
    assert r2.exhausted and breaker.state is BreakerState.OPEN
    assert transport.call_count == 5
    r3 = client.quote(PARAMS)
    assert isinstance(r3.outcome, CircuitOpen) and r3.circuit_open
    assert transport.call_count == 5  # zero rede
    assert 0 < r3.outcome.retry_in_s <= 30


def test_half_open_envia_exatamente_uma_sonda_e_fecha_no_200():
    clock = FakeClock()
    client, transport, breaker, _, _, _ = build(*([503] * 5), ft.ok(), ft.ok(), clock=clock)
    client.quote(PARAMS)
    client.quote(PARAMS)
    assert breaker.state is BreakerState.OPEN
    clock.advance(29.9)
    assert isinstance(client.quote(PARAMS).outcome, CircuitOpen)
    clock.advance(0.2)
    assert breaker.allow() is True  # sonda liberada
    assert breaker.allow() is False  # segunda chamada em half-open é barrada
    breaker.record_success()
    assert breaker.state is BreakerState.CLOSED
    assert client.quote(PARAMS).ok


def test_half_open_reabre_na_falha_da_sonda():
    clock = FakeClock()
    breaker = CircuitBreaker(threshold=5, cooldown_s=30.0, clock=clock)
    for _ in range(5):
        breaker.record_failure()
    assert breaker.state is BreakerState.OPEN and breaker.open_count == 1
    clock.advance(31)
    assert breaker.allow()
    breaker.record_failure()
    assert breaker.state is BreakerState.OPEN and breaker.open_count == 2
    assert breaker.retry_in_s() > 29


def test_429_faz_um_retry_honrando_retry_after_em_contador_separado():
    client, transport, breaker, rl, waits, _ = build(ft.rate_limited(1), ft.ok())
    result = client.quote(PARAMS)
    assert result.ok and transport.call_count == 2
    assert waits == [1.0]
    assert breaker.consecutive_failures == 0  # streak geral inalterado
    assert rl.consecutive_failures == 0  # zerado pelo sucesso


def test_429_duas_vezes_esgota_com_um_unico_retry():
    client, transport, breaker, rl, _, _ = build(ft.rate_limited(1), ft.rate_limited(1))
    result = client.quote(PARAMS)
    assert isinstance(result.outcome, RateLimited) and transport.call_count == 2
    assert rl.consecutive_failures == 2 and breaker.consecutive_failures == 0


def test_retry_after_e_limitado():
    client, _, _, _, waits, _ = build(ft.rate_limited(120), ft.ok())
    client.quote(PARAMS)
    assert waits == [5.0]


def test_breaker_de_rate_limit_abre_separado_do_geral():
    clock = FakeClock()
    client, transport, breaker, rl, _, _ = build(
        ft.rate_limited(1), ft.rate_limited(1), ft.rate_limited(1), ft.ok(), clock=clock
    )
    client.quote(PARAMS)  # 429, 429 → rl streak 2
    client.quote(PARAMS)  # 429 → rl abre em 3; sem retry
    assert rl.state is BreakerState.OPEN and breaker.state is BreakerState.CLOSED
    result = client.quote(PARAMS)
    assert isinstance(result.outcome, CircuitOpen) and result.outcome.scope == "rate_limit"
    assert transport.call_count == 3


def test_calibragem_consecutivas_quase_nunca_abre_com_servico_normal():
    """10.000 tentativas com p=0,30 de falha iid: aberturas espúrias < 1% das tentativas."""
    rng = random.Random(42)
    clock = FakeClock()
    breaker = CircuitBreaker(threshold=5, cooldown_s=0.0, clock=clock)
    for _ in range(10_000):
        breaker.allow()
        if rng.random() < 0.30:
            breaker.record_failure()
        else:
            breaker.record_success()
    assert breaker.open_count / 10_000 < 0.01
    # ordem de grandeza esperada: 0,3^5 ≈ 0,24% por posição
    assert 5 <= breaker.open_count <= 60


def test_janela_deslizante_abriria_muito_mais():
    """Comparativo do README: 50% em 10 chamadas dispara em ~15% das janelas com p=0,30."""
    rng = random.Random(42)
    hits = 0
    windows = 20_000
    for _ in range(windows):
        fails = sum(rng.random() < 0.30 for _ in range(10))
        hits += fails >= 5
    assert 0.10 < hits / windows < 0.20
