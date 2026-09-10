import datetime as dt

import pytest

from agent.tools.quote_client import (
    InternalDefect,
    NeedsInput,
    Ok,
    QuoteClient,
    QuoteParams,
    RateLimited,
    Refused,
    Transient,
    normalize_cep,
    normalize_date,
)
from evals import fake_transport as ft

TODAY = dt.date(2026, 9, 10)


def make_client(*script: ft.Step, **kw) -> tuple[QuoteClient, ft.FakeQuoteTransport]:
    transport = ft.FakeQuoteTransport(list(script), **kw)
    return QuoteClient(transport, timeout_s=1.5), transport


PARAMS = QuoteParams("completo", 35, 2022, "01310-100", "2026-07-15")


# ---------------------------------------------------------------- classificação pelo corpo


def test_200_vira_ok_com_valores_permitidos():
    client, _ = make_client(
        ft.ok(premio_mensal=209.9, pro_rata={"valor_primeiro_pagamento": 115.1})
    )
    out = client.quote(PARAMS)
    assert isinstance(out, Ok)
    assert out.quote.premio_mensal == 209.9
    assert out.quote.allowed_amounts == {209.9, 3000.0, 115.1}
    assert out.latency_ms >= 0


def test_422_idade_e_recusa_real():
    client, _ = make_client(ft.refused("Idade acima do limite de aceitacao (75 anos)."))
    out = client.quote(PARAMS)
    assert isinstance(out, Refused) and out.kind == "idade"


def test_422_idade_fora_das_faixas_tambem_e_recusa_de_idade():
    client, _ = make_client(ft.refused("Idade fora das faixas aceitas."))
    out = client.quote(PARAMS)
    assert isinstance(out, Refused) and out.kind == "idade"


def test_422_veiculo_e_recusa_real():
    client, _ = make_client(ft.refused_vehicle())
    out = client.quote(PARAMS)
    assert isinstance(out, Refused) and out.kind == "veiculo"


def test_422_idade_do_veiculo_classifica_como_veiculo_nao_idade():
    client, _ = make_client(ft.refused("Idade do veiculo fora das faixas aceitas."))
    out = client.quote(PARAMS)
    assert isinstance(out, Refused) and out.kind == "veiculo"


def test_422_plano_inexistente_e_defeito_interno_nunca_recusa():
    client, _ = make_client(ft.plan_inexistente("turbo"))
    out = client.quote(PARAMS)
    assert isinstance(out, InternalDefect) and out.kind == "plano"


def test_422_schema_pydantic_e_defeito_interno():
    client, _ = make_client(ft.schema_error())
    out = client.quote(PARAMS)
    assert isinstance(out, InternalDefect) and out.kind == "schema"


def test_400_isoformat_e_defeito_interno():
    client, _ = make_client(ft.payload_invalido())
    out = client.quote(PARAMS)
    assert isinstance(out, InternalDefect) and out.kind == "payload"
    assert "isoformat" in out.detail


@pytest.mark.parametrize("status", [500, 502, 503, 504, 408])
def test_5xx_e_408_sao_transitorios(status):
    client, _ = make_client(status)
    out = client.quote(PARAMS)
    assert isinstance(out, Transient) and out.kind == "http" and out.http_status == status


def test_timeout_e_transitorio_com_latencia():
    client, _ = make_client(ft.TIMEOUT)
    out = client.quote(PARAMS)
    assert isinstance(out, Transient) and out.kind == "timeout" and out.http_status is None


def test_erro_de_conexao_e_transitorio():
    client, _ = make_client(ft.CONNECTION_ERROR)
    out = client.quote(PARAMS)
    assert isinstance(out, Transient) and out.kind == "connection"


def test_429_honra_retry_after():
    client, _ = make_client(ft.rate_limited(2))
    out = client.quote(PARAMS)
    assert isinstance(out, RateLimited) and out.retry_after_s == 2.0


@pytest.mark.parametrize("status", [401, 403])
def test_401_403_nunca_sao_transitorios(status):
    client, _ = make_client(ft.TransportResponse(status, {"detail": "nope"}))
    out = client.quote(PARAMS)
    assert isinstance(out, InternalDefect) and out.kind == "auth"


def test_200_com_corpo_quebrado_e_defeito_de_corpo():
    client, _ = make_client(ft.TransportResponse(200, {"foo": "bar"}))
    out = client.quote(PARAMS)
    assert isinstance(out, InternalDefect) and out.kind == "body"


# ---------------------------------------------------------------- pré-validação (zero rede)


def test_cep_invalido_nao_toca_a_rede():
    client, transport = make_client(ft.ok())
    out = client.validate(
        {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022, "cep": "abc"}, TODAY
    )
    assert isinstance(out, NeedsInput) and out.field == "cep"
    assert transport.call_count == 0


def test_cep_sem_hifen_e_aceito_e_normalizado():
    assert normalize_cep("07123456") == "07123-456"
    assert normalize_cep("07123-456") == "07123-456"
    assert normalize_cep(" 07123 456 ") == "07123-456"
    assert normalize_cep("0712345") is None
    assert normalize_cep("071234567") is None


def test_cep_sem_hifen_produz_agravo_na_logica_real():
    transport = ft.LocalLogicTransport(TODAY)
    client = QuoteClient(transport)
    params = client.validate(
        {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022, "cep": "07123456"}, TODAY
    )
    assert isinstance(params, QuoteParams)
    out = client.quote(params)
    assert isinstance(out, Ok)
    assert out.quote.multiplicadores["regiao"] == 1.3
    assert out.quote.premio_mensal == round(209.90 * 1.3, 2)


def test_data_brasileira_e_normalizada_para_iso():
    assert normalize_date("15/07/2026", TODAY) == "2026-07-15"
    assert normalize_date("15-07-2026", TODAY) == "2026-07-15"
    assert normalize_date("2026-07-15", TODAY) == "2026-07-15"
    assert normalize_date("15/07", TODAY) == "2027-07-15"  # já passou em 2026 → próximo ano
    assert normalize_date("15/10", TODAY) == "2026-10-15"
    assert normalize_date("", TODAY) is None
    assert normalize_date(None, TODAY) is None
    assert normalize_date("amanhã", TODAY) is False
    assert normalize_date("31/02/2026", TODAY) is False


def test_data_ausente_e_omitida_do_payload_nunca_string_vazia():
    p = QuoteParams("completo", 35, 2022, "01310-100", None)
    assert "data_inicio" not in p.payload()


def test_plano_desconhecido_vira_needs_input_com_opcoes():
    client, transport = make_client()
    out = client.validate(
        {"plano_id": "turbo", "idade": 35, "veiculo_ano": 2022, "cep": "01310-100"}, TODAY
    )
    assert isinstance(out, NeedsInput) and out.field == "plano_id"
    assert out.options == ("essencial", "completo", "premium")
    assert transport.call_count == 0


def test_plano_e_normalizado_para_minusculo_sem_acento():
    client, _ = make_client()
    out = client.validate(
        {"plano_id": " Completo ", "idade": "35", "veiculo_ano": "2022", "cep": "01310100"}, TODAY
    )
    assert isinstance(out, QuoteParams)
    assert out.plano_id == "completo" and out.idade == 35 and out.cep == "01310-100"


@pytest.mark.parametrize(
    "raw,field",
    [
        ({"idade": None}, "idade"),
        ({"idade": 250}, "idade"),
        ({"veiculo_ano": 1900}, "veiculo_ano"),
        ({"veiculo_ano": "não sei"}, "veiculo_ano"),
        ({"data_inicio": "semana que vem"}, "data_inicio"),
    ],
)
def test_campos_invalidos_pedem_input(raw, field):
    client, transport = make_client()
    base = {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022, "cep": "01310-100"}
    out = client.validate({**base, **raw}, TODAY)
    assert isinstance(out, NeedsInput) and out.field == field
    assert transport.call_count == 0


def test_validacao_nao_decide_elegibilidade():
    """Idade 80 e carro de 1990 passam pelo formato: quem recusa é a API (fonte de verdade)."""
    client, _ = make_client()
    out = client.validate(
        {"plano_id": "essencial", "idade": 80, "veiculo_ano": 1990, "cep": "01310-100"}, TODAY
    )
    assert isinstance(out, QuoteParams)


# ---------------------------------------------------------------- /planos


def test_planos_e_buscado_uma_vez_por_processo():
    client, transport = make_client()
    for _ in range(5):
        client.planos()
        client.validate(
            {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022, "cep": "01310-100"}, TODAY
        )
    assert transport.planos_calls == 1
    assert client.catalog() is not None


def test_planos_indisponivel_usa_fallback_estatico():
    transport = ft.FakeQuoteTransport(planos=ft.TransportTimeout("x"))
    client = QuoteClient(transport)
    assert client.planos() == ("essencial", "completo", "premium")
