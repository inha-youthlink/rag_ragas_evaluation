# Context Precision, Context Recall, Faithfulness, Answer Relevancy 채점
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Score = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class ScoreResult(BaseModel):
    """샘플 1건의 지표 4개. 실패한 지표는 None으로 두고 errors에 지표명 → 사유를 남긴다."""

    model_config = ConfigDict(frozen=True)

    context_precision: Score | None = None
    context_recall: Score | None = None
    faithfulness: Score | None = None
    answer_relevancy: Score | None = None
    errors: dict[str, str] = Field(default_factory=dict)
