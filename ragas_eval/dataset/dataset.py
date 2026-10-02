# golden jsonl 로드, reviewed 필터, source_updated_at 변경 검사
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class GoldenSample(BaseModel):
    """golden jsonl 한 줄. 길이 제한은 ragas_evaluation_samples 컬럼과 맞춘다."""

    model_config = ConfigDict(frozen=True)

    sample_id: str = Field(min_length=1, max_length=50)
    policy_no: str = Field(min_length=1, max_length=30)
    question: str = Field(min_length=1)
    ground_truth: str = Field(min_length=1)
    reference_contexts: list[str] = Field(min_length=1)
    synthesizer_name: str
    profile: dict[str, Any] = Field(default_factory=dict)
    source_updated_at: AwareDatetime | None
    reviewed: bool = False
