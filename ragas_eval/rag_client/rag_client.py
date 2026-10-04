# RAG 서버 /internal/pipeline 호출 클라이언트
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

PG_INTEGER_MAX = 2_147_483_647
PIPELINE_PATH = "/internal/pipeline"
# 검색 + LLM 생성까지 기다리므로 httpx 기본값(5초)보다 길게 둔다
RAG_TIMEOUT_SECONDS = 120.0
CONNECT_TIMEOUT_SECONDS = 5.0
# RAG trace.tokens 키 → samples.metadata.tokens 키
TOKEN_KEYS = {"prompt": "prompt_tokens", "completion": "completion_tokens"}


class RagResult(BaseModel):
    """RAG 응답 중 평가에 쓰는 값.

    chunks는 samples.contexts에 저장하는 채점 근거([{"content": ...}])이고,
    retrieved_chunks는 trace.retrieved_chunks 원본으로 samples.metadata에 남긴다.
    """

    model_config = ConfigDict(frozen=True)

    answer: str
    retrieved_contexts: list[str]
    chunks: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: int | None = Field(default=None, ge=0, le=PG_INTEGER_MAX)
    tokens: dict[str, int] = Field(default_factory=dict)
    chat_model: str | None = None
    retriever: str | None = None
    top_k: int | None = Field(default=None, ge=1)


class _RetrievedChunk(BaseModel):
    chunk_id: str
    policy_no: str
    score: float


class _Latency(BaseModel):
    total: int | None = Field(ge=0, le=PG_INTEGER_MAX)


class _Tokens(BaseModel):
    prompt: int | None
    completion: int | None


class _Trace(BaseModel):
    """PRD "RAG 연동 계약"의 trace 필수 키. 키는 반드시 있어야 하고 값은 null을 허용한다."""

    contexts: list[str]
    retrieved_chunks: list[_RetrievedChunk]
    latency_ms: _Latency
    tokens: _Tokens
    chat_model: str | None
    retriever: str | None
    top_k: int | None = Field(ge=1)


class _PipelineResponse(BaseModel):
    answer: str
    trace: _Trace


def make_client(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(RAG_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS))


async def call_pipeline(
    client: httpx.AsyncClient, question: str, profile: Mapping[str, Any] | None = None
) -> RagResult:
    response = await client.post(PIPELINE_PATH, json={"question": question, "profile": dict(profile or {})})
    response.raise_for_status()
    # 응답 본문이 로그·traceback에 남지 않도록 위치·종류만 남기고, except 밖에서 던져 __context__도 끊는다
    try:
        return _to_result(response.json())
    except ValidationError as e:
        details = ", ".join(
            f"{'.'.join(map(str, err['loc'])) or '(응답 전체)'}:{err['type']}" for err in e.errors(include_input=False)
        )
    except ValueError:
        details = "본문이 JSON이 아님"
    raise ValueError(f"RAG 응답 계약 위반: {details}")


def _to_result(payload: Any) -> RagResult:
    parsed = _PipelineResponse.model_validate(payload)
    trace = parsed.trace
    # contexts는 RAG가 LLM에 넘긴 근거 순서(검색 순위) 그대로 쓴다
    return RagResult(
        answer=parsed.answer,
        retrieved_contexts=trace.contexts,
        chunks=[{"content": c} for c in trace.contexts],
        retrieved_chunks=payload["trace"]["retrieved_chunks"],
        latency_ms=trace.latency_ms.total,
        tokens={key: v for src, key in TOKEN_KEYS.items() if (v := getattr(trace.tokens, src)) is not None},
        chat_model=trace.chat_model,
        retriever=trace.retriever,
        top_k=trace.top_k,
    )
