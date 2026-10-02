# Context Precision, Context Recall, Faithfulness, Answer Relevancy 채점
import asyncio
import logging
import math
from collections.abc import Mapping
from numbers import Real
from typing import Annotated, Any

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field
from ragas.embeddings import OpenAIEmbeddings
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

logger = logging.getLogger(__name__)

Score = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
METRIC_NAMES = ("context_precision", "context_recall", "faithfulness", "answer_relevancy")
# AnswerRelevancy의 코사인 유사도 평균은 1.0000000000000002처럼 범위를 미세하게 넘을 수 있다
SCORE_TOLERANCE = 1e-9


class ScoreResult(BaseModel):
    """샘플 1건의 지표 4개. 실패한 지표는 None으로 두고 errors에 지표명 → 사유를 남긴다."""

    model_config = ConfigDict(frozen=True)

    context_precision: Score | None = None
    context_recall: Score | None = None
    faithfulness: Score | None = None
    answer_relevancy: Score | None = None
    errors: dict[str, str] = Field(default_factory=dict)


def build_metrics(client: AsyncOpenAI, judge_model: str, embedding_model: str) -> dict[str, Any]:
    llm = llm_factory(judge_model, client=client)
    embeddings = OpenAIEmbeddings(client=client, model=embedding_model)
    return {
        "context_precision": ContextPrecision(llm=llm),
        "context_recall": ContextRecall(llm=llm),
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
    }


async def score_sample(
    metrics: Mapping[str, Any], question: str, answer: str, retrieved_contexts: list[str], reference: str
) -> ScoreResult:
    missing = [name for name in METRIC_NAMES if name not in metrics]
    if missing:
        raise ValueError(f"지표 객체 누락: {missing}")
    inputs = {
        "context_precision": {"user_input": question, "retrieved_contexts": retrieved_contexts, "reference": reference},
        "context_recall": {"user_input": question, "retrieved_contexts": retrieved_contexts, "reference": reference},
        "faithfulness": {"user_input": question, "response": answer, "retrieved_contexts": retrieved_contexts},
        "answer_relevancy": {"user_input": question, "response": answer},
    }
    outcomes = await asyncio.gather(
        *(metrics[name].ascore(**inputs[name]) for name in METRIC_NAMES), return_exceptions=True
    )

    scores: dict[str, float | None] = {}
    errors: dict[str, str] = {}
    for name, outcome in zip(METRIC_NAMES, outcomes):
        # 취소·종료 신호는 채점 실패가 아니므로 그대로 올린다
        if isinstance(outcome, BaseException) and not isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, Exception):
            # 예외 메시지에는 프롬프트·응답 내용이 섞일 수 있어 클래스명만 남긴다
            value, error = None, type(outcome).__name__
        else:
            value, error = _check_value(getattr(outcome, "value", None))
        scores[name] = value
        if error:
            errors[name] = error
            logger.warning("채점 실패: metric=%s error=%s", name, error)
    return ScoreResult(**scores, errors=errors)


def _check_value(value: Any) -> tuple[float | None, str | None]:
    """0점과 실패를 구분하기 위해 0 ~ 1 실수만 점수로 인정한다."""
    if isinstance(value, bool) or not isinstance(value, Real):
        return None, "InvalidValue"
    if math.isnan(value):
        return None, "NaN"
    if not -SCORE_TOLERANCE <= value <= 1 + SCORE_TOLERANCE:
        return None, "InvalidValue"
    return min(max(float(value), 0.0), 1.0), None
