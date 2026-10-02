# CLI 서브커맨드 인자 파싱 테스트
import pytest

from ragas_eval.cli import build_parser


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
