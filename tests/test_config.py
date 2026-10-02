# 환경변수 설정(Settings) 필수 값과 기본값 테스트
import pytest
from pydantic import ValidationError

from ragas_eval.config import Settings

REQUIRED_ENV = {
    "DATABASE_URL": "postgresql://user:pw@localhost:5432/test_db",
    "OPENAI_API_KEY": "test-key",
    "GEN_MODEL": "test-gen-model",
    "JUDGE_MODEL": "test-judge-model",
}


@pytest.fixture
def required_env(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("BASELINE_MODEL", raising=False)


def test_baseline_model_defaults_to_none(required_env):
    settings = Settings(_env_file=None)

    assert settings.baseline_model is None


def test_baseline_model_is_read_from_env(required_env, monkeypatch):
    monkeypatch.setenv("BASELINE_MODEL", "test-baseline-model")

    settings = Settings(_env_file=None)

    assert settings.baseline_model == "test-baseline-model"


@pytest.mark.parametrize("key", list(REQUIRED_ENV))
def test_missing_required_value_fails(required_env, monkeypatch, key):
    monkeypatch.delenv(key)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
