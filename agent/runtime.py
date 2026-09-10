"""Monta os componentes do agente a partir das settings. Ponto único de composição:
a API, o eval harness e a demo passam por aqui, trocando só transporte, LLM e sink."""

from __future__ import annotations

from dataclasses import dataclass

from agent.config import Settings, get_settings
from agent.llm import LLM, OpenAILLM, RuleBasedLLM
from agent.orchestrator import Orchestrator
from agent.resilience.breaker import CircuitBreaker
from agent.resilience.retry import ResilientQuoteClient, RetryPolicy
from agent.security.injection import InjectionScanner
from agent.skills import SkillCatalog
from agent.state import ConversationStore
from agent.tools.quote_client import HttpxTransport, QuoteClient, QuoteTransport
from agent.tracing.sink import JsonlSink, MultiSink, TraceSink


@dataclass
class Runtime:
    settings: Settings
    store: ConversationStore
    sink: TraceSink
    catalog: SkillCatalog
    quote_client: QuoteClient
    quotes: ResilientQuoteClient
    llm: LLM
    orchestrator: Orchestrator

    @property
    def llm_mode(self) -> str:
        return "openai" if isinstance(self.llm, OpenAILLM) else "fake"


def build_runtime(
    settings: Settings | None = None,
    *,
    transport: QuoteTransport | None = None,
    llm: LLM | None = None,
    sink: TraceSink | None = None,
    extra_sinks: list[TraceSink] | None = None,
) -> Runtime:
    settings = settings or get_settings()
    store = ConversationStore()
    primary: TraceSink = sink if sink is not None else JsonlSink(settings.trace_dir)
    sinks: list[TraceSink] = [primary, *(extra_sinks or [])]
    if not extra_sinks:
        try:
            from agent.tracing.langwatch import build_langwatch_sink

            lw = build_langwatch_sink(settings)
            if lw is not None:
                sinks.append(lw)
        except ImportError:
            pass
    final_sink: TraceSink = sinks[0] if len(sinks) == 1 else MultiSink(sinks)

    catalog = SkillCatalog.load(settings.skills_dir)
    quote_client = QuoteClient(
        transport or HttpxTransport(settings.quote_api_url), timeout_s=settings.quote_timeout_s
    )
    quotes = ResilientQuoteClient(
        quote_client,
        RetryPolicy(
            max_attempts=settings.quote_max_attempts,
            backoff_base_s=settings.quote_backoff_base_s,
        ),
        CircuitBreaker(settings.breaker_consecutive, settings.breaker_cooldown_s, name="quote"),
        CircuitBreaker(
            settings.ratelimit_breaker_consecutive, settings.breaker_cooldown_s, name="rate_limit"
        ),
    )
    if llm is None:
        llm = OpenAILLM(settings) if settings.llm_enabled else RuleBasedLLM()
    scanner = InjectionScanner(
        classifier=llm.classify_injection if isinstance(llm, OpenAILLM) else None
    )
    orchestrator = Orchestrator(
        llm=llm,
        catalog=catalog,
        quotes=quotes,
        store=store,
        sink=final_sink,
        scanner=scanner,
        max_attempts=settings.quote_max_attempts,
    )
    return Runtime(settings, store, final_sink, catalog, quote_client, quotes, llm, orchestrator)
