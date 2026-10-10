# policy 테이블을 조회해 TestsetGenerator 입력 Document로 변환
import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

import psycopg
from langchain_core.documents import Document
from psycopg.rows import dict_row

TEXT_FIELDS = {
    "policy_name": "정책명",
    "description": "정책 설명",
    "support_content": "지원 내용",
}
DETAIL_FIELDS = {
    "application_method": "신청 방법",
    "submission_documents": "제출 서류",
    "screening_method": "심사 방법",
    "additional_qualification": "추가 자격",
    "participation_exclusion": "참여 제한",
}
# 온통청년 earnCndSeCd. 연소득 금액(min_income·max_income)의 단위는 만원이고, 0은 해당 경계 없음
INCOME_ANY = "0043001"
INCOME_ANNUAL = "0043002"
# 정책 지역 코드를 현재 시도·시군구 이름으로 해석한 조회용 View (youthlink-data-pipeline 지역 ETL).
# 미해결 코드(UNRESOLVED)는 이름이 NULL이라 제외한다
REGION_VIEW = "v_policy_region_resolved"
SELECT_POLICY_REGIONS = f"""
    SELECT policy_no, sido_name, region_name
    FROM {REGION_VIEW}
    WHERE policy_no = ANY(%(policy_nos)s) AND sido_name IS NOT NULL AND region_name IS NOT NULL
"""
SIDO_COUNT = 17
# 한 시도 안에서 이 수까지는 시군구 이름을 나열하고, 넘으면 시도 이름으로 줄인다
MAX_LISTED_REGIONS = 3

logger = logging.getLogger(__name__)

SELECT_TARGET_POLICIES = """
    SELECT policy_no, policy_name, description, support_content,
           min_age, max_age, income_condition_code, min_income, max_income, income_etc,
           application_start_date, application_end_date,
           application_method, submission_documents, screening_method,
           additional_qualification, participation_exclusion,
           source_updated_at
    FROM policy
    WHERE NULLIF(BTRIM(description), '') IS NOT NULL
      AND (application_end_date IS NULL OR application_end_date >= %(base_date)s)
    ORDER BY policy_no
"""


def load_documents(conn: psycopg.Connection, base_date: date) -> list[Document]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(SELECT_TARGET_POLICIES, {"base_date": base_date})
        rows = cur.fetchall()
    regions = _load_regions(conn, [row["policy_no"] for row in rows])
    return [build_document(row, regions.get(row["policy_no"], ())) for row in rows]


def _load_regions(conn: psycopg.Connection, policy_nos: list[str]) -> dict[str, list[tuple[str, str]]]:
    # 지역 View가 아직 없는 DB(지역 ETL 미적용)에서도 생성은 되도록 지역 줄만 빼고 알린다
    if conn.execute("SELECT to_regclass(%s)", [REGION_VIEW]).fetchone()[0] is None:
        logger.warning("%s가 없어 정책 문서에 지역을 넣지 않음", REGION_VIEW)
        return {}
    regions: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for policy_no, sido_name, region_name in conn.execute(SELECT_POLICY_REGIONS, {"policy_nos": policy_nos}):
        regions[policy_no].append((sido_name, region_name))
    return regions


def build_document(row: Mapping[str, Any], regions: Sequence[tuple[str, str]] = ()) -> Document:
    """regions: (시도 이름, 시군구 지역 이름) 목록."""
    lines = [
        *_text_lines(row, TEXT_FIELDS),
        _region_line(regions),
        _age_line(row["min_age"], row["max_age"]),
        _income_line(row["income_condition_code"], row["min_income"], row["max_income"], _clean(row["income_etc"])),
        _period_line(row["application_start_date"], row["application_end_date"]),
        *_text_lines(row, DETAIL_FIELDS),
    ]
    updated_at = row["source_updated_at"]
    return Document(
        page_content="\n".join(line for line in lines if line),
        metadata={
            "policy_no": row["policy_no"],
            "source_updated_at": updated_at.isoformat() if updated_at else None,
        },
    )


def _clean(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _text_lines(row: Mapping[str, Any], fields: dict[str, str]) -> list[str]:
    cleaned = {label: _clean(row[key]) for key, label in fields.items()}
    return [f"{label}: {value}" for label, value in cleaned.items() if value]


def _range(low: str | None, high: str | None) -> str | None:
    if low and high:
        return f"{low} ~ {high}"
    if low:
        return f"{low} 이상"
    if high:
        return f"{high} 이하"
    return None


def _region_line(regions: Sequence[tuple[str, str]]) -> str | None:
    sidos = sorted({sido for sido, _ in regions})
    if not sidos:
        return None
    if len(sidos) >= SIDO_COUNT:
        return "지역: 전국"
    names = sorted({name for _, name in regions})
    if len(sidos) == 1 and len(names) <= MAX_LISTED_REGIONS:
        return f"지역: {', '.join(names)}"
    return f"지역: {', '.join(sidos)}"


def _age_line(min_age: int | None, max_age: int | None) -> str | None:
    if min_age is not None and max_age is not None:
        return f"지원 연령: 만 {min_age}세 ~ {max_age}세"
    age = _range(_age(min_age), _age(max_age))
    return f"지원 연령: {age}" if age else None


def _age(value: int | None) -> str | None:
    return f"만 {value}세" if value is not None else None


def _income_line(
    code: str | None, min_income: int | None, max_income: int | None, income_etc: str | None
) -> str | None:
    # API가 비어 있는 설명을 "-"로 채운 경우가 있다
    income_etc = income_etc if income_etc and income_etc.strip("- ") else None
    base = None
    if code == INCOME_ANY:
        base = "무관"
    elif code == INCOME_ANNUAL:
        amount = _range(_manwon(min_income), _manwon(max_income))
        base = f"연소득 {amount}" if amount else None
    if base and income_etc:
        return f"소득 기준: {base} ({income_etc})"
    if base or income_etc:
        return f"소득 기준: {base or income_etc}"
    return None


def _manwon(value: int | None) -> str | None:
    return f"{value:,}만원" if value else None


def _period_line(start: date | None, end: date | None) -> str | None:
    if start and end:
        return f"신청 기간: {start.isoformat()} ~ {end.isoformat()}"
    if start:
        return f"신청 기간: {start.isoformat()} ~"
    if end:
        return f"신청 기간: ~ {end.isoformat()}"
    return None
