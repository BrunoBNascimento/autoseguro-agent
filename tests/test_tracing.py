import json
import random

import pytest

from agent.resilience.breaker import CircuitBreaker
from agent.resilience.retry import ResilientQuoteClient, RetryPolicy
from agent.security.pii import find_pii
from agent.tools.quote_client import QuoteClient, QuoteParams
from agent.tracing.sink import JsonlSink, MemorySink, MultiSink
from agent.tracing.tracer import Tracer
from evals import fake_transport as ft

PARAMS = QuoteParams("completo", 35, 2022, "01310-100", "2026-07-15")


def test_turno_feliz_emite_a_sequencia_esperada():
    sink = MemorySink()
    tr = Tracer(sink, "conv_test")
    tr.begin_turn("msg_1")
    tr.emit("ingress", pii_masked=["cpf"], injection_verdict="benign")
    tr.emit("skill_selection", skills_used=["identity_and_scope", "quote"])
    with tr.span("llm_call", model="fake") as sp:
        sp.set(tokens={"in": 10, "out": 5})
    tr.emit("tool_call", tool="quote_api", latency_ms=1.2, attempt=1, attempts_total=3)
    tr.emit("guard", "pass", rules_applied=["BR-01"])
    tr.emit("outbound")
    assert [e["event"] for e in sink.events] == [
        "ingress",
        "skill_selection",
        "llm_call",
        "tool_call",
        "guard",
        "outbound",
    ]
    assert all(
        e["conversation_id"] == "conv_test" and e["message_id"] == "msg_1" for e in sink.events
    )
    assert all(e["turn"] == 1 for e in sink.events)
    llm = sink.of_type("llm_call")[0]
    assert llm["latency_ms"] >= 0 and llm["tokens"] == {"in": 10, "out": 5}


def test_span_grava_latencia_e_erro_mesmo_com_excecao():
    sink = MemorySink()
    tr = Tracer(sink, "conv_x")
    tr.begin_turn()
    with pytest.raises(RuntimeError):
        with tr.span("llm_call", model="fake"):
            raise RuntimeError("boom")
    ev = sink.events[0]
    assert ev["status"] == "error" and ev["error"]["kind"] == "RuntimeError"
    assert "latency_ms" in ev


def test_spans_aninhados_tem_parent():
    sink = MemorySink()
    tr = Tracer(sink, "conv_x")
    tr.begin_turn()
    with tr.span("llm_call") as outer:
        tr.emit("guard", "pass", rules_applied=["BR-02"])
    guard, llm = sink.events
    assert guard["parent_span_id"] == outer.event.span_id
    assert "parent_span_id" not in llm


def test_cada_tentativa_de_retry_e_seu_proprio_evento():
    sink = MemorySink()
    tr = Tracer(sink, "conv_r")
    tr.begin_turn()
    transport = ft.FakeQuoteTransport([503, ft.TIMEOUT, ft.ok()])
    client = ResilientQuoteClient(
        QuoteClient(transport),
        RetryPolicy(),
        CircuitBreaker(),
        sleep=lambda s: None,
        rng=random.Random(1),
        on_attempt=lambda rec: tr.quote_attempt(rec, PARAMS, 3),
    )
    result = client.quote(PARAMS)
    assert result.ok
    calls = sink.of_type("tool_call")
    assert [c["attempt"] for c in calls] == [1, 2, 3]
    assert [c["status"] for c in calls] == ["error", "error", "ok"]
    assert all("latency_ms" in c for c in calls)
    assert calls[0]["error"]["retryable"] is True and calls[0]["http_status"] == 503
    assert calls[1]["error"]["kind"] == "timeout"
    assert calls[0]["input_sanitized"]["cep"] == "01***-***"
    assert calls[0]["detail"]["will_retry"] is True and calls[2]["detail"]["will_retry"] is False


def test_guard_bloqueado_tem_regra():
    sink = MemorySink()
    tr = Tracer(sink, "conv_g")
    tr.begin_turn()
    tr.emit("guard", "blocked", rules_applied=["BR-02"], detail={"gate": "price_gate"})
    ev = sink.events[0]
    assert ev["status"] == "blocked" and ev["rules_applied"] == ["BR-02"]


def test_jsonl_valido_uma_linha_por_evento_e_sem_pii(tmp_path):
    sink = JsonlSink(tmp_path)
    tr = Tracer(sink, "conv_j")
    tr.begin_turn()
    tr.emit(
        "ingress",
        detail={
            "text": "cpf 389.083.863-43 email a@b.com cep 01310-100 tel (11) 98765-4321 placa ABC1D23"
        },
    )
    tr.emit("tool_call", tool="quote_api", input_sanitized={"cep": "01310-100", "idade": 35})
    raw = (tmp_path / "conv_j.jsonl").read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if ln]
    assert len(lines) == 2
    events = [json.loads(ln) for ln in lines]
    assert find_pii(raw) == []
    assert "01310-100" not in raw and "01***-***" in raw
    assert events[1]["input_sanitized"] == {"cep": "01***-***", "idade": 35}
    assert sink.read("conv_j") == events
    assert sink.conversations() == ["conv_j"]


def test_falha_de_io_nao_derruba_o_turno():
    class Broken:
        def write(self, event):
            raise OSError("disk full")

    tr = Tracer(Broken(), "conv_b")
    tr.begin_turn()
    tr.emit("ingress")  # não levanta
    with tr.span("llm_call"):
        pass


def test_multisink_isola_falhas():
    class Broken:
        def write(self, event):
            raise OSError("x")

    mem = MemorySink()
    tr = Tracer(MultiSink([Broken(), mem]), "conv_m")
    tr.begin_turn()
    tr.emit("ingress")
    assert len(mem.events) == 1


def test_nome_de_arquivo_e_saneado(tmp_path):
    sink = JsonlSink(tmp_path)
    assert sink.path_for("../../etc/passwd").name == "etcpasswd.jsonl"
