# ETL DB 스키마

## 개요

PostgreSQL + pgvector 단일 DB다. ETL이 정책을 적재하고 챗봇이 검색·응답에 쓰며, RAGAS 평가는 ETL이 넘겨준 정책 스냅샷으로 평가 데이터셋을 만들어 챗봇을 채점한다.

| 테이블 | 쓰는 쪽 | 읽는 쪽 |
| --- | --- | --- |
| `policies` | ETL | 챗봇, 평가 |
| `policy_attachments` | ETL | ETL |
| `policy_chunks` | ETL | 챗봇 |
| `etl_runs` | ETL | 운영, 평가 |
| `chat_sessions`, `chat_messages` | 챗봇 | 챗봇 |

### RAGAS 데이터셋 생성

| 항목 | 내용 |
| --- | --- |
| 원천 데이터 | `is_active = true` 정책 스냅샷. `policies` 전체 컬럼에서 `raw_json` 제외, 정규화 후 값 그대로 |
| 추가 필드 | `attachment_parse_status`(none / ok / failed), `reviewed`(`full_text` 검수 여부, 약 100건) |
| 저장 위치 | `s3://{S3_BUCKET}/eval/snapshots/policies_YYYY-MM-DD.jsonl` + `.meta.json` |
| 생성 방식 | 검수된 정책의 `full_text`를 1건씩 RAGAS 테스트셋 생성기에 넣고 사람이 검수. 생성 모델은 답변 모델과 다르게 |
| 데이터셋 구성 | `golden_v1.jsonl`로 git 고정. 단일 정책 질문 100 내외, 답 없는 질문 10~20, 경계값 프로필 추천 30~50 |
| 평가 DB 고정 | 스냅샷 기준일 상태로 유지, `policy_chunks`도 같은 `index_version`. 변경 정책은 `etl_runs.stats`의 `changed_policy_ids`, `deactivated_policy_ids`로 추적 |

### 평가 지표

| 지표 | 방식 | 보는 것 |
| --- | --- | --- |
| Context Recall | RAGAS | 필요한 근거를 빠짐없이 가져왔나 |
| Context Precision | RAGAS | 쓸모 있는 근거가 위에 있나 |
| Faithfulness | RAGAS | 근거에 없는 말을 지어냈나 |
| Factual Correctness | RAGAS | 금액, 나이, 기간 같은 사실이 맞나 |
| 답 없는 질문 처리율 | 판정 스크립트 | 없는 정책을 지어내지 않았나 |
| 응답 지연 p50/p95, 질문당 토큰 | trace 집계 | 비용과 속도 |

| RAGAS 입력 | 값 |
| --- | --- |
| `user_input` | 데이터셋 `question` |
| `retrieved_contexts` | 챗봇 `trace.contexts` (`policy_chunks.text`) |
| `response` | 챗봇 최종 답변 |
| `reference` | 데이터셋 `reference` (`full_text` 기반) |

### 평가 흐름

우선 단일 정책 질문만 진행한다.

- [ ] 1. 데이터셋 생성: 정책 `full_text`를 1건씩 RAGAS 테스트셋 생성기에 넣어 LLM으로 `question`, `reference` 생성
- [ ] 2. 데이터셋 검수: 사람이 검수 후 `golden_v1.jsonl`로 고정
- [ ] 3. RAG 실행: 하네스가 질문을 챗봇에 `?debug=true`로 보내 답변과 trace 저장
- [ ] 4. 채점: 질문, `trace.contexts`, 답변, 정답을 RAGAS에 넣어 채점 LLM으로 4개 지표 산출
- [ ] 5. 반복: 같은 조건으로 3회 실행해 평균과 노이즈 폭 기록

### `ragas_eval` 명령어

- `ragas_eval`은 RAGAS 기본 명령어가 아니라 이 프로젝트에서 만든 패키지다(`RAGAS/ragas_eval/`).
- 명령어 정의: `ragas_eval/cli.py`
- `python -m ragas_eval generate --snapshot <S3 또는 로컬 경로>`: 정책 스냅샷에서 질문·정답 후보 생성(`ragas_eval/generate.py`) → `golden_candidates.jsonl`
- `python -m ragas_eval run --golden golden_v1.jsonl`: 검수·확정된 데이터셋으로 평가 실행
- `ragas` 라이브러리는 이 코드 안에서 생성·채점 도구로 호출한다.

## policies

| 컬럼 | 타입 | NULL | 기본값 | 제약 |
| --- | --- | --- | --- | --- |
| `id` | TEXT | NOT NULL | | PK |
| `last_modified_at` | TEXT | NOT NULL | | |
| `first_registered_at` | TEXT | NULL | | |
| `categories` | TEXT[] | NOT NULL | `'{}'` | |
| `subcategory` | TEXT | NULL | | |
| `keywords` | TEXT[] | NOT NULL | `'{}'` | |
| `zip_codes` | TEXT[] | NOT NULL | `'{}'` | |
| `sido_codes` | TEXT[] | NOT NULL | `'{}'` | |
| `min_age` | INT | NULL | | |
| `max_age` | INT | NULL | | |
| `marital_code` | TEXT | NOT NULL | `'0055003'` | |
| `income_type_code` | TEXT | NOT NULL | `'0043001'` | |
| `income_min` | INT | NULL | | |
| `income_max` | INT | NULL | | |
| `education_codes` | TEXT[] | NOT NULL | `'{}'` | |
| `major_codes` | TEXT[] | NOT NULL | `'{}'` | |
| `job_codes` | TEXT[] | NOT NULL | `'{}'` | |
| `special_codes` | TEXT[] | NOT NULL | `'{}'` | |
| `apply_type_code` | TEXT | NOT NULL | | |
| `apply_start` | DATE | NULL | | |
| `apply_end` | DATE | NULL | | |
| `biz_start` | DATE | NULL | | |
| `biz_end` | DATE | NULL | | |
| `title` | TEXT | NOT NULL | | |
| `description` | TEXT | NULL | | |
| `support_content` | TEXT | NULL | | |
| `extra_qualification` | TEXT | NULL | | |
| `excluded_target` | TEXT | NULL | | |
| `income_etc` | TEXT | NULL | | |
| `apply_method` | TEXT | NULL | | |
| `screening_method` | TEXT | NULL | | |
| `documents` | TEXT | NULL | | |
| `etc_note` | TEXT | NULL | | |
| `org_name` | TEXT | NULL | | |
| `operator_name` | TEXT | NULL | | |
| `first_come` | BOOLEAN | NOT NULL | `FALSE` | |
| `apply_url` | TEXT | NULL | | |
| `ref_urls` | TEXT[] | NOT NULL | `'{}'` | |
| `full_text` | TEXT | NOT NULL | | |
| `raw_json` | JSONB | NOT NULL | | |
| `is_active` | BOOLEAN | NOT NULL | `TRUE` | |
| `fetched_at` | TIMESTAMPTZ | NOT NULL | `now()` | |

## policy_attachments

| 컬럼 | 타입 | NULL | 기본값 | 제약 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | NOT NULL | | PK |
| `policy_id` | TEXT | NULL | | FK → `policies(id)` ON DELETE CASCADE |
| `found_on` | TEXT | NULL | | |
| `file_url` | TEXT | NOT NULL | | |
| `file_type` | TEXT | NULL | | |
| `s3_key` | TEXT | NULL | | |
| `parse_status` | TEXT | NOT NULL | | |
| `parsed_text` | TEXT | NULL | | |
| `error` | TEXT | NULL | | |

| 제약 | 컬럼 |
| --- | --- |
| UNIQUE | (`policy_id`, `file_url`) |

## policy_chunks

| 컬럼 | 타입 | NULL | 기본값 | 제약 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | NOT NULL | | PK |
| `policy_id` | TEXT | NULL | | FK → `policies(id)` ON DELETE CASCADE |
| `chunk_idx` | INT | NOT NULL | `0` | |
| `text` | TEXT | NOT NULL | | |
| `embedding` | VECTOR(1536) | NOT NULL | | |
| `index_version` | TEXT | NOT NULL | `'v1'` | |
| `is_truncated` | BOOLEAN | NOT NULL | `FALSE` | |

| 제약 | 컬럼 |
| --- | --- |
| UNIQUE | (`policy_id`, `index_version`, `chunk_idx`) |

## etl_runs

| 컬럼 | 타입 | NULL | 기본값 | 제약 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | NOT NULL | | PK |
| `mode` | TEXT | NOT NULL | | |
| `status` | TEXT | NOT NULL | | |
| `stats` | JSONB | NULL | | |
| `started_at` | TIMESTAMPTZ | NOT NULL | | |
| `finished_at` | TIMESTAMPTZ | NULL | | |

## chat_sessions

| 컬럼 | 타입 | NULL | 기본값 | 제약 |
| --- | --- | --- | --- | --- |
| `id` | UUID | NOT NULL | | PK |
| `client_id` | | | | |
| `title` | | | | |
| `categories` | | | | |
| `profile` | JSONB | | | |
| `created_at` | | | | |
| `last_active_at` | | | | |

## chat_messages

| 컬럼 | 타입 | NULL | 기본값 | 제약 |
| --- | --- | --- | --- | --- |
| `id` | | NOT NULL | | PK |
| `session_id` | | | | FK → `chat_sessions(id)` ON DELETE CASCADE |
| `role` | | | | |
| `content` | | | | |
| `sources` | TEXT[] | | | |
| `trace` | JSONB | | | |
| `created_at` | | | | |
