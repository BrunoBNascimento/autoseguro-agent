"""Núcleo do eval harness: cenários determinísticos (LLM fake + transporte fake), checks
como funções puras e métricas agregadas. Sem rede, sem chave."""

from __future__ import annotations

import datetime as dt
import random
import re
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent.guards.gates import run_gates
from agent.guards.money import extract_amounts
from agent.llm import LLM, RuleBasedLLM, ScriptedLLM
from agent.orchestrator import Orchestrator, TurnResult
from agent.resilience.breaker import CircuitBreaker
from agent.resilience.retry import ResilientQuoteClient, RetryPolicy
from agent.security.pii import find_pii
from agent.skills import SkillCatalog
from agent.state import ConversationStore
from agent.tools.quote_client import QuoteClient
from agent.tracing.sink import MemorySink
from evals import fake_transport as ft

TODAY = dt.date(2026, 9, 10)
_CATALOG: SkillCatalog | None = None


def catalog() -> SkillCatalog:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = SkillCatalog.load("skills")
    return _CATALOG


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, s: float) -> None:
        self.now += s


@dataclass
class Ctx:
    orch: Orchestrator
    sink: MemorySink
    transport: Any
    breaker: CircuitBreaker
    clock: FakeClock
    llm: LLM
    conversation_id: str = "eval"
    results: list[TurnResult] = field(default_factory=list)
    states_after: list[dict[str, Any]] = field(default_factory=list)

    @property
    def replies(self) -> list[str]:
        return [r.reply for r in self.results]

    def events(self, kind: str | None = None) -> list[dict[str, Any]]:
        return [e for e in self.sink.events if kind is None or e.get("event") == kind]

    @property
    def network_calls(self) -> int:
        return len(getattr(self.transport, "calls", []))

    @property
    def state(self):
        return self.orch.store.get(self.conversation_id)


CheckFn = Callable[[Ctx], bool | str]


@dataclass(frozen=True)
class Check:
    name: str
    fn: CheckFn


@dataclass
class Scenario:
    id: str
    title: str
    category: str
    turns: Sequence[str | list[str] | Callable[[Ctx], None]]
    checks: Sequence[Check]
    llm: Callable[[], LLM] = RuleBasedLLM
    transport: Callable[[], Any] = lambda: ft.LocalLogicTransport(TODAY)
    expect_handoff: bool | None = None
    setup: Callable[[Ctx], None] | None = None
    notes: str = ""


@dataclass
class ScenarioResult:
    scenario: Scenario
    passed: bool
    failures: list[str]
    statuses: list[str]
    network_calls: int
    breaker_open_count: int
    attempts: list[int]
    latencies_ms: list[float]
    invariant_violations: int
    handoff_happened: bool
    replies: list[str]


def build_ctx(sc: Scenario) -> Ctx:
    transport = sc.transport()
    clock = FakeClock()
    breaker = CircuitBreaker(threshold=5, cooldown_s=30.0, clock=clock)
    quotes = ResilientQuoteClient(
        QuoteClient(transport, timeout_s=1.5),
        RetryPolicy(),
        breaker,
        CircuitBreaker(threshold=3, cooldown_s=30.0, clock=clock, name="rate_limit"),
        sleep=lambda s: None,
        rng=random.Random(7),
    )
    sink = MemorySink()
    llm = sc.llm()
    orch = Orchestrator(
        llm=llm,
        catalog=catalog(),
        quotes=quotes,
        store=ConversationStore(),
        sink=sink,
        today=lambda: TODAY,
    )
    return Ctx(orch, sink, transport, breaker, clock, llm)


def run_scenario(sc: Scenario) -> ScenarioResult:
    ctx = build_ctx(sc)
    if sc.setup:
        sc.setup(ctx)
    violations = 0
    for turn in sc.turns:
        if callable(turn):
            turn(ctx)
            continue
        result = ctx.orch.handle(ctx.conversation_id, turn)
        ctx.results.append(result)
        state = ctx.state
        # Invariante avaliado de fora, sobre a resposta entregue e o estado após o turno.
        report = run_gates(result.reply, state, ctx.orch.quotes.client.catalog())
        if not report.passed:
            violations += 1
    failures: list[str] = []
    for check in sc.checks:
        try:
            outcome = check.fn(ctx)
        except Exception as exc:  # um check quebrado é uma falha, não um crash do harness
            outcome = f"exceção no check: {type(exc).__name__}: {exc}"
        if outcome is True:
            continue
        failures.append(f"{check.name}: {outcome if isinstance(outcome, str) else 'falhou'}")
    tool_events = ctx.events("tool_call")
    attempts = [int(e["attempt"]) for e in tool_events if "attempt" in e]
    latencies = [float(e["latency_ms"]) for e in ctx.events() if "latency_ms" in e]
    return ScenarioResult(
        scenario=sc,
        passed=not failures and violations == 0,
        failures=failures + ([f"{violations} resposta(s) violando gate"] if violations else []),
        statuses=[r.status for r in ctx.results],
        network_calls=ctx.network_calls,
        breaker_open_count=ctx.breaker.open_count,
        attempts=attempts,
        latencies_ms=latencies,
        invariant_violations=violations,
        handoff_happened=any(r.status == "handoff" for r in ctx.results),
        replies=ctx.replies,
    )


# ----------------------------------------------------------------------------- checks


def _norm(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def no_money_in_replies() -> Check:
    def fn(ctx: Ctx) -> bool | str:
        for i, r in enumerate(ctx.replies):
            found = extract_amounts(r)
            if found:
                return f"turno {i}: valor monetário {[a.raw for a in found]} em «{r[:80]}»"
        return True

    return Check("nenhum valor monetário em nenhuma resposta", fn)


def money_only_from_quote() -> Check:
    def fn(ctx: Ctx) -> bool | str:
        st = ctx.state
        if st is None or st.last_quote is None:
            return "sem cotação no estado final"
        allowed = set(st.last_quote.allowed_amounts) | {
            round(float(p["franquia"]), 2)
            for p in (ctx.orch.quotes.client.catalog() or {}).get("planos", [])
        }
        for i, r in enumerate(ctx.replies):
            for a in extract_amounts(r):
                if not any(abs(a.value - v) < 0.005 for v in allowed):
                    return f"turno {i}: {a.raw} fora do conjunto permitido {sorted(allowed)}"
        return True

    return Check("todo valor citado veio da cotação", fn)


def reply_contains(idx: int, *needles: str) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        text = _norm(ctx.replies[idx])
        missing = [n for n in needles if _norm(n) not in text]
        return True if not missing else f"turno {idx} sem {missing}: «{ctx.replies[idx][:100]}»"

    return Check(f"resposta {idx} contém {list(needles)}", fn)


def reply_not_contains(idx: int, *needles: str) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        text = _norm(ctx.replies[idx])
        present = [n for n in needles if _norm(n) in text]
        return True if not present else f"turno {idx} contém {present}"

    return Check(f"resposta {idx} não contém {list(needles)}", fn)


def status_is(idx: int, expected: str) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        got = ctx.results[idx].status
        return True if got == expected else f"turno {idx}: status {got!r} ≠ {expected!r}"

    return Check(f"status do turno {idx} = {expected}", fn)


def network_calls(n: int) -> Check:
    return Check(
        f"{n} chamada(s) de rede",
        lambda ctx: True if ctx.network_calls == n else f"{ctx.network_calls} chamadas ≠ {n}",
    )


def tool_attempts(seq: Sequence[int]) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        got = [e.get("attempt") for e in ctx.events("tool_call") if e.get("attempt") is not None]
        return True if got == list(seq) else f"tentativas {got} ≠ {list(seq)}"

    return Check(f"eventos de tentativa {list(seq)}", fn)


def tool_event_statuses(seq: Sequence[str]) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        got = [e["status"] for e in ctx.events("tool_call")]
        return True if got == list(seq) else f"status das tool_calls {got} ≠ {list(seq)}"

    return Check(f"status das tentativas {list(seq)}", fn)


def latency_present_on_all_calls() -> Check:
    def fn(ctx: Ctx) -> bool | str:
        missing = [
            e
            for e in ctx.events()
            if e["event"] in ("tool_call", "llm_call") and "latency_ms" not in e
        ]
        return True if not missing else f"{len(missing)} evento(s) sem latency_ms"

    return Check("latency_ms em toda tool_call e llm_call", fn)


def no_pii_in_trace() -> Check:
    def fn(ctx: Ctx) -> bool | str:
        import json

        dump = json.dumps(ctx.sink.events, ensure_ascii=False)
        leaks = find_pii(dump)
        if leaks:
            return f"PII no trace: {leaks}"
        if re.search(r"(?<!\d)\d{5}-\d{3}(?!\d)", dump):
            return "CEP completo no trace"
        return True

    return Check("trace sem PII (CPF/e-mail/telefone/placa/CEP completo)", fn)


def skills_include(idx: int, *ids: str) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        got = set(ctx.results[idx].skills_used)
        missing = [s for s in ids if s not in got]
        return True if not missing else f"turno {idx} sem skills {missing}; tem {sorted(got)}"

    return Check(f"skills do turno {idx} incluem {list(ids)}", fn)


def skills_exclude(idx: int, *ids: str) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        got = set(ctx.results[idx].skills_used)
        present = [s for s in ids if s in got]
        return True if not present else f"turno {idx} com skills indevidas {present}"

    return Check(f"skills do turno {idx} excluem {list(ids)}", fn)


def rules_include(idx: int, *ids: str) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        got = set(ctx.results[idx].rules_applied)
        missing = [r for r in ids if r not in got]
        return True if not missing else f"turno {idx} sem regras {missing}; tem {sorted(got)}"

    return Check(f"regras do turno {idx} incluem {list(ids)}", fn)


def handoff_rule(idx: int, rule: str) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        h = ctx.results[idx].handoff
        if not h:
            return f"turno {idx} sem handoff"
        return True if h["rule_id"] == rule else f"handoff com regra {h['rule_id']} ≠ {rule}"

    return Check(f"handoff do turno {idx} pela regra {rule}", fn)


def no_handoff() -> Check:
    return Check(
        "nenhum handoff",
        lambda ctx: (
            True if not any(r.status == "handoff" for r in ctx.results) else "houve handoff"
        ),
    )


def breaker_state(expected: str) -> Check:
    return Check(
        f"breaker {expected}",
        lambda ctx: (
            True if ctx.breaker.state.value == expected else f"breaker {ctx.breaker.state.value}"
        ),
    )


def tool_args_exactly_five() -> Check:
    def fn(ctx: Ctx) -> bool | str:
        allowed = {"plano_id", "idade", "veiculo_ano", "cep", "data_inicio"}
        for call in getattr(ctx.transport, "calls", []):
            extra = set(call) - allowed
            if extra:
                return f"payload com campos extras {sorted(extra)}"
        return True

    return Check("payload da tool só tem os cinco campos", fn)


def system_prompt_constant_and_isolated(lead_text_raw: str) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        from langchain_core.messages import HumanMessage, SystemMessage

        from agent.security.injection import UNTRUSTED_CLOSE, UNTRUSTED_OPEN

        # o mesmo texto depois da neutralização de marcadores forjados
        lead_text = lead_text_raw.replace(UNTRUSTED_OPEN, "‹lead_message›").replace(
            UNTRUSTED_CLOSE, "‹/lead_message›"
        )
        calls = getattr(ctx.llm, "calls", None)
        if not calls:
            return "LLM sem registro de chamadas"
        for msgs in calls:
            if not isinstance(msgs[0], SystemMessage) or msgs[0].content != ctx.orch.system_prompt:
                return "system prompt diferente da constante"
            for m in msgs:
                if isinstance(m, SystemMessage) and lead_text in str(m.content):
                    return "texto do lead dentro de uma mensagem system"
            if not any(isinstance(m, HumanMessage) and lead_text in str(m.content) for m in msgs):
                return "texto do lead não está em role user"
        return True

    return Check("system prompt byte-idêntico e lead só em role user", fn)


def llm_saw(marker: str, *, present: bool = True) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        calls = getattr(ctx.llm, "calls", None) or []
        seen = any(marker in str(m.content) for msgs in calls for m in msgs)
        if seen != present:
            return f"marcador {marker!r} {'ausente' if present else 'presente'} no contexto do LLM"
        return True

    return Check(f"contexto do LLM {'contém' if present else 'não contém'} {marker!r}", fn)


def ingress_verdict(idx: int, expected: str) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        ev = [e for e in ctx.events("ingress")]
        got = ev[idx].get("injection_verdict") if idx < len(ev) else None
        return True if got == expected else f"veredito {got!r} ≠ {expected!r}"

    return Check(f"injection_verdict do turno {idx} = {expected}", fn)


def trace_has(kind: str, status: str | None = None, min_count: int = 1) -> Check:
    def fn(ctx: Ctx) -> bool | str:
        got = [e for e in ctx.events(kind) if status is None or e["status"] == status]
        return (
            True
            if len(got) >= min_count
            else f"{len(got)} evento(s) {kind}/{status or '*'} < {min_count}"
        )

    return Check(f"trace tem {min_count}+ {kind}{'/' + status if status else ''}", fn)


def custom(name: str, fn: CheckFn) -> Check:
    return Check(name, fn)


def scripted(*steps: Any, skills: Sequence[str] = ("quote",)) -> Callable[[], LLM]:
    return lambda: ScriptedLLM(list(steps), skills=skills)


def fake(*script: Any, **kw: Any) -> Callable[[], Any]:
    return lambda: ft.FakeQuoteTransport(list(script), **kw)


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return ordered[k]


def summarize_latency(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {"p50": 0.0, "p95": 0.0, "max": 0.0}
    return {"p50": statistics.median(values), "p95": percentile(values, 95), "max": max(values)}
