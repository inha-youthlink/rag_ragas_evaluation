# 데이터셋 생성 품질 보정 (golden_v1 준비)

golden_v0(시험 10건)에서 드러난 생성 품질 문제 3가지를 고쳤다.

## 요약

| 항목 | 기존 문제 | 원인 | 해결 |
| --- | --- | --- | --- |
| 소득 조건 | 정책 문서에 "소득 기준: 0원 ~ 0원", "0원 ~ 5000원" 같은 틀린 문장이 들어가고, 이 문장으로 만든 정답도 틀림 (golden_v0 2번) | 우리 `policy_source`가 DB 행을 문서로 바꿀 때 소득 조건 종류(`income_condition_code`)를 읽지 않고, 만원 단위 금액을 원으로 해석. 0("경계 없음")도 금액으로 처리 | 종류 코드로 분기해 "무관", "연소득 5,000만원 이하", 기타 설명 문장으로 표기. 설명이 `-`뿐이면 생략 |
| 표본 추출 | 질문 10건의 정책이 113470~113493번대에 몰림. 대상 정책 전체를 넣어 분석 비용이 정책 수만큼 늘어남 | 생성기는 넣은 정책을 고르게 고르는 것을 보장하지 않음. 생성기에 넣을 정책 범위를 제한하는 기능이 없음 | `generate --policy-limit N`: 정책 번호순 정렬 후 고정 시드로 N건 무작위 추출해 생성기에 전달 |
| 페르소나 | 질문 말투가 어색함 ("청년 정책 자문과 여론 수렴 활동에 관심이 있는 청년의 관점에서…"). 페르소나 이름 불일치로 생성이 멈춤 ("김도윤 (재직 기술인력)") | TestsetGenerator가 정책 문서 요약을 보고 "이 문서에 관심 있을 인물"을 페르소나로 자동 생성. 서비스 사용자인 청년이 아니라 문서 내용에서 나온 인물이라 청년 사용자 초점에서 벗어남 | 청년정책 사용자 5명을 직접 지정해 생성기에 전달. 자동 생성 단계를 건너뜀 |

## 1. 소득 조건

### 문제 위치

DB 저장은 정상이고, DB에서 꺼내 생성기용 문서로 바꾸는 우리 코드(`ragas_eval/policy_source/policy_source.py`)에 문제가 있었다.

| 단계 | 담당 | 하는 일 | 문제 여부 |
| --- | --- | --- | --- |
| 1 | ETL | 온통청년 API → DB `policy` 저장 | 정상 |
| 2 | 우리 `policy_source` | DB 행 → 정책 1건당 텍스트 문서 1개 | **잘못 변환** |
| 3 | 우리 `generate` | 문서를 TestsetGenerator에 전달 | 틀린 문장이 그대로 전달 |
| 4 | ragas TestsetGenerator | 문서만 보고 질문·정답 생성 (DB는 보지 않음) | 틀린 문장으로 정답 생성 |

### DB 소득 컬럼 (온통청년 `earnCndSeCd`)

| 컬럼 | 의미 |
| --- | --- |
| `income_condition_code` | 0043001 무관 / 0043002 연소득 / 0043003 기타 |
| `min_income`, `max_income` | 연소득 하한·상한, 만원 단위, 0은 경계 없음 |
| `income_etc` | 기타 조건 설명 |

만원 단위는 정책 본문으로 확인했다 (본문 "연소득 5,000만원 이하" = `max_income` 5000).

### 변환 결과

| 소득 조건 | 정책 수 (로컬 3,149건 기준) | 수정 전 | 수정 후 |
| --- | --- | --- | --- |
| 무관 | 2,723 | 소득 기준: 0원 ~ 0원 | 소득 기준: 무관 |
| 연소득 | 45 | 소득 기준: 0원 ~ 5000원 | 소득 기준: 연소득 5,000만원 이하 |
| 기타 | 약 380 | 소득 기준: 0원 ~ 0원 (설명) | 소득 기준: (설명) |
| 기타, 설명이 `-`뿐 | 30 | 소득 기준: - | 소득 줄 생략 |

설명이 `-`뿐인 30건은 API 원본 값이다. ETL 수정 없이 변환 단계에서 빈 값으로 처리한다.

## 2. 표본 추출

| 항목 | 내용 |
| --- | --- |
| 명령 | `python -m ragas_eval generate --testset-size 130 --policy-limit 150` |
| 함수 | `generate.sample_documents(documents, limit)` |
| 순서 | ① 대상 정책을 `policy_no` 순으로 정렬 ② `random.Random(SAMPLE_SEED).sample(정렬된 목록, N)` ③ 뽑힌 정책을 다시 `policy_no` 순으로 정렬 |
| 고정 시드 | `SAMPLE_SEED = 20261010`. 정책 목록이 같으면 항상 같은 표본 → 정책 분석 캐시(`datasets/.cache/`) 키가 같아 재실행 시 분석 비용이 다시 들지 않음 |
| 입력 순서 무관 | 먼저 정렬하므로 DB 조회 순서가 바뀌어도 같은 표본 |
| `--policy-limit` 생략 또는 대상보다 큼 | 전체 정책 사용 (기존 동작) |
| 입력 검증 | 1 이상 정수만 허용 (`cli.positive_int`) |
| 한계 | 생성기에 넣는 범위를 고르게 할 뿐, 그 안에서 어떤 정책으로 질문을 만들지는 생성기가 정함. 생성 후 정책 분포를 확인 |

```python
def sample_documents(documents, limit):
    ordered = sorted(documents, key=lambda d: d.metadata["policy_no"])
    if limit is None or limit >= len(ordered):
        return ordered
    picked = random.Random(SAMPLE_SEED).sample(ordered, limit)
    return sorted(picked, key=lambda d: d.metadata["policy_no"])
```

## 3. 페르소나

| 항목 | 기존 (자동 생성) | 변경 (직접 지정) |
| --- | --- | --- |
| 만드는 주체 | TestsetGenerator가 정책 문서 요약으로 생성 | 코드에 고정 (`generate.YOUTH_PERSONAS`) |
| 페르소나 성격 | 문서 내용에서 나온 인물 (예: 재직 기술인력, 정책 자문 관심자) | 청년정책 서비스 사용자 |
| 질문 말투 | 문서 관점이라 어색함 | 사용자 관점 |
| 이름 | LLM이 이름을 변형해 답해 불일치 발생 | 고정 이름 5개 |
| 전달 방식 | 없음 (생성기 기본값) | `TestsetGenerator(persona_list=…)`, `generate(num_personas=5)` |

| 페르소나 | 관심사 |
| --- | --- |
| 대학생 | 장학금, 주거, 교육 지원의 자격과 금액 |
| 취업준비생 | 취업 지원, 직업 훈련, 구직활동 지원금과 신청 방법 |
| 사회초년생 | 월세, 자산 형성, 대출 지원과 소득 기준 |
| 청년 창업자 | 창업 자금, 임차료, 교육·컨설팅 지원 |
| 신혼부부 청년 | 전세·주택 대출과 월세 지원의 조건과 규모 |

한계: 페르소나는 질문의 말투와 관점만 바꾼다. 질문과 정답이 서로 다른 사업을 가리키는 문제(golden_v0 5번)는 검수에서 거른다.

## 변경 파일

| 파일 | 변경 |
| --- | --- |
| `ragas_eval/policy_source/policy_source.py` | `income_condition_code` 조회, 소득 줄 분기, 만원 표기 |
| `ragas_eval/generate/generate.py` | `sample_documents`, `SAMPLE_SEED`, `YOUTH_PERSONAS`, `generate(policy_limit=…)` |
| `ragas_eval/cli.py` | `generate --policy-limit` (1 이상) |
| `tests/` | 소득 분기 12건, 표본 재현성·범위, 페르소나 전달, CLI 파싱 |
| `docs/RAGAS_PRD.md`, `README.md` | 원천 텍스트, 정책 표본, 페르소나, 실행 예시 |

## 검증

| 항목 | 결과 |
| --- | --- |
| 테스트 | 288 passed (임시 PostgreSQL 포함) |
| 실제 DB 변환 확인 | 로컬 정책 3,149건에서 "0원 ~ 0원" 0건, 소득 줄 분포 위 표와 일치 |
| LLM 비용 | 없음 (생성 실행 전) |

## 참고

로컬 `policy_chunk`(RAG 연결 확인용 임시 적재)는 수정 전 변환 텍스트로 만들어 소득 줄에 "0원 ~ 0원"이 남아 있다. 다시 넣으면 임베딩 비용 약 $0.03.
