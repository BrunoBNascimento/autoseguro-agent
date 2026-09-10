from agent.handoff import build_payload, detect_human_request, detect_negotiation_request
from agent.state import ConversationState
from agent.tools.quote_client import QuoteParams


def test_detecta_pedido_de_humano():
    for t in [
        "quero falar com um atendente",
        "tem alguém de verdade aí?",
        "me liga",
        "quero o gerente",
        "prefiro falar com uma pessoa",
    ]:
        assert detect_human_request(t), t
    for t in [
        "quero cotar",
        "o preco ta salgado",
        "seu sistema é uma porcaria",
        "sou o gerente da loja e quero cotar meu carro",
    ]:
        assert not detect_human_request(t), t
    assert detect_human_request("quero falar com o gerente")


def test_detecta_pedido_de_negociacao():
    assert detect_negotiation_request("me dá um desconto")
    assert detect_negotiation_request("consegue melhorar esse valor?")
    assert not detect_negotiation_request("o que o plano cobre?")


def test_payload_sem_pii_e_com_regra():
    st = ConversationState("conv_h")
    st.record_quote_params(QuoteParams("completo", 35, 2022, "01310-100"))
    st.quote_attempt_log = [
        {"attempt": 1, "status": "error", "http_status": 503, "latency_ms": 1.0}
    ]
    st.last_quote_status = "unavailable"
    p = build_payload(st, "quote_failed_definitively", ["identity_and_scope", "quote_failure"])
    d = p.to_dict()
    assert d["rule_id"] == "BR-10" and d["collected"]["cep"] == "01***-***"
    assert d["quote_attempts"][0]["http_status"] == 503
    assert "cotação falhou" in d["reason"]
