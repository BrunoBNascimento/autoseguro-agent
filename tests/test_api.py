import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from agent.api import create_app
from agent.config import Settings
from agent.llm import RuleBasedLLM
from agent.runtime import build_runtime
from agent.security.pii import find_pii
from agent.tracing.sink import JsonlSink
from evals import fake_transport as ft

TODAY = dt.date(2026, 9, 10)


@pytest.fixture
def api(tmp_path):
    settings = Settings(llm_mode="fake", trace_dir=tmp_path)
    runtime = build_runtime(
        settings,
        transport=ft.LocalLogicTransport(TODAY),
        llm=RuleBasedLLM(),
        sink=JsonlSink(tmp_path),
    )
    runtime.orchestrator._today = lambda: TODAY
    runtime.orchestrator.quotes._sleep = lambda s: None
    with TestClient(create_app(runtime), raise_server_exceptions=False) as c:
        yield c, runtime


def test_conversa_completa_via_http(api):
    client, runtime = api
    cid = client.post("/conversations").json()["conversation_id"]
    r = client.post(f"/conversations/{cid}/messages", json={"text": "oi, quero cotar o completo"})
    assert r.status_code == 200 and r.json()["status"] == "answered"
    r = client.post(
        f"/conversations/{cid}/messages",
        json={"texts": ["tenho 35 anos", "onix 2022", "cep 01310-100, cpf 389.083.863-43"]},
    )
    body = r.json()
    assert body["status"] == "answered" and "R$ 209,90" in body["reply"]
    assert "quote" in body["skills_used"] and body["breaker"]["state"] == "closed"
    state = client.get(f"/conversations/{cid}").json()
    assert (
        state["last_quote"]["premio_mensal"] == 209.9 and state["collected"]["cep"] == "01***-***"
    )


def test_trace_via_http_e_valido_e_sem_pii(api):
    client, runtime = api
    cid = client.post("/conversations").json()["conversation_id"]
    client.post(
        f"/conversations/{cid}/messages",
        json={
            "text": "cpf 389.083.863-43, email a@b.com, 35 anos, onix 2022, cep 01310-100, completo"
        },
    )
    r = client.get(f"/conversations/{cid}/trace")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == len(data["events"]) > 5
    dump = json.dumps(data, ensure_ascii=False)
    assert find_pii(dump) == [] and "01310-100" not in dump
    kinds = [e["event"] for e in data["events"]]
    assert kinds[0] == "ingress" and "tool_call" in kinds and kinds[-1] == "outbound"


def test_404_com_shape_consistente(api):
    client, runtime = api
    for path in ["/conversations/nope", "/conversations/nope/trace"]:
        r = client.get(path)
        assert r.status_code == 404
        assert r.json() == {
            "error": "not_found",
            "message": "conversa não encontrada",
            "conversation_id": "nope",
        }
    r = client.post("/conversations/nope/messages", json={"text": "oi"})
    assert r.status_code == 404 and r.json()["error"] == "not_found"


def test_mensagem_vazia_ou_gigante_e_rejeitada(api):
    client, runtime = api
    cid = client.post("/conversations").json()["conversation_id"]
    assert client.post(f"/conversations/{cid}/messages", json={"text": ""}).status_code == 422
    assert client.post(f"/conversations/{cid}/messages", json={"text": "   "}).status_code == 422
    r = client.post(f"/conversations/{cid}/messages", json={"text": "x" * 10_001})
    assert r.status_code == 422 and r.json()["error"] == "invalid_request"
    assert client.post(f"/conversations/{cid}/messages", json={}).status_code == 422
    assert (
        client.post(
            f"/conversations/{cid}/messages", json={"text": "a", "texts": ["b"]}
        ).status_code
        == 422
    )


def test_excecao_nao_tratada_vira_500_sem_stacktrace_e_com_trace(api, tmp_path):
    client, runtime = api
    cid = client.post("/conversations").json()["conversation_id"]

    def boom(*a, **k):
        raise RuntimeError("kaboom secreto")

    runtime.orchestrator.handle = boom
    r = client.post(f"/conversations/{cid}/messages", json={"text": "oi"})
    assert r.status_code == 500
    assert r.json() == {
        "error": "internal_error",
        "message": "erro interno",
        "conversation_id": cid,
    }
    assert "kaboom" not in r.text
    events = JsonlSink(tmp_path).read(cid)
    assert (
        events and events[-1]["event"] == "error" and events[-1]["error"]["kind"] == "RuntimeError"
    )


def test_health_reflete_breaker_aberto(api):
    client, runtime = api
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["quote_api"]["breaker"]["state"] == "closed"
    assert h["llm"]["mode"] == "fake" and h["quote_api"]["catalog_loaded"] is True
    for _ in range(5):
        runtime.quotes.breaker.record_failure()
    assert client.get("/health").json()["quote_api"]["breaker"]["state"] == "open"


def test_duas_conversas_nao_misturam_estado_nem_trace(api, tmp_path):
    client, runtime = api
    a = client.post("/conversations").json()["conversation_id"]
    b = client.post("/conversations").json()["conversation_id"]
    client.post(
        f"/conversations/{a}/messages", json={"text": "completo, 35 anos, onix 2022, cep 01310-100"}
    )
    client.post(f"/conversations/{b}/messages", json={"text": "oi"})
    assert client.get(f"/conversations/{a}").json()["last_quote"] is not None
    assert client.get(f"/conversations/{b}").json()["last_quote"] is None
    assert (tmp_path / f"{a}.jsonl").exists() and (tmp_path / f"{b}.jsonl").exists()
    assert all(
        e["conversation_id"] == b for e in client.get(f"/conversations/{b}/trace").json()["events"]
    )
