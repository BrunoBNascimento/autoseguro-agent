"""Respostas seguras usadas quando o modelo viola uma regra duas vezes seguidas.
Apresentação determinística de dados que vieram da API — não é regra comercial."""

from __future__ import annotations

from agent.tools.quote_client import Quote

COVER_LABEL = {
    "colisao": "colisão",
    "roubo": "roubo",
    "furto": "furto",
    "terceiros": "danos a terceiros",
    "vidros": "vidros",
    "carro_reserva": "carro reserva",
    "assistencia_24h": "assistência 24h",
}


def fmt_brl(value: float) -> str:
    inteiro, cents = f"{value:.2f}".split(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    return f"R$ {inteiro},{cents}"


def render_quote(quote: Quote) -> str:
    covers = ", ".join(COVER_LABEL.get(c, c) for c in quote.coberturas)
    parts = [
        f"Sua cotação no plano {quote.plano_nome}: {fmt_brl(quote.premio_mensal)} por mês, "
        f"franquia de {fmt_brl(quote.franquia)}.",
        f"Coberturas: {covers}.",
    ]
    carencia = quote.carencia or {}
    if carencia.get("coberturas"):
        cov = " e ".join(COVER_LABEL.get(c, c) for c in carencia["coberturas"])
        parts.append(
            f"{cov.capitalize()} passam a valer {carencia.get('dias', 30)} dias após o início "
            "da vigência (carência)."
        )
    if quote.valor_primeiro_pagamento is not None and quote.primeiro_pagamento_pro_rata:
        pr = quote.primeiro_pagamento_pro_rata
        parts.append(
            f"Como a vigência começa no meio do mês, o primeiro pagamento é proporcional: "
            f"{fmt_brl(quote.valor_primeiro_pagamento)} por {pr.get('dias_cobrados')} dias; "
            "os meses seguintes são integrais."
        )
    parts.append("Quer seguir com essa opção ou tem alguma dúvida sobre as coberturas?")
    return " ".join(parts)


NO_QUOTE_SAFE = (
    "Só consigo te passar valores que saíram da nossa cotação oficial, então não vou "
    "estimar. Para cotar eu preciso do plano (Essencial, Completo ou Premium), da idade do "
    "condutor, do ano do veículo e do CEP de onde o carro dorme. Pode me passar?"
)
