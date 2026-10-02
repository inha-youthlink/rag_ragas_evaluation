# 모드별 RAGAS 지표 채점 (검색 지표 3개 + Answer Relevancy + 할루시네이션 비교 지표 2개)
import asyncio
import logging
import math
from collections.abc import Mapping
from numbers import Real
from types import MappingProxyType
from typing import Annotated, Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field
from ragas.embeddings import OpenAIEmbeddings
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    FactualCorrectness,
    Faithfulness,
)

logger = logging.getLogger(__name__)

Score = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
METRIC_NAMES = (
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_relevancy",
    "factual_correctness",
    "reference_faithfulness",
)
# baseline은 검색을 하지 않으므로 검색 결과가 필요한 지표를 계산하지 않는다 (PRD "평가 지표" 모드별 표)
Mode = Literal["rag", "baseline", "offline"]
METRICS_BY_MODE = MappingProxyType(
    {
        "rag": METRIC_NAMES,
        "baseline": ("answer_relevancy", "factual_correctness", "reference_faithfulness"),
        "offline": METRIC_NAMES,
    }
)
MODES = tuple(METRICS_BY_MODE)
# AnswerRelevancy의 코사인 유사도 평균은 1.0000000000000002처럼 범위를 미세하게 넘을 수 있다
SCORE_TOLERANCE = 1e-9


class ScoreResult(BaseModel):
    """샘플 1건의 지표 6개. 실패한 지표는 None으로 두고 errors에 지표명 → 사유를 남긴다.
    모드에서 제외된 지표도 None이지만 errors에는 남기지 않는다."""

    model_config = ConfigDict(frozen=True)

    context_precision: Score | None = None
    context_recall: Score | None = None
    faithfulness: Score | None = None
    answer_relevancy: Score | None = None
    factual_correctness: Score | None = None
    reference_faithfulness: Score | None = None
    errors: dict[str, str] = Field(default_factory=dict)


def build_metrics(client: AsyncOpenAI, judge_model: str, embedding_model: str) -> dict[str, Any]:
    llm = llm_factory(judge_model, client=client)
    embeddings = OpenAIEmbeddings(client=client, model=embedding_model)
    return {
        "context_precision": ContextPrecision(llm=llm),
        "context_recall": ContextRecall(llm=llm),
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
        "factual_correctness": FactualCorrectness(llm=llm),
        "reference_faithfulness": Faithfulness(llm=llm, name="reference_faithfulness"),
    }


async def score_sample(
    metrics: Mapping[str, Any],
    *,
    question: str,
    answer: str,
    retrieved_contexts: list[str],
    reference: str,
    reference_contexts: list[str],
    mode: Mode = "rag",
) -> ScoreResult:
    if mode not in METRICS_BY_MODE:
        raise ValueError(f"알 수 없는 mode: {mode!r} (허용: {sorted(METRICS_BY_MODE)})")
    names = METRICS_BY_MODE[mode]
    missing = [name for name in names if name not in metrics]
    if missing:
        raise ValueError(f"지표 객체 누락: {missing}")
    inputs = {
        "context_precision": {"user_input": question, "retrieved_contexts": retrieved_contexts, "reference": reference},
        "context_recall": {"user_input": question, "retrieved_contexts": retrieved_contexts, "reference": reference},
        "faithfulness": {"user_input": question, "response": answer, "retrieved_contexts": retrieved_contexts},
        "answer_relevancy": {"user_input": question, "response": answer},
        "factual_correctness": {"response": answer, "reference": reference},
        # 검색 결과 대신 정책 원문 기준으로 충실도를 재서 검색이 없는 baseline과 같은 기준으로 비교한다
        "reference_faithfulness": {
            "user_input": question,
            "response": answer,
            "retrieved_contexts": reference_contexts,
        },
    }
    outcomes = await asyncio.gather(*(metrics[name].ascore(**inputs[name]) for name in names), return_exceptions=True)

    scores: dict[str, float | None] = {}
    errors: dict[str, str] = {}
    for name, outcome in zip(names, outcomes):
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
