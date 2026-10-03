# TestsetGenerator로 데이터셋 후보(golden_candidates.jsonl)를 생성
import asyncio
import json
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NamedTuple

import psycopg
from langchain_core.documents import Document
from openai import AsyncOpenAI
from pydantic import ValidationError
from ragas.embeddings import OpenAIEmbeddings
from ragas.testset import TestsetGenerator
from ragas.testset.synthesizers.single_hop.specific import SingleHopSpecificQuerySynthesizer

from ragas_eval.config import Settings, get_settings
from ragas_eval.dataset.dataset import GoldenSample
from ragas_eval.policy_source.policy_source import load_documents
from ragas_eval.scorer.scorer import make_llm

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
LANGUAGE = "korean"
# 확정 데이터셋은 수정하지 않는다(CLAUDE.md). 생성 결과로 덮어쓰지 않도록 막는다
CONFIRMED_DATASET = re.compile(r"golden_v\d+\.jsonl", re.IGNORECASE)


class GenerateSummary(NamedTuple):
    written: int
    dropped: int


def match_policy(contexts: Sequence[str], documents: Iterable[Document]) -> Document | None:
    """모든 reference_context를 본문에 포함하는 정책이 정확히 하나일 때만 그 Document를 돌려준다."""
    # ragas HeadlineSplitter가 섹션을 공백으로 이어 붙이므로 공백을 정규화한 뒤 비교한다
    needles = [_squash(c) for c in contexts if c.strip()]
    if not needles:
        return None
    matched = [d for d in documents if all(n in _squash(d.page_content) for n in needles)]
    return matched[0] if len(matched) == 1 else None


def _squash(text: str) -> str:
    return " ".join(text.split())


def build_records(rows: Iterable[Mapping[str, Any]], documents: Sequence[Document]) -> tuple[list[dict], int]:
    """생성 결과를 golden 형식으로 바꾼다. 정책을 특정할 수 없거나 질문·정답이 비면 버린다."""
    records: list[dict] = []
    dropped = 0
    for row in rows:
        doc = match_policy(row.get("reference_contexts") or [], documents)
        if doc is None:
            logger.warning("생성 결과 제외: 정책을 하나로 특정할 수 없음")
            dropped += 1
            continue
        record = {
            "sample_id": f"single-{len(records) + 1:06d}",
            "policy_no": doc.metadata["policy_no"],
            "question": (row.get("user_input") or "").strip(),
            "ground_truth": (row.get("reference") or "").strip(),
            "reference_contexts": list(row["reference_contexts"]),
            "synthesizer_name": row.get("synthesizer_name") or "",
            "profile": {},
            "source_updated_at": doc.metadata["source_updated_at"],
            "reviewed": False,
        }
        try:
            GoldenSample.model_validate(record)
        except ValidationError as e:
            # 생성 원문은 남기지 않고 위치·종류만 남긴다
            details = ", ".join(
                f"{'.'.join(map(str, err['loc']))}:{err['type']}" for err in e.errors(include_input=False)
            )
            logger.warning("생성 결과 제외: policy_no=%s 검증 실패 %s", doc.metadata["policy_no"], details)
            dropped += 1
            continue
        records.append(record)
    return records, dropped


def write_jsonl(records: Iterable[Mapping[str, Any]], path: str | Path) -> None:
    path = Path(path)
    _check_out_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) + "\n" for r in records]
    path.write_text("".join(lines), encoding="utf-8")


def generate(testset_size: int, out_path: str) -> GenerateSummary:
    _check_out_path(Path(out_path))
    settings = get_settings()
    documents = _load_target_documents(settings)
    if not documents:
        raise ValueError("대상 정책이 없어 생성하지 않음 (description이 있고 신청 기간이 남은 정책 0건)")
    rows = _run_generator(documents, testset_size, settings)
    records, dropped = build_records(rows, documents)
    if not records:
        # 검수 중인 기존 후보 파일을 빈 파일로 덮어쓰지 않는다
        raise ValueError(f"생성 결과 {dropped}건이 모두 제외되어 저장하지 않음")
    write_jsonl(records, out_path)
    return GenerateSummary(written=len(records), dropped=dropped)


def _check_out_path(path: Path) -> None:
    # Windows는 대소문자를 구분하지 않고 끝의 공백·점을 지우므로 같은 파일로 취급되는 이름도 막는다
    if CONFIRMED_DATASET.fullmatch(path.name.rstrip(" .")):
        raise ValueError(f"확정 데이터셋(golden_vN)에는 쓰지 않음: {path.name}")


def _load_target_documents(settings: Settings) -> list[Document]:
    # policy는 SELECT만 한다. 읽기 전용 세션으로 열어 실수로 쓰는 것도 막는다
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        conn.read_only = True
        return load_documents(conn, datetime.now(KST).date())


def _run_generator(documents: Sequence[Document], testset_size: int, settings: Settings) -> list[dict]:
    api_key = settings.openai_api_key.get_secret_value()
    synthesizer = asyncio.run(_korean_synthesizer(api_key, settings.gen_model))

    # ragas는 변환·생성 단계마다 새 이벤트 루프(asyncio.run)를 열어 이 클라이언트를 여러 루프에서 재사용한다.
    # 닫힌 루프에 묶인 연결 오류는 SDK 기본 재시도(2회)로 복구된다(스텁 서버로 확인, 실제 OpenAI 미확인)
    client = AsyncOpenAI(api_key=api_key)
    llm = make_llm(settings.gen_model, client)
    synthesizer.llm = llm
    generator = TestsetGenerator(
        llm=llm, embedding_model=OpenAIEmbeddings(client=client, model=settings.embedding_model)
    )
    testset = generator.generate_with_langchain_docs(
        documents, testset_size=testset_size, query_distribution=[(synthesizer, 1.0)]
    )
    return testset.to_list()


async def _korean_synthesizer(api_key: str, model: str) -> SingleHopSpecificQuerySynthesizer:
    async with AsyncOpenAI(api_key=api_key) as client:
        llm = make_llm(model, client)
        synthesizer = SingleHopSpecificQuerySynthesizer(llm=llm)
        prompts = await synthesizer.adapt_prompts(LANGUAGE, llm=llm)
        synthesizer.set_prompts(**prompts)
    return synthesizer
