"""Application configuration management."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables from default shell environment first.
load_dotenv()

# Load backend-local .env if present.
backend_env = Path(__file__).parent.parent.parent / ".env"
if backend_env.exists():
    load_dotenv(backend_env, override=False)

# Load optional HelloAgents .env if project is colocated.
helloagents_env = Path(__file__).parent.parent.parent.parent / "HelloAgents" / ".env"
if helloagents_env.exists():
    load_dotenv(helloagents_env, override=False)


class Settings(BaseSettings):
    """Strongly-typed runtime settings."""

    app_name: str = "智能旅行助手"
    app_version: str = "1.0.0"
    debug: bool = False

    host: str = "127.0.0.1"
    port: int = 8000

    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    amap_api_key: str = ""

    unsplash_access_key: str = os.getenv("UNSPLASH_ACCESS_KEY", "")
    unsplash_secret_key: str = os.getenv("UNSPLASH_SECRET_KEY", "")

    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen3.5-plus"
    # Dedicated model for judge/eval (separate from generation model).
    judge_model: str = "glm-4.7"
    llm_embedding_model: str = "text-embedding-3-small"
    rag_debug: bool = False
    schedule_use_mcp_route: bool = False
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/trip_planner"
    database_echo: bool = False

    @property
    def openai_api_key(self) -> str:
        """Backward-compatible alias for llm_api_key."""
        return self.llm_api_key

    @property
    def openai_base_url(self) -> str:
        """Backward-compatible alias for llm_base_url."""
        return self.llm_base_url

    @property
    def openai_model(self) -> str:
        """Backward-compatible alias for llm_model."""
        return self.llm_model

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

    def get_cors_origins_list(self) -> List[str]:
        """Split comma-separated CORS origins into normalized list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()


def get_settings() -> Settings:
    """Return singleton settings object."""
    return settings


def validate_config() -> bool:
    """Validate mandatory configuration and raise on critical errors."""
    errors: list[str] = []
    warnings: list[str] = []

    if not settings.amap_api_key:
        errors.append("AMAP_API_KEY is not configured")

    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or settings.llm_api_key
    if not llm_api_key:
        warnings.append("LLM_API_KEY / OPENAI_API_KEY is not configured; model features may be unavailable")

    if errors:
        error_msg = "Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)

    if warnings:
        print("\nConfiguration warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    return True


def print_config() -> None:
    """Print key runtime configuration (without exposing secrets)."""
    print(f"Application: {settings.app_name}")
    print(f"Version: {settings.app_version}")
    print(f"Server: {settings.host}:{settings.port}")
    print(f"AMAP API Key: {'configured' if settings.amap_api_key else 'missing'}")

    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or settings.llm_api_key
    llm_base_url = os.getenv("LLM_BASE_URL") or settings.llm_base_url
    llm_model = os.getenv("LLM_MODEL_ID") or settings.llm_model
    judge_model = os.getenv("JUDGE_MODEL") or settings.judge_model

    print(f"LLM API Key: {'configured' if llm_api_key else 'missing'}")
    print(f"LLM Base URL: {llm_base_url}")
    print(f"LLM Model: {llm_model}")
    print(f"Judge Model: {judge_model}")
    print(f"Log Level: {settings.log_level}")
