# policy 행 → Document 변환과 대상 정책 조회 테스트
from datetime import date

import psycopg
import pytest
from psycopg import sql

from ragas_eval.policy_source.policy_source import build_document, load_documents


def test_document_lines_follow_fixed_order(policy_row):
    document = build_document(policy_row)

    assert document.page_content.splitlines() == [
        "정책명: 테스트 청년 월세 지원",
        "정책 설명: 청년의 월세 부담을 줄이기 위한 가짜 정책",
        "지원 내용: 월 최대 20만원, 최대 12개월",
        "지원 연령: 만 19세 ~ 34세",
        "소득 기준: 30000000원 이하",
        "신청 기간: 2026-01-01 ~ 2026-12-31",
        "신청 방법: 온라인 신청",
        "제출 서류: 임대차계약서, 주민등록등본",
        "심사 방법: 소득 순 선정",
        "참여 제한: 기존 주거급여 수급자",
    ]


def test_metadata_has_policy_no_and_iso_source_updated_at(policy_row):
    document = build_document(policy_row)

    assert document.metadata == {"policy_no": "TEST-0001", "source_updated_at": "2026-09-30T00:00:00+09:00"}


def test_null_source_updated_at_stays_none(policy_row):
    document = build_document({**policy_row, "source_updated_at": None})

    assert document.metadata["source_updated_at"] is None


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_text_column_is_omitted(policy_row, value):
    document = build_document({**policy_row, "support_content": value})

    assert not any(line.startswith("지원 내용:") for line in document.page_content.splitlines())


@pytest.mark.parametrize(
    ("min_age", "max_age", "expected"),
    [
        (19, 34, "지원 연령: 만 19세 ~ 34세"),
        (19, None, "지원 연령: 만 19세 이상"),
        (None, 34, "지원 연령: 만 34세 이하"),
        (0, None, "지원 연령: 만 0세 이상"),
        (None, None, None),
    ],
)
def test_age_range_line(policy_row, min_age, max_age, expected):
    lines = build_document({**policy_row, "min_age": min_age, "max_age": max_age}).page_content.splitlines()

    age_lines = [line for line in lines if line.startswith("지원 연령:")]
    assert age_lines == ([expected] if expected else [])


@pytest.mark.parametrize(
    ("min_income", "max_income", "income_etc", "expected"),
    [
        (10000000, 30000000, None, "소득 기준: 10000000원 ~ 30000000원"),
        (10000000, None, None, "소득 기준: 10000000원 이상"),
        (None, 30000000, "중위소득 150% 이하", "소득 기준: 30000000원 이하 (중위소득 150% 이하)"),
        (None, None, "중위소득 150% 이하", "소득 기준: 중위소득 150% 이하"),
        (None, 0, None, "소득 기준: 0원 이하"),
        (None, None, None, None),
    ],
)
def test_income_line(policy_row, min_income, max_income, income_etc, expected):
    row = {**policy_row, "min_income": min_income, "max_income": max_income, "income_etc": income_etc}

    income_lines = [line for line in build_document(row).page_content.splitlines() if line.startswith("소득 기준:")]

    assert income_lines == ([expected] if expected else [])


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2026, 1, 1), None, "신청 기간: 2026-01-01 ~"),
        (None, date(2026, 12, 31), "신청 기간: ~ 2026-12-31"),
        (None, None, None),
    ],
)
def test_application_period_line(policy_row, start, end, expected):
    row = {**policy_row, "application_start_date": start, "application_end_date": end}

    period_lines = [line for line in build_document(row).page_content.splitlines() if line.startswith("신청 기간:")]

    assert period_lines == ([expected] if expected else [])


@pytest.mark.db
def test_load_documents_selects_target_policies_only(test_database_url, policy_row):
    with psycopg.connect(test_database_url) as conn, conn.transaction(force_rollback=True):
        conn.execute(
            """
            CREATE TEMP TABLE policy (
                policy_no VARCHAR(30) PRIMARY KEY, policy_name VARCHAR(300) NOT NULL,
                description TEXT, support_content TEXT, min_age INTEGER, max_age INTEGER,
                min_income BIGINT, max_income BIGINT, income_etc TEXT,
                application_start_date DATE, application_end_date DATE,
                application_method TEXT, submission_documents TEXT, screening_method TEXT,
                additional_qualification TEXT, participation_exclusion TEXT,
                source_updated_at TIMESTAMPTZ
            )
            """
        )
        rows = [
            {**policy_row, "policy_no": "TEST-OPEN", "application_end_date": date(2026, 12, 31)},
            {**policy_row, "policy_no": "TEST-NO-END", "application_end_date": None},
            {**policy_row, "policy_no": "TEST-ENDS-TODAY", "application_end_date": date(2026, 10, 2)},
            {**policy_row, "policy_no": "TEST-CLOSED", "application_end_date": date(2026, 10, 1)},
            {**policy_row, "policy_no": "TEST-NO-DESC", "description": None},
            {**policy_row, "policy_no": "TEST-BLANK-DESC", "description": "   "},
        ]
        for row in rows:
            insert = sql.SQL("INSERT INTO pg_temp.policy ({}) VALUES ({})").format(
                sql.SQL(", ").join(map(sql.Identifier, row)),
                sql.SQL(", ").join(map(sql.Placeholder, row)),
            )
            conn.execute(insert, row)

        documents = load_documents(conn, base_date=date(2026, 10, 2))

    assert [d.metadata["policy_no"] for d in documents] == ["TEST-ENDS-TODAY", "TEST-NO-END", "TEST-OPEN"]
