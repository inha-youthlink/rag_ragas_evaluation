# RagResult 타입 검증 테스트
import pytest
from pydantic import ValidationError

from ragas_eval.rag_client.rag_client import RagResult


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
