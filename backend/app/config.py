"""应用配置管理。"""

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

backend_env = Path(__file__).parent.parent.parent / ".env"
if backend_env.exists():
    load_dotenv(backend_env, override=False)

helloagents_env = Path(__file__).parent.parent.parent.parent / "HelloAgents" / ".env"
if helloagents_env.exists():
    load_dotenv(helloagents_env, override=False)


class Settings(BaseSettings):
    """应用配置。"""

    app_name: str = "智能旅行助手"
    app_version: str = "1.0.0"
    debug: bool = False

    host: str = "127.0.0.1"
    port: int = 8000

    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    amap_api_key: str = ""

    unsplash_access_key: str = os.getenv("UNSPLASH_ACCESS_KEY", "")
    unsplash_secret_key: str = os.getenv("UNSPLASH_SECRET_KEY", "")

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4"
    openai_embedding_model: str = "text-embedding-3-small"
    rag_debug: bool = False
    schedule_use_mcp_route: bool = False

    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/trip_planner"
    database_echo: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

    def get_cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()


def get_settings() -> Settings:
    return settings


def validate_config() -> bool:
    errors = []
    warnings = []

    if not settings.amap_api_key:
        errors.append("AMAP_API_KEY 未配置")

    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or settings.openai_api_key
    if not llm_api_key:
        warnings.append("LLM_API_KEY 或 OPENAI_API_KEY 未配置，LLM 功能可能无法使用")

    if errors:
        error_msg = "配置错误:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)

    if warnings:
        print("\n配置警告:")
        for warning in warnings:
            print(f"  - {warning}")

    return True


def print_config() -> None:
    print(f"应用名称: {settings.app_name}")
    print(f"版本: {settings.app_version}")
    print(f"服务地址: {settings.host}:{settings.port}")
    print(f"高德地图 API Key: {'已配置' if settings.amap_api_key else '未配置'}")

    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or settings.openai_api_key
    llm_base_url = os.getenv("LLM_BASE_URL") or settings.openai_base_url
    llm_model = os.getenv("LLM_MODEL_ID") or settings.openai_model

    print(f"LLM API Key: {'已配置' if llm_api_key else '未配置'}")
    print(f"LLM Base URL: {llm_base_url}")
    print(f"LLM Model: {llm_model}")
    print(f"日志级别: {settings.log_level}")
