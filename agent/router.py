"""Roteador de intenção por palavra-chave (fallback determinístico do roteador do modelo).
Vocabulário de detecção, como o dos gates: aqui se reconhece o que o lead quer, não se
decide o que a empresa oferece."""

from __future__ import annotations

import re
import unicodedata


def _strip(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def keyword_router(text: str, allowed: list[str]) -> list[str]:
    """Roteador de fallback por palavra-chave. Usado sem chave ou quando o roteador do
    modelo falha. Insulto e reclamação não são fora de escopo."""
    t = _strip(text)
    chosen: list[str] = []
    if re.search(
        r"\b(caro|salgad|barat|concorrent|pensar|esposa|marido|franquia (ta|esta) alta|"
        r"desconto|negoci|abaix|mais em conta|nao compensa|achei (caro|alto))",
        t,
    ):
        chosen.append("objection_handling")
    if re.search(
        r"\b(cobre|cobertura|coberturas|carencia|franquia|vigencia|pro.?rata|diferenca|"
        r"o que (ta|esta) inclu|inclui|roubo|furto|colisao|vidro|terceiro|carro reserva|assistencia)",
        t,
    ):
        chosen.append("coverage_explanation")
    if re.search(
        r"\b(seguro (residencial|de vida|saude|viagem|celular|moto)|sinistro|boleto|"
        r"cancelar|cancelamento|apolice|renovacao|segunda via|reembolso|batida (que )?tive|"
        r"acionar o seguro|abrir (um )?chamado)\b",
        t,
    ):
        chosen.append("out_of_scope")
    if not chosen or re.search(
        r"\b(cot|preco|valor|quanto|fica|custa|plano|contratar|fechar|seguro|carro|"
        r"veiculo|anos|cep|\d{4})",
        t,
    ):
        if "out_of_scope" not in chosen:
            chosen.append("quote")
    return [c for c in chosen if c in allowed] or [c for c in ("quote",) if c in allowed]
