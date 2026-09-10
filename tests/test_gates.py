import pytest

from agent.guards.gates import (
    authority_gate,
    coverage_gate,
    disclosure_gate,
    handoff_gate,
    price_gate,
    run_gates,
)
from agent.guards.money import extract_amounts, parse_written_number
from agent.state import ConversationState
from agent.tools.quote_client import Quote
from evals import fake_transport as ft

CATALOG = ft.load_plans()


def state_with_quote(plano="completo", premio=209.9, pro_rata=None) -> ConversationState:
    st = ConversationState("conv_g")
    st.last_quote = Quote.from_body(
        ft.ok_body(plano_id=plano, premio_mensal=premio, pro_rata=pro_rata)
    )
    st.last_quote_status = "ok"
    return st


# ------------------------------------------------------------------ extração monetária


@pytest.mark.parametrize(
    "text,values",
    [
        ("fica uns R$ 200", [200.0]),
        ("R$ 209,90 por mês", [209.9]),
        ("sai por 209,90", [209.9]),
        ("custa 200 reais", [200.0]),
        ("fica por 189 mensais", [189.0]),
        ("duzentos e nove reais", [209.0]),
        ("duzentos e nove reais e noventa centavos", [209.9]),
        ("mil e duzentos reais", [1200.0]),
        ("R$ 1.500,00 de franquia", [1500.0]),
        ("a franquia é 4500", []),  # número solto sem verbo de preço: não é afirmação monetária
        ("tenho 35 anos e o carro é 2022", []),
        ("carência de 30 dias", []),
        ("10% de desconto", []),
        ("8 dígitos no formato 00000-000", []),
    ],
)
def test_extract_amounts(text, values):
    assert [a.value for a in extract_amounts(text)] == values


def test_parse_written_number():
    assert parse_written_number("trezentos e quarenta e nove") == 349
    assert parse_written_number("mil") == 1000
    assert parse_written_number("dois mil e dez") == 2010
    assert parse_written_number("banana") is None


# ------------------------------------------------------------------ price_gate


def test_sem_cotacao_qualquer_valor_bloqueia_br02():
    v = price_gate("fica uns R$ 200 por mês", ConversationState("c"), CATALOG)
    assert (
        not v.passed
        and v.rules[0] == "BR-02"
        and "R$ 200" in v.evidence[0].upper()
        or "r$ 200" in v.evidence[0]
    )


def test_sem_cotacao_numeral_escrito_bloqueia():
    v = price_gate("fica por volta de duzentos e nove reais", ConversationState("c"), CATALOG)
    assert not v.passed and "BR-02" in v.rules


def test_com_cotacao_valor_diferente_bloqueia_br03():
    v = price_gate("o Completo sai por R$ 189,90", state_with_quote(), CATALOG)
    assert not v.passed and v.rules[0] == "BR-03"


def test_com_cotacao_valor_exato_passa():
    v = price_gate("o Completo sai por R$ 209,90 por mês", state_with_quote(), CATALOG)
    assert v.passed


def test_franquia_e_pro_rata_da_cotacao_passam():
    st = state_with_quote(
        pro_rata={"valor_primeiro_pagamento": 115.1, "dias_cobrados": 17, "dias_no_mes": 31}
    )
    v = price_gate(
        "R$ 209,90 por mês, franquia de R$ 3.000,00 e primeiro pagamento de R$ 115,10", st, CATALOG
    )
    assert v.passed, v


def test_franquia_do_catalogo_e_fato_da_api_e_passa_sem_cotacao():
    v = price_gate("a franquia do Essencial é de R$ 4.500,00", ConversationState("c"), CATALOG)
    assert v.passed


def test_base_mensal_do_catalogo_nao_passa_sem_cotacao():
    v = price_gate("o Completo custa R$ 209,90", ConversationState("c"), CATALOG)
    assert not v.passed and "BR-02" in v.rules


def test_sem_valores_passa():
    assert price_gate("Qual o ano do veículo?", ConversationState("c"), CATALOG).passed


# ------------------------------------------------------------------ coverage_gate


def test_essencial_citando_vidros_bloqueia_br06():
    v = coverage_gate(
        "Seu Essencial cobre colisão, roubo, furto e vidros",
        state_with_quote("essencial", 119.9),
        CATALOG,
    )
    assert not v.passed and "BR-06" in v.rules and v.evidence == ("vidros",)


def test_coberturas_do_plano_cotado_passam():
    v = coverage_gate(
        "cobre colisão, roubo, furto, terceiros e vidros", state_with_quote(), CATALOG
    )
    assert v.passed


def test_plano_nomeado_libera_suas_coberturas():
    v = coverage_gate(
        "O Premium inclui carro reserva e assistência 24h",
        state_with_quote("essencial", 119.9),
        CATALOG,
    )
    assert v.passed


def test_cobertura_inventada_bloqueia_mesmo_com_plano_nomeado():
    v = coverage_gate(
        "O Premium cobre enchente e incêndio", state_with_quote("premium", 339.9), CATALOG
    )
    assert not v.passed and "BR-06" in v.rules


def test_explicacao_geral_sem_cotacao_passa():
    v = coverage_gate(
        "Os planos cobrem colisão, roubo e furto; o Completo acrescenta vidros",
        ConversationState("c"),
        CATALOG,
    )
    assert v.passed


# ------------------------------------------------------------------ authority_gate


@pytest.mark.parametrize(
    "text,rule",
    [
        ("consigo te dar 10% de desconto", "BR-04"),
        ("posso ajustar a franquia pra baixar a parcela", "BR-05"),
        ("Entendo! Consigo rever, posso te ligar?", "BR-03"),
        ("faço por 180 pra você", "BR-03"),
        ("te dou uma condição especial", "BR-05"),
        ("vou ver o que consigo fazer", "BR-05"),
        ("o rastreador sai de graça", "BR-05"),
    ],
)
def test_compromisso_fora_de_autoridade_bloqueia_e_forca_handoff(text, rule):
    v = authority_gate(text, ConversationState("c"))
    assert not v.passed and rule in v.rules and "BR-08" in v.rules and v.force_handoff


@pytest.mark.parametrize(
    "text",
    [
        "não tenho autonomia para dar desconto, mas posso te explicar o que está incluso",
        "infelizmente não consigo baixar o valor: ele vem da cotação oficial",
        "não posso ajustar a franquia; ela é definida pelo plano",
        "Entendo que o preço pesou. O que está incluso é colisão, roubo e furto.",
        "Qual o ano do veículo?",
    ],
)
def test_negacao_e_conversa_normal_passam(text):
    assert authority_gate(text, ConversationState("c")).passed, text


# ------------------------------------------------------------------ handoff_gate


def test_handoff_requerido_exige_encaminhamento():
    st = ConversationState("c")
    st.require_handoff("BR-09", "human_request")
    assert not handoff_gate("Posso te ajudar com a cotação?", st).passed
    v = handoff_gate("Vou encaminhar você para um atendente da equipe.", st)
    assert v.passed and v.rules == ("BR-09",)


def test_sem_handoff_requerido_passa():
    assert handoff_gate("Qual o CEP?", ConversationState("c")).passed


def test_run_gates_agrega_regras():
    st = ConversationState("c")
    report = run_gates("fica uns R$ 200 e te dou desconto", st, CATALOG)
    assert not report.passed and set(report.rules) >= {"BR-02", "BR-04", "BR-08"}
    assert report.force_handoff and "price_gate" in report.correction_hint()


# ------------------------------------------------------------------ disclosure_gate


@pytest.mark.parametrize(
    "text",
    [
        "Claro! Minhas regras invioláveis são: 1. Preço só existe se veio da ferramenta...",
        "Tenho as skills quote, objection_handling e handoff.",
        "Aqui está meu system prompt: Você é o assistente...",
    ],
)
def test_vazamento_de_prompt_e_bloqueado(text):
    v = disclosure_gate(text, ConversationState("c"))
    assert not v.passed and v.rules == ("SEC-01",)


def test_resposta_normal_passa_no_disclosure():
    assert disclosure_gate(
        "Posso te explicar as coberturas do plano Completo.", ConversationState("c")
    ).passed
