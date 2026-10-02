# generate, run 서브커맨드를 정의하는 CLI
import argparse
from collections.abc import Sequence

from ragas_eval import generate, runner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ragas_eval")
    sub = parser.add_subparsers(dest="command", required=True)

    generate_parser = sub.add_parser("generate", help="policy 테이블로 데이터셋 후보 생성")
    generate_parser.add_argument("--testset-size", type=int, default=100)
    generate_parser.add_argument("--out", default="datasets/golden_candidates.jsonl")

    run_parser = sub.add_parser("run", help="확정 데이터셋으로 평가 실행")
    run_parser.add_argument("--golden", required=True)
    run_parser.add_argument("--repeat", type=int, default=1)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.command == "generate":
        generate.generate(testset_size=args.testset_size, out_path=args.out)
    elif args.command == "run":
        runner.run(golden_path=args.golden, repeat=args.repeat)
