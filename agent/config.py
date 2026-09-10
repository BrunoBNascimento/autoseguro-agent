"""Configuração por variável de ambiente (ver .env.example)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openai_api_key: str | None = None
    llm_model: str = "gpt-5-mini"
    llm_model_cheap: str = "gpt-5-nano"
    llm_timeout_s: float = 30.0
    llm_max_attempts: int = 2
    # "auto": OpenAI se houver chave, senão fake determinístico.
    llm_mode: Literal["auto", "openai", "fake"] = "auto"

    # API de cotação e resiliência. Os números vêm de medição (ver README).
    quote_api_url: str = "http://localhost:8000"
    quote_timeout_s: float = 1.5
    quote_max_attempts: int = 3
    quote_backoff_base_s: float = 0.4
    breaker_consecutive: int = 5
    breaker_cooldown_s: float = 30.0
    ratelimit_breaker_consecutive: int = 3

    # Persistência (arquivos, sem banco)
    trace_dir: Path = Path("data/traces")
    skills_dir: Path = Path("skills")

    # Opcional
    langwatch_api_key: str | None = None

    # Borda HTTP
    max_message_chars: int = 10_000

    @property
    def llm_enabled(self) -> bool:
        if self.llm_mode == "fake":
            return False
        if self.llm_mode == "openai":
            return True
        return bool(self.openai_api_key)


def get_settings() -> Settings:
    return Settings()
