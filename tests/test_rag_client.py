# RagResult 타입 검증과 /internal/pipeline 호출 테스트
import asyncio
import json
import re

import httpx
import pytest
from pydantic import ValidationError

from ragas_eval.rag_client.rag_client import RagResult, call_pipeline


def test_rag_payload_values_are_kept(rag_payload):
    trace = rag_payload["trace"]

    result = RagResult(
        answer=rag_payload["answer"],
        retrieved_contexts=[c["content"] for c in trace["chunks"]],
        chunks=trace["chunks"],
        latency_ms=trace["latency_ms"],
        tokens={"prompt_tokens": trace["prompt_tokens"], "completion_tokens": trace["completion_tokens"]},
    )

    assert result.chunks == trace["chunks"]
    assert result.latency_ms == trace["latency_ms"]
    assert result.tokens == {"prompt_tokens": 850, "completion_tokens": 40}


def test_rag_settings_are_kept():
    result = RagResult(
        answer="a", retrieved_contexts=[], chunks=[], chat_model="test-chat-model", retriever="vector", top_k=10
    )

    assert (result.chat_model, result.retriever, result.top_k) == ("test-chat-model", "vector", 10)


def test_offline_result_has_no_latency_tokens_or_rag_settings():
    result = RagResult(answer="정답", retrieved_contexts=["근거"], chunks=[{"content": "근거"}])

    assert result.latency_ms is None
    assert result.tokens == {}
    assert (result.chat_model, result.retriever, result.top_k) == (None, None, None)


def test_zero_top_k_fails():
    with pytest.raises(ValidationError):
        RagResult(answer="a", retrieved_contexts=[], chunks=[], top_k=0)


@pytest.mark.parametrize("latency_ms", [-1, 2_147_483_648])
def test_latency_outside_db_integer_range_fails(latency_ms):
    with pytest.raises(ValidationError):
        RagResult(answer="a", retrieved_contexts=[], chunks=[], latency_ms=latency_ms)


def chunk(content, score, index=0):
    return {
        "chunk_id": f"00000000-0000-0000-0000-00000000000{index}",
        "policy_no": "TEST-0001",
        "chunk_index": index,
        "chunk_type": "body",
        "content": content,
        "score": score,
    }


def call_with(payload, status_code=200, profile=None):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code, json=payload)

    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://rag") as client:
            return await call_pipeline(client, question="가짜 질문", profile=profile)

    return asyncio.run(call()), requests


def test_call_pipeline_posts_question_and_profile_with_debug(rag_payload):
    profile = {"age": 25, "region_code": "11000"}

    _, requests = call_with(rag_payload, profile=profile)

    (request,) = requests
    assert request.method == "POST"
    assert request.url.path == "/internal/pipeline"
    assert request.url.params["debug"] == "true"
    assert json.loads(request.content) == {"question": "가짜 질문", "profile": profile}


def test_call_pipeline_sends_empty_profile_by_default(rag_payload):
    _, requests = call_with(rag_payload)

    assert json.loads(requests[0].content)["profile"] == {}


def test_call_pipeline_maps_answer_and_trace(rag_payload):
    trace = rag_payload["trace"]

    result, _ = call_with(rag_payload)

    assert result.answer == rag_payload["answer"]
    assert result.retrieved_contexts == ["지원 대상: 만 19세 ~ 34세 청년"]
    assert result.chunks == trace["chunks"]
    assert result.latency_ms == 1200
    assert result.tokens == {"prompt_tokens": 850, "completion_tokens": 40}
    assert (result.chat_model, result.retriever, result.top_k) == ("test-chat-model", "vector", 10)


def test_retrieved_contexts_follow_score_desc_and_chunks_keep_original(rag_payload):
    chunks = [chunk("낮음", 0.2, 1), chunk("높음", 0.9, 2), chunk("중간", 0.5, 3)]
    payload = {**rag_payload, "trace": {**rag_payload["trace"], "chunks": chunks}}

    result, _ = call_with(payload)

    assert result.retrieved_contexts == ["높음", "중간", "낮음"]
    assert result.chunks == chunks


def test_null_trace_values_are_kept_empty(rag_payload):
    trace = {**rag_payload["trace"], "chunks": [], "latency_ms": None, "prompt_tokens": None, "top_k": None}

    result, _ = call_with({**rag_payload, "trace": trace})

    assert result.retrieved_contexts == []
    assert result.latency_ms is None
    assert result.tokens == {"completion_tokens": 40}
    assert result.top_k is None


@pytest.mark.parametrize("status_code", [404, 422, 500])
def test_http_error_raises(rag_payload, status_code):
    with pytest.raises(httpx.HTTPStatusError):
        call_with(rag_payload, status_code=status_code)


@pytest.mark.parametrize(
    "key", ["chunks", "latency_ms", "prompt_tokens", "completion_tokens", "chat_model", "retriever", "top_k"]
)
def test_missing_trace_key_fails(rag_payload, key):
    trace = {k: v for k, v in rag_payload["trace"].items() if k != key}

    with pytest.raises(ValueError, match=re.escape(f"trace.{key}:missing")):
        call_with({**rag_payload, "trace": trace})


@pytest.mark.parametrize(
    ("payload_patch", "loc"),
    [
        pytest.param({"answer": None}, "answer:string_type", id="answer-null"),
        pytest.param({"trace": None}, "trace:model_type", id="trace-null"),
    ],
)
def test_invalid_response_fails(rag_payload, payload_patch, loc):
    with pytest.raises(ValueError, match=loc):
        call_with({**rag_payload, **payload_patch})


def test_non_json_body_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>비밀-페이지</html>")

    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://rag") as client:
            return await call_pipeline(client, question="가짜 질문")

    with pytest.raises(ValueError, match="본문이 JSON이 아님") as exc_info:
        asyncio.run(call())

    assert "비밀-페이지" not in str(exc_info.value)
    assert exc_info.value.__context__ is None


def test_chunk_without_policy_no_fails(rag_payload):
    bad_chunk = {k: v for k, v in chunk("본문", 0.5).items() if k != "policy_no"}
    payload = {**rag_payload, "trace": {**rag_payload["trace"], "chunks": [bad_chunk]}}

    with pytest.raises(ValueError, match=r"trace\.chunks\.0\.policy_no:missing"):
        call_with(payload)


def test_chunk_without_content_fails_without_leaking_values(rag_payload):
    bad_chunk = {k: v for k, v in chunk("비밀-본문", 0.5).items() if k != "content"}
    payload = {**rag_payload, "trace": {**rag_payload["trace"], "chunks": [bad_chunk]}}

    with pytest.raises(ValueError, match=r"trace\.chunks\.0\.content:missing") as exc_info:
        call_with(payload)

    assert "비밀-본문" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize(
    ("key", "value", "loc"),
    [
        pytest.param("latency_ms", -1, "trace.latency_ms:greater_than_equal", id="negative-latency"),
        pytest.param("top_k", 0, "trace.top_k:greater_than_equal", id="zero-top-k"),
    ],
)
def test_out_of_range_trace_value_fails(rag_payload, key, value, loc):
    payload = {**rag_payload, "trace": {**rag_payload["trace"], key: value}}

    with pytest.raises(ValueError, match=re.escape(loc)):
        call_with(payload)
