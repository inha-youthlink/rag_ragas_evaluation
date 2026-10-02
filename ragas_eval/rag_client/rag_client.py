# RAG 서버 /internal/pipeline 호출 클라이언트
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PG_INTEGER_MAX = 2_147_483_647


class RagResult(BaseModel):
    """RAG 응답 중 평가에 쓰는 값. chunks는 trace.chunks 원본으로 samples.contexts에 저장한다."""

    model_config = ConfigDict(frozen=True)

    answer: str
    retrieved_contexts: list[str]
    chunks: list[dict[str, Any]]
    latency_ms: int | None = Field(default=None, ge=0, le=PG_INTEGER_MAX)
    tokens: dict[str, int] = Field(default_factory=dict)
    chat_model: str | None = None
    retriever: str | None = None
    top_k: int | None = Field(default=None, ge=1)
