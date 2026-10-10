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
        "소득 기준: 연소득 3,000만원 이하",
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
    ("code", "min_income", "max_income", "income_etc", "expected"),
    [
        pytest.param("0043001", 0, 0, None, "소득 기준: 무관", id="any"),
        pytest.param("0043001", None, None, None, "소득 기준: 무관", id="any-null-amount"),
        pytest.param("0043002", 0, 5000, None, "소득 기준: 연소득 5,000만원 이하", id="annual-max"),
        pytest.param("0043002", 2515, 9999, None, "소득 기준: 연소득 2,515만원 ~ 9,999만원", id="annual-range"),
        pytest.param("0043002", 4000, 0, None, "소득 기준: 연소득 4,000만원 이상", id="annual-min"),
        pytest.param("0043002", 0, 6000, "부부합산", "소득 기준: 연소득 6,000만원 이하 (부부합산)", id="annual-etc"),
        pytest.param("0043002", 0, 0, "중위소득 150% 이하", "소득 기준: 중위소득 150% 이하", id="annual-no-amount"),
        pytest.param("0043002", 0, 0, None, None, id="annual-empty"),
        pytest.param("0043003", 0, 0, "중위소득 150% 이하", "소득 기준: 중위소득 150% 이하", id="etc"),
        pytest.param("0043003", 0, 0, None, None, id="etc-empty"),
        pytest.param("0043003", 0, 0, "-", None, id="etc-dash-only"),
        pytest.param(None, 0, 3000, None, None, id="unknown-code-ignores-amount"),
    ],
)
def test_income_line(policy_row, code, min_income, max_income, income_etc, expected):
    row = {
        **policy_row,
        "income_condition_code": code,
        "min_income": min_income,
        "max_income": max_income,
        "income_etc": income_etc,
    }

    income_lines = [line for line in build_document(row).page_content.splitlines() if line.startswith("소득 기준:")]

    assert income_lines == ([expected] if expected else [])


@pytest.mark.parametrize(
    ("code", "start", "end", "expected"),
    [
        ("0057001", date(2026, 1, 1), None, "신청 기간: 2026-01-01 ~"),
        ("0057001", None, date(2026, 12, 31), "신청 기간: ~ 2026-12-31"),
        ("0057001", None, None, None),
        ("0057002", None, None, "신청 기간: 상시"),
        ("0057002", date(2026, 1, 1), None, "신청 기간: 상시"),
        (None, None, None, None),
    ],
)
def test_application_period_line(policy_row, code, start, end, expected):
    row = {**policy_row, "application_period_type_code": code, "application_start_date": start, "application_end_date": end}

    period_lines = [line for line in build_document(row).page_content.splitlines() if line.startswith("신청 기간:")]

    assert period_lines == ([expected] if expected else [])


ALL_SIDO = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시",
    "세종특별자치시", "경기도", "강원특별자치도", "충청북도", "충청남도", "전북특별자치도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도",
]


@pytest.mark.parametrize(
    ("regions", "expected"),
    [
        pytest.param([], None, id="none"),
        pytest.param([("부산광역시", "부산광역시 금정구")], "지역: 부산광역시 금정구", id="one-sigungu"),
        pytest.param(
            [("인천광역시", "인천광역시 중구"), ("인천광역시", "인천광역시 동구"), ("인천광역시", "인천광역시 동구")],
            "지역: 인천광역시 동구, 인천광역시 중구",
            id="few-sigungu-dedup",
        ),
        pytest.param(
            [("경기도", f"경기도 테스트{i}시") for i in range(4)], "지역: 경기도", id="many-sigungu-one-sido"
        ),
        pytest.param(
            [("충청남도", "충청남도 천안시"), ("대전광역시", "대전광역시 서구")],
            "지역: 대전광역시, 충청남도",
            id="several-sido",
        ),
        pytest.param([(sido, f"{sido} 테스트구") for sido in ALL_SIDO], "지역: 전국", id="all-sido"),
    ],
)
def test_region_line(policy_row, regions, expected):
    lines = build_document(policy_row, regions).page_content.splitlines()

    region_lines = [line for line in lines if line.startswith("지역:")]
    assert region_lines == ([expected] if expected else [])


def test_region_line_follows_support_content(policy_row):
    lines = build_document(policy_row, [("부산광역시", "부산광역시 금정구")]).page_content.splitlines()

    assert lines[2:5] == ["지원 내용: 월 최대 20만원, 최대 12개월", "지역: 부산광역시 금정구", "지원 연령: 만 19세 ~ 34세"]


POLICY_DDL = """
    CREATE TEMP TABLE policy (
        policy_no VARCHAR(30) PRIMARY KEY, policy_name VARCHAR(300) NOT NULL,
        description TEXT, support_content TEXT, min_age INTEGER, max_age INTEGER,
        income_condition_code VARCHAR(20), min_income BIGINT, max_income BIGINT, income_etc TEXT,
        application_period_type_code VARCHAR(30), application_start_date DATE, application_end_date DATE,
        application_method TEXT, submission_documents TEXT, screening_method TEXT,
        additional_qualification TEXT, participation_exclusion TEXT,
        source_updated_at TIMESTAMPTZ
    )
"""


def insert_policy(conn, row):
    insert = sql.SQL("INSERT INTO pg_temp.policy ({}) VALUES ({})").format(
        sql.SQL(", ").join(map(sql.Identifier, row)),
        sql.SQL(", ").join(map(sql.Placeholder, row)),
    )
    conn.execute(insert, row)


@pytest.mark.db
def test_load_documents_adds_resolved_regions(test_database_url, policy_row):
    with psycopg.connect(test_database_url) as conn, conn.transaction(force_rollback=True):
        conn.execute(POLICY_DDL)
        # 서비스 DB의 v_policy_region_resolved와 같은 이름·컬럼의 임시 테이블 (미해결 코드는 이름이 NULL)
        conn.execute(
            "CREATE TEMP TABLE v_policy_region_resolved "
            "(policy_no VARCHAR(30), sido_name VARCHAR(50), region_name VARCHAR(100))"
        )
        insert_policy(conn, {**policy_row, "policy_no": "TEST-LOCAL"})
        insert_policy(conn, {**policy_row, "policy_no": "TEST-NO-REGION"})
        conn.execute(
            "INSERT INTO pg_temp.v_policy_region_resolved VALUES "
            "('TEST-LOCAL', '부산광역시', '부산광역시 금정구'), ('TEST-LOCAL', NULL, NULL), "
            "('TEST-OTHER', '서울특별시', '서울특별시 종로구')"
        )

        documents = load_documents(conn, base_date=date(2026, 10, 2))

    regions = {d.metadata["policy_no"]: [l for l in d.page_content.splitlines() if l.startswith("지역:")] for d in documents}
    assert regions == {"TEST-LOCAL": ["지역: 부산광역시 금정구"], "TEST-NO-REGION": []}


@pytest.mark.db
def test_load_documents_selects_target_policies_only(test_database_url, policy_row):
    with psycopg.connect(test_database_url) as conn, conn.transaction(force_rollback=True):
        conn.execute(POLICY_DDL)
        rows = [
            {**policy_row, "policy_no": "TEST-OPEN", "application_end_date": date(2026, 12, 31)},
            {**policy_row, "policy_no": "TEST-NO-END", "application_end_date": None},
            {**policy_row, "policy_no": "TEST-ENDS-TODAY", "application_end_date": date(2026, 10, 2)},
            {**policy_row, "policy_no": "TEST-CLOSED", "application_end_date": date(2026, 10, 1)},
            {**policy_row, "policy_no": "TEST-NO-DESC", "description": None},
            {**policy_row, "policy_no": "TEST-BLANK-DESC", "description": "   "},
            # 온통청년 마감(0057003) 정책은 종료일이 비어 있어 종료일만으로는 걸러지지 않는다
            {**policy_row, "policy_no": "TEST-CLOSED-CODE", "application_period_type_code": "0057003",
             "application_end_date": None},
            {**policy_row, "policy_no": "TEST-ALWAYS", "application_period_type_code": "0057002",
             "application_start_date": None, "application_end_date": None},
            {**policy_row, "policy_no": "TEST-NO-CODE", "application_period_type_code": None},
        ]
        for row in rows:
            insert_policy(conn, row)

        documents = load_documents(conn, base_date=date(2026, 10, 2))

    assert [d.metadata["policy_no"] for d in documents] == [
        "TEST-ALWAYS", "TEST-ENDS-TODAY", "TEST-NO-CODE", "TEST-NO-END", "TEST-OPEN"
    ]
