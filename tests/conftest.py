# 테스트 공용 fixture (가짜 정책·데이터셋·RAG 응답, 임시 DB URL)
import os
import re
from datetime import date, datetime, timedelta, timezone

import pytest
from psycopg.conninfo import conninfo_to_dict

KST = timezone(timedelta(hours=9))
TEST_DB_NAME = re.compile(r"(^|_)test(_|$)")


@pytest.fixture
def policy_row() -> dict:
    return {
        "policy_no": "TEST-0001",
        "policy_name": "테스트 청년 월세 지원",
        "description": "청년의 월세 부담을 줄이기 위한 가짜 정책",
        "support_content": "월 최대 20만원, 최대 12개월",
        "min_age": 19,
        "max_age": 34,
        "min_income": None,
        "max_income": 30000000,
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
            "chunks": [
                {
                    "chunk_id": "00000000-0000-0000-0000-000000000001",
                    "policy_no": "TEST-0001",
                    "chunk_index": 0,
                    "chunk_type": "eligibility",
                    "content": "지원 대상: 만 19세 ~ 34세 청년",
                    "score": 0.91,
                },
            ],
            "latency_ms": 1200,
            "prompt_tokens": 850,
            "completion_tokens": 40,
            "chat_model": "test-chat-model",
            "retriever": "vector",
            "top_k": 10,
        },
    }


@pytest.fixture
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL이 없어 DB 통합 테스트를 건너뜀")
    if not TEST_DB_NAME.search(conninfo_to_dict(url).get("dbname", "")):
        pytest.fail("TEST_DATABASE_URL의 DB 이름에 'test' 구분 단어가 없음. 공유·개발 DB 보호를 위해 중단")
    return url
