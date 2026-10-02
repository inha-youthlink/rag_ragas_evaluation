# policy 테이블을 조회해 TestsetGenerator 입력 Document로 변환
from collections.abc import Mapping
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

SELECT_TARGET_POLICIES = """
    SELECT policy_no, policy_name, description, support_content,
           min_age, max_age, min_income, max_income, income_etc,
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
        return [build_document(row) for row in cur.fetchall()]


def build_document(row: Mapping[str, Any]) -> Document:
    lines = [
        *_text_lines(row, TEXT_FIELDS),
        _age_line(row["min_age"], row["max_age"]),
        _income_line(row["min_income"], row["max_income"], _clean(row["income_etc"])),
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


def _age_line(min_age: int | None, max_age: int | None) -> str | None:
    if min_age is not None and max_age is not None:
        return f"지원 연령: 만 {min_age}세 ~ {max_age}세"
    age = _range(_age(min_age), _age(max_age))
    return f"지원 연령: {age}" if age else None


def _age(value: int | None) -> str | None:
    return f"만 {value}세" if value is not None else None


def _income_line(min_income: int | None, max_income: int | None, income_etc: str | None) -> str | None:
    amount = _range(_won(min_income), _won(max_income))
    if amount and income_etc:
        return f"소득 기준: {amount} ({income_etc})"
    if amount or income_etc:
        return f"소득 기준: {amount or income_etc}"
    return None


def _won(value: int | None) -> str | None:
    return f"{value}원" if value is not None else None


def _period_line(start: date | None, end: date | None) -> str | None:
    if start and end:
        return f"신청 기간: {start.isoformat()} ~ {end.isoformat()}"
    if start:
        return f"신청 기간: {start.isoformat()} ~"
    if end:
        return f"신청 기간: ~ {end.isoformat()}"
    return None
