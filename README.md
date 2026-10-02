# rag_ragas_evaluation

YouthLink RAG를 RAGAS로 평가합니다. 상세 계획은 `docs/RAGAS_PRD.md`, DB 스키마는 `docs/Schema.md`를 참고합니다.

## 설치

Python 3.12 필요 (3.14는 `scikit-network` Windows wheel 없음).

```bash
py -3.12 -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
```

## DB

```bash
psql -d youthlink -f db/ragas_schema.sql
```

## 실행

```bash
python -m ragas_eval generate --testset-size 100 --out datasets/golden_candidates.jsonl
python -m ragas_eval run --golden datasets/golden_v1.jsonl --repeat 3
```

## 테스트

```bash
pytest
```

## 작업 방식

Claude Code 기반 스펙 주도 개발(Spec-Driven Development)로 진행합니다.

| 단계 | 문서 | 역할 |
| --- | --- | --- |
| 스펙 | `docs/RAGAS_PRD.md`, `docs/Schema.md` | 무엇을 만들지 먼저 확정 |
| 상시 규칙 | `CLAUDE.md` | 매 세션 적용되는 기술 스택·필수·금지·검증 규칙 |
| 상세 규칙 | `.claude/skills/` | 작업별로 필요할 때만 불러오는 규칙 (예: `/ragas-eval-test`) |
| 검증 | `tests/`, 완료 보고 | 테스트 통과와 미검증 사항 확인 후 논리 단위로 커밋 |
