"""Sanitização de PII por entidade — não é moderação de conteúdo.

Insulto, reclamação e objeção são conteúdo relevante e passam intactos. Só dado sensível
é substituído por um marcador. Duas políticas:

- `LLM_CONTEXT`: CPF, e-mail, telefone e placa mascarados; CEP em claro (a cotação
  precisa dele para o agravo regional).
- `PERSISTENCE`: o mesmo, mais CEP reduzido ao prefixo (`01***-***`) — os 2 primeiros
  dígitos bastam para auditar o multiplicador sem guardar o endereço.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Policy(StrEnum):
    LLM_CONTEXT = "llm_context"
    PERSISTENCE = "persistence"


CPF = "[CPF]"
EMAIL = "[EMAIL]"
TELEFONE = "[TELEFONE]"
PLACA = "[PLACA]"

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CPF_RE = re.compile(r"(?<!\d)(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})[-.\s]?(\d{2})(?!\d)")
# DDD obrigatório: sem ele, 8 dígitos seriam indistinguíveis de um CEP sem hífen.
_PHONE_RE = re.compile(
    r"(?<![\w])(?:\+?55[\s.-]?)?\(?0?\d{2}\)?[\s.-]?(?:9[\s.-]?\d{4}|[2-5]\d{3})[\s.-]?\d{4}(?!\d)"
)
_PLATE_RE = re.compile(r"\b(?:[A-Za-z]{3}-?\d{4}|[A-Za-z]{3}\d[A-Za-z]\d{2})\b")
_CEP_RE = re.compile(r"(?<!\d)(\d{5})-?(\d{3})(?!\d)")

_PII_KEYS = {
    "cpf": CPF,
    "email": EMAIL,
    "e-mail": EMAIL,
    "telefone": TELEFONE,
    "phone": TELEFONE,
    "whatsapp": TELEFONE,
    "placa": PLACA,
}
# Identificadores técnicos nunca são PII; sanitizá-los quebraria a árvore do trace.
_ID_KEYS = {
    "conversation_id",
    "message_id",
    "span_id",
    "parent_span_id",
    "trace_id",
    "tool_call_id",
    "ts",
    "created_at",
    "model",
    "event",
    "status",
}


def cpf_is_valid(digits: str) -> bool:
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    nums = [int(d) for d in digits]
    for size in (9, 10):
        total = sum((size + 1 - i) * v for i, v in enumerate(nums[:size]))
        check = (total * 10) % 11
        check = 0 if check == 10 else check
        if check != nums[size]:
            return False
    return True


def cep_prefix(cep: str | None) -> str | None:
    if cep is None:
        return None
    if "*" in str(cep):  # já mascarado — a sanitização é idempotente
        return str(cep)
    digits = re.sub(r"\D", "", str(cep))
    if len(digits) != 8:
        return "*****-***"
    return f"{digits[:2]}***-***"


@dataclass(frozen=True)
class SanitizeResult:
    text: str
    entities: tuple[str, ...]

    @property
    def found(self) -> bool:
        return bool(self.entities)


def sanitize_text(text: str, policy: Policy = Policy.LLM_CONTEXT) -> SanitizeResult:
    found: list[str] = []

    def mark(label: str) -> None:
        if label not in found:
            found.append(label)

    def cpf_sub(m: re.Match[str]) -> str:
        digits = "".join(m.groups())
        if not cpf_is_valid(digits):
            return m.group(0)
        mark("cpf")
        return CPF

    def simple_sub(label: str, marker: str):
        def _sub(m: re.Match[str]) -> str:
            mark(label)
            return marker

        return _sub

    out = _EMAIL_RE.sub(simple_sub("email", EMAIL), text)
    out = _CPF_RE.sub(cpf_sub, out)
    out = _PHONE_RE.sub(simple_sub("telefone", TELEFONE), out)
    out = _PLATE_RE.sub(simple_sub("placa", PLACA), out)
    if policy is Policy.PERSISTENCE:

        def cep_sub(m: re.Match[str]) -> str:
            mark("cep")
            return f"{m.group(1)[:2]}***-***"

        out = _CEP_RE.sub(cep_sub, out)
    return SanitizeResult(out, tuple(found))


def sanitize_obj(obj: Any, policy: Policy = Policy.PERSISTENCE, _key: str | None = None) -> Any:
    """Aplica a política a toda string de um dict/lista, recursivamente."""
    if isinstance(obj, str):
        if _key and _key.lower() in _ID_KEYS:
            return obj
        if _key and _key.lower() in _PII_KEYS:
            return _PII_KEYS[_key.lower()]
        if _key and _key.lower() == "cep" and policy is Policy.PERSISTENCE:
            return cep_prefix(obj)
        return sanitize_text(obj, policy).text
    if isinstance(obj, Mapping):
        return {str(k): sanitize_obj(v, policy, str(k)) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [sanitize_obj(v, policy) for v in obj]
    return obj


def pseudonym(conversation_id: str, name: str) -> str:
    """Pseudônimo estável por conversa; conversas diferentes dão pseudônimos diferentes."""
    digest = hashlib.sha256(f"{conversation_id}:{name.strip().lower()}".encode()).hexdigest()
    return f"lead_{digest[:4]}"


def find_pii(text: str) -> list[str]:
    """Rótulos de PII sensível presentes em claro (CPF válido, e-mail, telefone, placa).
    Usado pelos testes anti-vazamento sobre o trace."""
    labels: list[str] = []
    if _EMAIL_RE.search(text):
        labels.append("email")
    if any(cpf_is_valid("".join(m.groups())) for m in _CPF_RE.finditer(text)):
        labels.append("cpf")
    if _PHONE_RE.search(text):
        labels.append("telefone")
    if _PLATE_RE.search(text):
        labels.append("placa")
    return labels
