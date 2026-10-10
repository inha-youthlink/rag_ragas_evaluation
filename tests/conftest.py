# 테스트 공용 fixture (가짜 정책·데이터셋·RAG 응답, 임시 DB URL)
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

KST = timezone(timedelta(hours=9))
TEST_DB_NAME = re.compile(r"(^|_)test(_|$)")
LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1"}
RAGAS_SCHEMA_SQL = Path(__file__).resolve().parents[1] / "db" / "ragas_schema.sql"


@pytest.fixture
def policy_row() -> dict:
    return {
        "policy_no": "TEST-0001",
        "policy_name": "테스트 청년 월세 지원",
        "description": "청년의 월세 부담을 줄이기 위한 가짜 정책",
        "support_content": "월 최대 20만원, 최대 12개월",
        "min_age": 19,
        "max_age": 34,
        "income_condition_code": "0043002",
        "min_income": 0,
        "max_income": 3000,
        "income_etc": None,
        "application_start_date": date(2026, 1, 1),
        "application_end_date": date(2026, 12, 31),
        "application_method": "온라인 신청",
        "submission_documents": "임대차계약서, 주민등록등본",
        "screening_method": "소득 순 선정",
        "additional_qualification": None,
        "participation_exclusion": "기존 주거급여 수급자",
        "source_updated_at": datetime(2026, 9, 30, tzinfo=KST),
    }


@pytest.fixture
def golden_record() -> dict:
    return {
        "sample_id": "single-000001",
        "policy_no": "TEST-0001",
        "question": "테스트 청년 월세 지원은 몇 살까지 신청할 수 있나요?",
        "ground_truth": "만 19세부터 34세까지 신청할 수 있습니다.",
        "reference_contexts": ["지원 대상: 만 19세 ~ 34세 청년"],
        "synthesizer_name": "single_hop_specific_query_synthesizer",
        "profile": {},
        "source_updated_at": "2026-09-30T00:00:00+09:00",
        "reviewed": True,
    }


@pytest.fixture
def rag_payload() -> dict:
    return {
        "answer": "만 19세부터 34세까지 신청할 수 있습니다.",
        "policies": [],
        "trace": {
            "contexts": ["<정책 1> 테스트 청년 정책\n[신청 상태] 상시 모집\n[내용]\n지원 대상: 만 19세 ~ 34세 청년"],
            "retrieved_chunks": [
                {
                    "chunk_id": "00000000-0000-0000-0000-000000000001",
                    "policy_no": "TEST-0001",
                    "chunk_type": "eligibility",
                    "score": 0.91,
                },
            ],
            "latency_ms": {"retrieve": 300, "policy_lookup": 30, "generate": 860, "total": 1200},
            "tokens": {"prompt": 850, "completion": 40},
            "chat_model": "test-chat-model",
            "retriever": "vector",
            "top_k": 10,
            "prompt_version": "generate_v1",
        },
    }


def _checked_test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL이 없어 DB 통합 테스트를 건너뜀")
    info = conninfo_to_dict(url)
    if not TEST_DB_NAME.search(info.get("dbname", "")):
        pytest.fail("TEST_DATABASE_URL의 DB 이름에 'test' 구분 단어가 없음. 공유·개발 DB 보호를 위해 중단")
    if info.get("host", "") not in LOCAL_DB_HOSTS:
        pytest.fail("TEST_DATABASE_URL의 host가 로컬이 아님. 원격 DB 보호를 위해 중단")
    return url


@pytest.fixture
def test_database_url() -> str:
    return _checked_test_database_url()


@pytest.fixture(scope="session")
def eval_schema_url() -> str:
    """임시 DB에 평가 테이블 DDL을 적용한다. 두 번 적용해 재실행 안전성도 함께 확인한다."""
    url = _checked_test_database_url()
    with psycopg.connect(url, autocommit=True) as conn:
        for _ in range(2):
            conn.execute(RAGAS_SCHEMA_SQL.read_text(encoding="utf-8"))
    return url


@pytest.fixture
def eval_conn(eval_schema_url):
    """테스트마다 롤백되는 연결. repository 함수는 커밋하지 않으므로 쓴 행은 남지 않는다."""
    with psycopg.connect(eval_schema_url) as conn:
        try:
            yield conn
        finally:
            conn.rollback()
