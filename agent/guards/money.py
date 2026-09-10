"""Extração de expressões monetárias em pt-BR para o gate de preço.

Cobre `R$ 209,90`, `209,90`, `200 reais`, `por 209`, `fica uns 200` e numerais escritos
(`duzentos e nove reais`). É regex: evadível por construção, e o README diz isso. O gate é
a última linha; a primeira é a tool sem parâmetro de preço.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_UNITS = {
    "zero": 0,
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "quatorze": 14,
    "catorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
    "sessenta": 60,
    "setenta": 70,
    "oitenta": 80,
    "noventa": 90,
    "cem": 100,
    "cento": 100,
    "duzentos": 200,
    "trezentos": 300,
    "quatrocentos": 400,
    "quinhentos": 500,
    "seiscentos": 600,
    "setecentos": 700,
    "oitocentos": 800,
    "novecentos": 900,
}
_WORD = "|".join(sorted(_UNITS, key=len, reverse=True)) + "|mil"
_WRITTEN_RE = re.compile(
    rf"\b((?:(?:{_WORD})\b(?:\s+e\s+|\s+)?)+)(?:reais|real|conto|pila)\b"
    rf"(?:\s+e\s+((?:(?:{_WORD})\b(?:\s+e\s+|\s+)?)+)centavos)?"
)
_RS_RE = re.compile(r"r\$\s?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?")
_DECIMAL_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d+),(\d{2})(?![\d])")
_REAIS_RE = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d{2,6})\s*(?:reais|real|conto|pila|mangos)\b"
)
_PRICE_VERB_RE = re.compile(
    r"\b(?:por|fica(?:ria|m)?|sai|saem|custa(?:m|ria)?|valor de|a partir de|em torno de|"
    r"uns|cerca de|mais ou menos|aproximadamente|na faixa de|em media|de)\s+"
    r"(?:uns\s+|cerca de\s+|em torno de\s+|aproximadamente\s+)?(\d{2,3}(?:\.\d{3})+|\d{2,6})"
    r"(?!\d|[,.]\d)(?!\s*(?:%|dias?|anos?|meses|km|cc|cv|horas?|h\b|minutos?|vezes|parcelas?|x\b|"
    r"digitos?|dígitos?|caracteres|litros?|mil\b))"
)
_YEAR_RANGE = (1950, 2100)


@dataclass(frozen=True)
class Amount:
    value: float
    raw: str
    kind: str


def _strip(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def _to_float(inteiro: str, cents: str | None) -> float:
    value = float(inteiro.replace(".", ""))
    if cents:
        value += int(cents.ljust(2, "0")) / 100
    return round(value, 2)


def parse_written_number(words: str) -> int | None:
    total = 0
    current = 0
    seen = False
    for tok in re.split(r"\s+", words.strip()):
        if tok in ("e", ""):
            continue
        if tok == "mil":
            current = (current or 1) * 1000
            total += current
            current = 0
            seen = True
            continue
        if tok not in _UNITS:
            return None
        current += _UNITS[tok]
        seen = True
    return total + current if seen else None


def extract_amounts(text: str) -> list[Amount]:
    t = _strip(text)
    found: dict[tuple[int, int], Amount] = {}

    def add(m: re.Match[str], value: float, kind: str) -> None:
        span = m.span()
        if any(s < span[1] and span[0] < e for (s, e) in found):
            return
        found[span] = Amount(value, m.group(0).strip(), kind)

    for m in _RS_RE.finditer(t):
        add(m, _to_float(m.group(1), m.group(2)), "rs")
    for m in _WRITTEN_RE.finditer(t):
        inteiro = parse_written_number(m.group(1))
        if inteiro is None:
            continue
        cents = parse_written_number(m.group(2)) if m.group(2) else 0
        add(m, round(inteiro + (cents or 0) / 100, 2), "written")
    for m in _DECIMAL_RE.finditer(t):
        add(m, _to_float(m.group(1), m.group(2)), "decimal")
    for m in _REAIS_RE.finditer(t):
        add(m, _to_float(m.group(1), None), "reais")
    for m in _PRICE_VERB_RE.finditer(t):
        value = _to_float(m.group(1), None)
        if _YEAR_RANGE[0] <= value <= _YEAR_RANGE[1] or value < 10:
            continue
        add(m, value, "verb")
    return [found[k] for k in sorted(found)]
