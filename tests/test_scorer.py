# ScoreResult 타입 검증 테스트
import pytest
from pydantic import ValidationError

from ragas_eval.scorer.scorer import ScoreResult


def test_score_result_keeps_four_metrics():
    result = ScoreResult(context_precision=0.9, context_recall=1.0, faithfulness=0.0, answer_relevancy=0.75)

    assert result.model_dump(exclude={"errors"}) == {
        "context_precision": 0.9,
        "context_recall": 1.0,
        "faithfulness": 0.0,
        "answer_relevancy": 0.75,
    }


def test_failed_metric_is_none_with_error():
    result = ScoreResult(faithfulness=None, errors={"faithfulness": "TimeoutError"})

    assert result.faithfulness is None
    assert result.context_precision is None
    assert result.errors == {"faithfulness": "TimeoutError"}


@pytest.mark.parametrize("value", [-0.01, 1.01, float("nan"), float("inf")])
def test_out_of_range_or_nan_score_fails(value):
    with pytest.raises(ValidationError):
        ScoreResult(faithfulness=value)
