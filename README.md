# rag-eval

YouthLink RAG를 RAGAS로 평가합니다. 상세 계획은 `docs/RAGAS_PRD.md`, DB 스키마는 `docs/Schema.md`를 참고합니다.

## 설치

```bash
python -m venv .venv
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
