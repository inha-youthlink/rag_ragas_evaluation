# RAG 없이 LLM에 질문만 보내는 baseline 호출 테스트 (OpenAI 클라이언트는 AsyncMock, 실제 호출 없음)
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ragas_eval.baseline_client.baseline_client import (
    BASELINE_RETRIEVER,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    call_baseline,
)
from ragas_eval.rag_client.rag_client import RagResult

MODEL = "test-baseline-model"
QUESTION = "가짜 질문"


DEFAULT_USAGE = object()


def fake_client(output_text="가짜 답변", usage=DEFAULT_USAGE, status="completed"):
    if usage is DEFAULT_USAGE:
        usage = SimpleNamespace(input_tokens=120, output_tokens=30)
    response = SimpleNamespace(output_text=output_text, usage=usage, status=status)
    return SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=response)))


def call(client):
    return asyncio.run(call_baseline(client, model=MODEL, question=QUESTION))


def test_sends_only_system_prompt_and_question():
    client = fake_client()

    call(client)

    client.responses.create.assert_awaited_once_with(
        model=MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": QUESTION},
        ],
    )


def test_maps_response_to_rag_result_without_retrieval():
    client = fake_client()

    result = call(client)

    assert isinstance(result, RagResult)
    assert result.answer == "가짜 답변"
    assert (result.retrieved_contexts, result.chunks) == ([], [])
    assert result.tokens == {"prompt_tokens": 120, "completion_tokens": 30}
    assert (result.chat_model, result.retriever, result.top_k) == (MODEL, BASELINE_RETRIEVER, None)
    assert BASELINE_RETRIEVER == "none"


def test_latency_is_measured_in_ms(monkeypatch):
    ticks = iter([10.0, 11.25])
    monkeypatch.setattr("ragas_eval.baseline_client.baseline_client.time.perf_counter", lambda: next(ticks))

    result = call(fake_client())

    assert result.latency_ms == 1250


def test_missing_usage_gives_empty_tokens():
    result = call(fake_client(usage=None))

    assert result.tokens == {}


@pytest.mark.parametrize("output_text", ["", "   \n"])
def test_empty_answer_fails(output_text):
    with pytest.raises(ValueError, match="비어 있음"):
        call(fake_client(output_text=output_text))


def test_incomplete_response_fails():
    with pytest.raises(ValueError, match="완료되지 않음"):
        call(fake_client(status="incomplete"))


def test_openai_error_propagates():
    client = fake_client()
    client.responses.create.side_effect = TimeoutError()

    with pytest.raises(TimeoutError):
        call(client)


def test_system_prompt_has_no_unfilled_placeholder():
    assert "{" not in SYSTEM_PROMPT
    assert PROMPT_VERSION
