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
# DB policy 읽기 → 질문·정답 후보 100건 생성 → datasets/에 저장 (검수 후 golden_v1.jsonl로 확정)
python -m ragas_eval generate --testset-size 100 --out datasets/golden_candidates.jsonl

# 확정 데이터셋으로 RAG 호출 → 채점 → 결과 DB 저장, 3회 반복
python -m ragas_eval run --golden datasets/golden_v1.jsonl --repeat 3

# RAG 없이 정답을 응답으로 넣어 채점 → DB 저장 경로만 검증
python -m ragas_eval run --golden datasets/golden_v1.jsonl --offline
```

## 테스트

```bash
pytest
```