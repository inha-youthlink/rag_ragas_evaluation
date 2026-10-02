# CLI 서브커맨드 인자 파싱 테스트
import pytest

from ragas_eval.generate import generate
from ragas_eval.runner import runner
from ragas_eval.cli import build_parser, main


def test_generate_uses_default_options():
    args = build_parser().parse_args(["generate"])

    assert args.command == "generate"
    assert args.testset_size == 100
    assert args.out == "datasets/golden_candidates.jsonl"


def test_run_parses_golden_and_repeat():
    args = build_parser().parse_args(["run", "--golden", "datasets/golden_v1.jsonl", "--repeat", "3"])

    assert args.command == "run"
    assert args.golden == "datasets/golden_v1.jsonl"
    assert args.repeat == 3


def test_run_requires_golden():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run"])


def test_run_offline_defaults_to_false():
    args = build_parser().parse_args(["run", "--golden", "datasets/golden_v1.jsonl"])

    assert args.offline is False


def test_run_parses_offline_flag():
    args = build_parser().parse_args(["run", "--golden", "datasets/golden_v1.jsonl", "--offline"])

    assert args.offline is True


def test_main_passes_offline_to_runner(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "run", lambda **kwargs: calls.append(kwargs))

    main(["run", "--golden", "datasets/golden_v1.jsonl", "--offline"])

    assert calls == [{"golden_path": "datasets/golden_v1.jsonl", "repeat": 1, "offline": True}]


def test_main_prints_generate_counts(monkeypatch, capsys):
    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        return generate.GenerateSummary(written=3, dropped=1)

    monkeypatch.setattr(generate, "generate", fake_generate)

    main(["generate", "--testset-size", "10", "--out", "datasets/candidates.jsonl"])

    out = capsys.readouterr().out
    assert calls == [{"testset_size": 10, "out_path": "datasets/candidates.jsonl"}]
    assert "3건" in out and "1건" in out and "datasets/candidates.jsonl" in out
