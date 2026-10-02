# GoldenSample 타입 검증 테스트
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ragas_eval.dataset.dataset import GoldenSample


def test_golden_record_parses_into_sample(golden_record):
    sample = GoldenSample.model_validate(golden_record)

    assert sample.sample_id == "single-000001"
    assert sample.reference_contexts == ["지원 대상: 만 19세 ~ 34세 청년"]
    assert sample.source_updated_at == datetime(2026, 9, 30, tzinfo=timezone(timedelta(hours=9)))
    assert sample.reviewed is True


def test_missing_reviewed_and_profile_use_defaults(golden_record):
    record = {k: v for k, v in golden_record.items() if k not in ("reviewed", "profile")}

    sample = GoldenSample.model_validate(record)

    assert sample.reviewed is False
    assert sample.profile == {}


def test_null_source_updated_at_is_allowed(golden_record):
    sample = GoldenSample.model_validate({**golden_record, "source_updated_at": None})

    assert sample.source_updated_at is None


def test_naive_source_updated_at_fails(golden_record):
    with pytest.raises(ValidationError):
        GoldenSample.model_validate({**golden_record, "source_updated_at": "2026-09-30T00:00:00"})


@pytest.mark.parametrize(
    "field",
    ["sample_id", "policy_no", "question", "ground_truth", "reference_contexts", "synthesizer_name", "source_updated_at"],
)
def test_missing_required_field_fails(golden_record, field):
    record = {k: v for k, v in golden_record.items() if k != field}

    with pytest.raises(ValidationError):
        GoldenSample.model_validate(record)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sample_id", "x" * 51),
        ("policy_no", "x" * 31),
        ("question", ""),
        ("ground_truth", ""),
        ("reference_contexts", []),
    ],
)
def test_invalid_value_fails(golden_record, field, value):
    with pytest.raises(ValidationError):
        GoldenSample.model_validate({**golden_record, field: value})


def test_assigning_field_fails(golden_record):
    sample = GoldenSample.model_validate(golden_record)

    with pytest.raises(ValidationError):
        sample.question = "바뀐 질문"
