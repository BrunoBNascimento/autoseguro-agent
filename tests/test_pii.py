import itertools

import pytest

from agent.security.pii import (
    Policy,
    cep_prefix,
    cpf_is_valid,
    find_pii,
    pseudonym,
    sanitize_obj,
    sanitize_text,
)


def test_exemplo_do_dataset():
    r = sanitize_text("Cpf 389.083.863-43, tenho 35 anos, cep 26703-384")
    assert r.text == "Cpf [CPF], tenho 35 anos, cep 26703-384"
    assert r.entities == ("cpf",)


def test_seis_permutacoes_e_duas_capitalizacoes():
    bits = ["CPF 389.083.863-43", "tenho 35 anos", "CEP 26703-384"]
    for perm in itertools.permutations(bits):
        for text in (", ".join(perm), ", ".join(perm).capitalize()):
            r = sanitize_text(text)
            assert "389" not in r.text and "[CPF]" in r.text
            assert "35 anos" in r.text.lower() and "26703-384" in r.text


def test_cpf_sem_pontuacao_e_mascarado():
    assert sanitize_text("meu cpf 38908386343 ta ai").text == "meu cpf [CPF] ta ai"


def test_onze_digitos_com_dv_invalido_nao_e_cpf():
    assert not cpf_is_valid("12345678901")
    assert sanitize_text("pedido 12345678901").text == "pedido 12345678901"


@pytest.mark.parametrize(
    "phone", ["(11) 98765-4321", "+55 11 98765-4321", "11987654321", "11 3333-4444"]
)
def test_telefones_sao_mascarados(phone):
    r = sanitize_text(f"me liga no {phone} depois")
    assert r.text == "me liga no [TELEFONE] depois", r.text
    assert "telefone" in r.entities


def test_email_e_mascarado():
    r = sanitize_text(
        "meu email é ursula_souza12@gmail.com e o whats é esse mesmo +55 47 91234-5678"
    )
    assert r.text == "meu email é [EMAIL] e o whats é esse mesmo [TELEFONE]"


@pytest.mark.parametrize("plate", ["ABC1D23", "ABC-1234", "abc1d23"])
def test_placas_mercosul_e_antiga(plate):
    assert sanitize_text(f"a placa é {plate} se precisar").text == "a placa é [PLACA] se precisar"


def test_ano_idade_e_valores_nunca_sao_mascarados():
    text = "tenho 35 anos, o carro é 2022, o premio é R$ 209,90 e a franquia 4500"
    assert sanitize_text(text).text == text
    assert sanitize_text(text, Policy.PERSISTENCE).text == text


def test_insulto_sai_byte_a_byte_identico():
    text = "seu sistema é uma porcaria, vocês são uns ladrões"
    assert sanitize_text(text).text == text
    assert sanitize_text(text, Policy.PERSISTENCE).text == text


def test_objecao_sai_intacta():
    for text in ["o preco ta salgado", "a franquia ta alta", "vi mais barato na concorrente"]:
        assert sanitize_text(text).text == text


def test_cep_em_claro_no_contexto_e_prefixo_na_persistencia():
    text = "moro no cep 07123-456, o carro dorme na rua"
    assert sanitize_text(text, Policy.LLM_CONTEXT).text == text
    r = sanitize_text(text, Policy.PERSISTENCE)
    assert r.text == "moro no cep 07***-***, o carro dorme na rua"
    assert "cep" in r.entities
    assert sanitize_text("cep 07123456", Policy.PERSISTENCE).text == "cep 07***-***"


def test_cep_prefix():
    assert cep_prefix("01310-100") == "01***-***"
    assert cep_prefix("07123456") == "07***-***"
    assert cep_prefix("abc") == "*****-***"
    assert cep_prefix(None) is None


def test_sanitize_obj_recursivo_com_chaves_conhecidas():
    obj = {
        "input": {"cep": "01310-100", "idade": 35, "nome": "Ana"},
        "msgs": ["cpf 389.083.863-43", {"email": "x@y.com"}],
        "placa": "ABC1D23",
    }
    out = sanitize_obj(obj)
    assert out == {
        "input": {"cep": "01***-***", "idade": 35, "nome": "Ana"},
        "msgs": ["cpf [CPF]", {"email": "[EMAIL]"}],
        "placa": "[PLACA]",
    }


def test_pseudonimo_estavel_por_conversa_e_diferente_entre_conversas():
    a1 = pseudonym("conv_1", "Ana Silva")
    assert a1 == pseudonym("conv_1", "ana silva ")
    assert a1 != pseudonym("conv_2", "Ana Silva")
    assert a1.startswith("lead_") and len(a1) == 9


def test_find_pii_detecta_vazamento():
    assert find_pii("cpf 389.083.863-43") == ["cpf"]
    assert find_pii("tenho 35 anos e o carro é 2022") == []
    assert set(find_pii("x@y.com (11) 98765-4321 ABC1D23")) == {"email", "telefone", "placa"}


def test_ids_tecnicos_nao_sao_sanitizados():
    obj = {"conversation_id": "conv_123456789012", "span_id": "sp_12345678", "cep": "12345678"}
    out = sanitize_obj(obj)
    assert out["conversation_id"] == "conv_123456789012" and out["span_id"] == "sp_12345678"
    assert out["cep"] == "12***-***"


def test_new_id_nunca_tem_quatro_digitos_seguidos():
    import re

    from agent.tracing.schema import new_id

    assert all(not re.search(r"\d{4}", new_id("x")) for _ in range(500))
