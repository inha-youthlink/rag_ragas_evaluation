# 평가에 필요한 환경변수를 읽는 설정
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: SecretStr
    openai_api_key: SecretStr
    rag_base_url: str = "http://localhost:8000"

    gen_model: str
    judge_model: str
    embedding_model: str = "text-embedding-3-small"
    # run --baseline에서만 사용. RAG chat_model과 같은 모델로 둬야 공정 비교가 된다
    baseline_model: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
