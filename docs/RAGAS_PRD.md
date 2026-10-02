# RAGAS 평가 PRD

## 개요

- 대상: `YouthLink_RAG` (`question` + `profile` → `answer` + `policies` + `trace`)
- 범위: 단일 정책 질문
- 데이터셋: DB `policy` → `TestsetGenerator` → 검수 → `golden_vN.jsonl` (git 고정)
- 평가: K8s Job → 질문 INSERT → RAG 응답·점수 UPDATE
- 지표: Context Precision, Context Recall, Faithfulness, Answer Relevancy

## 역할 분담

| 역할 | 담당 | 작업 | DB |
| --- | --- | --- | --- |
| ETL | ETL 담당자 | 온통청년 API → `policy` UPSERT | 쓰기 |
| 데이터셋 | 평가 담당자 | `policy` → 생성 → 검수 → `golden_vN.jsonl` | 읽기 `policy` |
| 평가 실행 | 미정 (평가 담당자 / RAG 담당자) | Job 실행 → 결과 저장 | 쓰기 `ragas_evaluation_*` |
| RAG | RAG 담당자 | 개선 → 배포 → 평가 요청 | 읽기 `policy_chunk` |
| `policy_chunk` 적재 | 미정 (ETL / RAG) | 청킹·임베딩 → `policy_chunk` | 쓰기 |

## 전체 흐름

| 단계 | 주체 | 빈도 | 입력 → 출력 |
| --- | --- | --- | --- |
| 1. 정책 적재 | ETL | 수시 | API → `policy` |
| 2. 데이터셋 생성 | 평가 담당자 (로컬) | 최초 1회, 버전업 시 | `policy` → `golden_candidates.jsonl` |
| 3. 검수·고정 | 평가 담당자 | 2 직후 | → `golden_vN.jsonl` (git) |
| 4. RAG 개선·배포 | RAG 담당자 | 개선 시마다 | → RAG 서버 (dev) |
| 5. 평가 실행 | K8s Job | 요청 시 | `golden_vN.jsonl` + RAG 응답 → 점수 |
| 6. 결과 확인 | RAG 담당자 | 5 직후 | `ragas_evaluation_run`, `ragas_evaluation_samples` |

## 의존 관계

| 연결 | 조건 |
| --- | --- |
| ETL → 데이터셋 | ETL 적재 완료 후 생성 |
| RAG 배포 → 평가 | Job은 `RAG_BASE_URL`에 배포된 버전을 평가 |
| ETL → 평가 | `source_updated_at` 변경 샘플 제외. 제외 증가 시 `golden_vN+1` |

## 현재 상태

| 구성 | 상태 |
| --- | --- |
| `youthlink-data-pipeline` | 수동 실행, 전체 수집, `policy`·`policy_region`·`policy_eligibility_code`만 적재, 삭제 정책 미반영 |
| `policy_chunk` | 적재 코드 없음 |
| `YouthLink_RAG` | `/health`만 존재, 파이프라인·엔드포인트 미구현 |
| `rag_ragas_evaluation` | 패키지 뼈대, CLI, `config`, `db/ragas_schema.sql`만 존재 |

## RAGAS 입력

| 필드 | RAGAS 인자 | 출처 | 시점 |
| --- | --- | --- | --- |
| `question` | `user_input` | `TestsetGenerator` `user_input` | 데이터셋 생성 |
| `ground_truth` | `reference` | `TestsetGenerator` `reference` → 검수 | 데이터셋 생성 |
| `contexts` | `retrieved_contexts` | RAG `trace.chunks[].content` | 평가 (UPDATE) |
| `answer` | `response` | RAG `answer` | 평가 (UPDATE) |

## 데이터셋 생성

| 항목 | 값 |
| --- | --- |
| 대상 | `description` NOT NULL, `application_end_date` NULL 또는 기준일 이후 |
| 원천 텍스트 | `policy_name`, `description`, `support_content`, `min_age`/`max_age`, `min_income`/`max_income`/`income_etc`, `application_start_date`/`application_end_date`, `application_method`, `submission_documents`, `screening_method`, `additional_qualification`, `participation_exclusion` |
| 입력 변환 | 정책 1건 → `Document` 1개 (`metadata`: `policy_no`, `source_updated_at`) |
| 생성기 | `TestsetGenerator(llm, embedding_model).generate_with_langchain_docs(docs, testset_size, query_distribution)` |
| 질문 유형 | `[(SingleHopSpecificQuerySynthesizer(llm), 1.0)]` |
| 한국어 | 생성기 프롬프트 한국어 adapt |
| 모델 | RAG `chat_model`과 다른 LLM, `text-embedding-3-small` |
| `policy_no` 복원 | `reference_contexts` ↔ `Document.page_content` 매칭 |
| 사전 검증 | 10건 시험 생성 (짧은 문서 누락, 한국어 품질) |
| 검수 | `reviewed = true`만 사용 |
| 규모 | 100건 내외 |
| 저장 | `datasets/golden_vN.jsonl` (git, DB 미저장) |

| jsonl 필드 | 타입 | 출처 |
| --- | --- | --- |
| `sample_id` | str | 생성 시 부여 (`single-000123`) |
| `policy_no` | str | 매칭 |
| `question` | str | `user_input` |
| `ground_truth` | str | `reference` |
| `reference_contexts` | list[str] | `reference_contexts` |
| `synthesizer_name` | str | `synthesizer_name` |
| `profile` | object | `{}` |
| `source_updated_at` | str (ISO 8601) | `Document.metadata` |
| `reviewed` | bool | 검수 |

## 평가 지표

| 지표 | 클래스 (`ragas.metrics.collections`, v0.4) | 입력 | 모델 |
| --- | --- | --- | --- |
| Context Precision | `ContextPrecision` | `user_input`, `retrieved_contexts`, `reference` | LLM |
| Context Recall | `ContextRecall` | `user_input`, `retrieved_contexts`, `reference` | LLM |
| Faithfulness | `Faithfulness` | `user_input`, `retrieved_contexts`, `response` | LLM |
| Answer Relevancy | `AnswerRelevancy` | `user_input`, `response` | LLM + 임베딩 |

| 항목 | 값 |
| --- | --- |
| 채점 LLM | `llm_factory(<judge_model>, client=AsyncOpenAI())`, RAG `chat_model`과 다른 모델 |
| 호출 | `await metric.ascore(...)` → `result.value` |
| 실패 | 해당 지표 NULL, `metadata.errors` 기록 |

## 평가 실행 순서

| 순서 | 테이블 | 작업 | 컬럼 |
| --- | --- | --- | --- |
| 1 | `ragas_evaluation_run` | INSERT | `run_id`, `dataset_version`, `repeat_no`, 모델 정보, `status = 'RUNNING'` |
| 2 | `ragas_evaluation_samples` | INSERT (`reviewed = true`) | `sample_id`, `policy_no`, `question`, `ground_truth` |
| 3 | `ragas_evaluation_samples` | UPDATE (RAG 응답) | `answer`, `contexts`, `latency_ms`, `metadata.tokens` |
| 4 | `ragas_evaluation_samples` | UPDATE (채점) | 지표 4개, `metadata.errors` |
| 5 | `ragas_evaluation_run` | UPDATE (집계) | `avg_*`, `sample_count`, `finished_at`, `status` |

- `--repeat 3` → 1~5를 3회 (run 3행)
- 이전 run 덮어쓰기 없음
- 재개: `answer IS NULL` → 3부터, 지표 전부 NULL → 4부터
- 성적표: `ragas_evaluation_run.avg_*` (실행별), `ragas_evaluation_samples` (샘플별)

## RAG 연동 계약

| 항목 | 값 |
| --- | --- |
| 호출 | `POST {RAG_BASE_URL}/internal/pipeline?debug=true` |
| 요청 | `PipelineInput` = `{question, profile}` |
| 응답 | `PipelineOutput` = `{answer, policies[], trace}` |
| `trace` 필수 키 | `chunks` (`chunk_id`, `policy_no`, `chunk_index`, `chunk_type`, `content`, `score`), `latency_ms`, `prompt_tokens`, `completion_tokens`, `chat_model`, `retriever`, `top_k` |
| `retrieved_contexts` | `[c.content for c in trace.chunks]` (score 내림차순) |

## 오프라인 모드 (`run --offline`)

| 항목 | 값 |
| --- | --- |
| 목적 | RAG 없이 데이터셋 → 채점 → DB 저장 경로 검증 |
| RAG 호출 | 없음 |
| `answer` | `ground_truth` |
| `contexts` | `reference_contexts` → `[{"content": c} for c in reference_contexts]` |
| `latency_ms` | NULL |
| run 기록 | `rag_chat_model`·`rag_retriever`·`rag_top_k` NULL, `metadata.mode = "offline"` |
| 기대 결과 | 지표 4개 1에 근접. 크게 낮으면 채점·매핑 오류 |
| 비용 | 채점 LLM 호출 발생 (사용자 확인 후 실행) |

## DB 추가 테이블 (`db/ragas_schema.sql`)

### ragas_evaluation_run

| 컬럼 | 타입 | NULL | 기본값 | 제약 |
| --- | --- | --- | --- | --- |
| run_id | UUID | NOT NULL | gen_random_uuid() | PK |
| dataset_version | VARCHAR(50) | NOT NULL | | |
| repeat_no | INTEGER | NOT NULL | 1 | CHECK >= 1 |
| rag_chat_model | VARCHAR(100) | NULL | | |
| rag_retriever | VARCHAR(50) | NULL | | |
| rag_top_k | INTEGER | NULL | | |
| judge_model | VARCHAR(100) | NOT NULL | | |
| embedding_model | VARCHAR(100) | NOT NULL | | |
| status | VARCHAR(20) | NOT NULL | 'RUNNING' | CHECK IN ('RUNNING', 'SUCCEEDED', 'FAILED') |
| sample_count | INTEGER | NULL | | |
| avg_context_precision | NUMERIC(4,3) | NULL | | |
| avg_context_recall | NUMERIC(4,3) | NULL | | |
| avg_faithfulness | NUMERIC(4,3) | NULL | | |
| avg_answer_relevancy | NUMERIC(4,3) | NULL | | |
| started_at | TIMESTAMPTZ | NOT NULL | NOW() | |
| finished_at | TIMESTAMPTZ | NULL | | |
| metadata | JSONB | NOT NULL | '{}'::jsonb | |

### ragas_evaluation_samples

| 컬럼 | 타입 | NULL | 기본값 | 제약 |
| --- | --- | --- | --- | --- |
| id | BIGSERIAL | NOT NULL | | PK |
| run_id | UUID | NOT NULL | | FK → ragas_evaluation_run.run_id (CASCADE), UNIQUE(run_id, sample_id) |
| sample_id | VARCHAR(50) | NOT NULL | | |
| policy_no | VARCHAR(30) | NULL | | FK 없음 |
| question | TEXT | NOT NULL | | |
| answer | TEXT | NULL | | |
| ground_truth | TEXT | NULL | | |
| contexts | JSONB | NOT NULL | '[]'::jsonb | `trace.chunks` 원본 |
| context_precision | NUMERIC(4,3) | NULL | | CHECK 0 ~ 1 |
| context_recall | NUMERIC(4,3) | NULL | | CHECK 0 ~ 1 |
| faithfulness | NUMERIC(4,3) | NULL | | CHECK 0 ~ 1 |
| answer_relevancy | NUMERIC(4,3) | NULL | | CHECK 0 ~ 1 |
| latency_ms | INTEGER | NULL | | |
| created_at | TIMESTAMPTZ | NOT NULL | NOW() | |
| metadata | JSONB | NOT NULL | '{}'::jsonb | |

| 인덱스 | 테이블 | 컬럼 |
| --- | --- | --- |
| idx_ragas_run_started | ragas_evaluation_run | started_at |
| idx_ragas_samples_run | ragas_evaluation_samples | run_id |
| idx_ragas_samples_policy | ragas_evaluation_samples | policy_no |

### 제시안 대비 변경

| 변경 | 이유 |
| --- | --- |
| `ragas_evaluation_run` 분리 + `run_id` FK | 실행 조건 비교, 반복 묶음 |
| `SERIAL` → `BIGSERIAL` | 행 누적 |
| `policy_no` 추가 (FK 없음) | 정책별 분석, 정책 변경과 무관하게 보존 |
| `contexts`에 `trace.chunks` 원본 | 검색 순위·점수 재분석 |
| 지표 CHECK 0 ~ 1, NULL 허용 | 채점 실패와 0점 구분 |
| `latency_ms` 추가 | 응답 속도 집계 |

## 코드 구조 (`rag_ragas_evaluation/`)

| 경로 | 역할 |
| --- | --- |
| `ragas_eval/__main__.py` | 진입점 |
| `ragas_eval/cli.py` | `generate`, `run` |
| `ragas_eval/config.py` | `DATABASE_URL`, `OPENAI_API_KEY`, `RAG_BASE_URL`, `GEN_MODEL`, `JUDGE_MODEL` |
| `ragas_eval/policy_source/policy_source.py` | `policy` → `Document` |
| `ragas_eval/generate/generate.py` | `TestsetGenerator` → `policy_no` 복원 → `golden_candidates.jsonl` |
| `ragas_eval/dataset/dataset.py` | jsonl 로드, `reviewed` 필터, `source_updated_at` 검사, `GoldenSample` 타입 |
| `ragas_eval/rag_client/rag_client.py` | RAG 호출, `RagResult` 타입 |
| `ragas_eval/scorer/scorer.py` | 지표 4개 `ascore`, `ScoreResult` 타입 |
| `ragas_eval/repository/repository.py` | run/samples INSERT·UPDATE |
| `ragas_eval/runner/runner.py` | 실행 순서 1~5, `--repeat`, `--offline` |
| `db/ragas_schema.sql` | DDL |
| `datasets/golden_vN.jsonl` | 확정 데이터셋 |
| `k8s/ragas-eval-job.yaml` | 평가 Job |
| `tests/` | 변환·저장 단위 테스트 |

## 명령어

- `ragas_eval`: 프로젝트 자체 패키지 (RAGAS 기본 명령어 아님)
- `python -m ragas_eval generate --testset-size 100 --out datasets/golden_candidates.jsonl`
- `python -m ragas_eval run --golden datasets/golden_v1.jsonl --repeat 3`
- `python -m ragas_eval run --golden datasets/golden_v1.jsonl --offline`

## 실행 환경

| 항목 | 값 |
| --- | --- |
| 형태 | K8s Job (`generate`는 로컬) |
| 데이터셋 | Job 이미지에 `datasets/` 포함 |
| `backoffLimit` | 0 |
| `activeDeadlineSeconds` | 3600 |
| 시크릿 | `OPENAI_API_KEY`, `DATABASE_URL` |
| 의존 | RAG Service (`RAG_BASE_URL`) |
| 동시성 | `asyncio.Semaphore(5)` |

## 선행 작업

| 항목 | 위치 | 담당 |
| --- | --- | --- |
| `policy_chunk` 청킹·임베딩 적재 | 미정 | 미정 (ETL / RAG) |
| 파이프라인 구현 (`runner`, `retrieval/vector`, `generator`) | `YouthLink_RAG` | RAG |
| `/internal/pipeline` + `debug` trace | `YouthLink_RAG/app/api/internal.py` | RAG |
| `load_policies.py` `__main__` 들여쓰기 수정 | `youthlink-data-pipeline` | ETL |
| 평가 실행 주체 결정 | - | 팀 |

## 구현 계획

| 단계 | 작업 | 방식 | 선행 |
| --- | --- | --- | --- |
| 1. 기반 | `pytest.ini`, `conftest.py`, 공유 타입 | 순차 | - |
| 2. 독립 모듈 | `policy_source`, `dataset`, `rag_client`, `scorer`, `repository` | 병렬 5 | 1 |
| 3. 조합 모듈 | `generate`, `runner` | 병렬 2 | `generate` ← `policy_source`, `dataset` / `runner` ← `dataset`, `rag_client`, `scorer`, `repository` |
| 4. 배포 | `Dockerfile`, `k8s/ragas-eval-job.yaml` | 순차 | 3 |

| 공유 타입 | 위치 | 사용처 |
| --- | --- | --- |
| `GoldenSample` | `dataset/dataset.py` | `generate`, `runner` |
| `RagResult` (`answer`, `retrieved_contexts`, `chunks`, `latency_ms`, `tokens`) | `rag_client/rag_client.py` | `runner` |
| `ScoreResult` (지표 4개, `errors`) | `scorer/scorer.py` | `runner`, `repository` |

## 구현 체크리스트

- [x] 1-1. `pytest.ini` (`db`, `llm` 마커, 기본 `-m "not llm"`)
- [x] 1-2. `tests/conftest.py` (가짜 정책·샘플 fixture)
- [x] 1-3. `GoldenSample`, `RagResult`, `ScoreResult` 정의
- [ ] 2-1. `policy_source` + 테스트
- [ ] 2-2. `dataset` + 테스트
- [ ] 2-3. `rag_client` + 테스트 (`httpx.MockTransport`)
- [ ] 2-4. `scorer` + 테스트 (`AsyncMock`, NaN → NULL)
- [ ] 2-5. `repository` + 테스트 (mock, `db` 마커 통합)
- [ ] 3-1. `generate` + 테스트
- [ ] 3-2. `runner` + 테스트 (`--repeat`, `--offline`, 재개, 실패 시 `FAILED`)
- [ ] 4-1. `Dockerfile` (Python 3.12, `datasets/` 포함)
- [ ] 4-2. `k8s/ragas-eval-job.yaml`

## 운영 체크리스트

- [ ] 1. `db/ragas_schema.sql` 적용
- [ ] 2. `policy` → `Document` → `TestsetGenerator`로 `question`, `ground_truth` 생성
- [ ] 3. 검수 → `golden_v1.jsonl` 고정
- [ ] 4. `run --offline`으로 채점 경로 검증
- [ ] 5. run INSERT, 질문 samples INSERT
- [ ] 6. RAG 호출 → `answer`, `contexts` UPDATE
- [ ] 7. 채점 → 지표 4개 UPDATE
- [ ] 8. 집계 → run UPDATE
- [ ] 9. 3회 반복 → 평균·노이즈 폭 기록
