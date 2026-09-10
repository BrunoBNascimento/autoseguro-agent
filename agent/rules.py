"""Ids das regras de negócio, lidos de `skills/business_rules.yaml`. O texto das regras
vive no arquivo; aqui só o registro para validação e trace."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

DEFAULT_RULES_PATH = Path("skills") / "business_rules.yaml"


@dataclass(frozen=True)
class BusinessRule:
    id: str
    text: str
    enforced_by: str


@lru_cache(maxsize=4)
def load_rules(path: Path | str = DEFAULT_RULES_PATH) -> dict[str, BusinessRule]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    rules = {}
    for rule_id, spec in (data.get("rules") or {}).items():
        rules[str(rule_id)] = BusinessRule(
            str(rule_id), str(spec["text"]), str(spec["enforced_by"])
        )
    if not rules:
        raise ValueError(f"nenhuma regra em {path}")
    return rules


def rule_ids(path: Path | str = DEFAULT_RULES_PATH) -> frozenset[str]:
    return frozenset(load_rules(path))
