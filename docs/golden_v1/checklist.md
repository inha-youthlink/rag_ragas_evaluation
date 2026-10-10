# golden_v1 체크리스트

목표: 검수를 마친 100건 데이터셋(`golden_v1`)으로 baseline과 rag를 비교한다.

## 0단계: 준비 (비용 없음)

- [x] 계획 문서 (`checklist.md`, `context-notes.md`)
- [x] `policy_source` 소득 줄을 소득 조건 코드 기준으로 보정 (무관, 연소득 만원 단위, 기타) + 테스트
- [x] `generate --policy-limit N`: 대상 정책을 고정 시드로 표본 추출 + 테스트
- [x] 청년정책 페르소나 지정 + 테스트
- [x] 전체 테스트 통과, 커밋

## 1단계: 후보 생성 (비용 확인 후 실행)

- [ ] 예상 비용 계산, 사용자 승인
- [ ] `generate --testset-size 130 --policy-limit 150`
- [ ] 생성 건수, 제외 건수 보고

## 2단계: 검수 → golden_v1 확정

- [ ] 후보를 검수용 표로 변환, 의심 샘플 1차 표시
- [ ] 사용자 검수 (질문·정답 일치, 근거, 명확성, 정책 ID)
- [ ] 100건 `datasets/golden_v1.jsonl` 저장, 커밋

## 3단계: 평가 실행 (단계마다 비용 확인)

- [ ] `run --offline`
- [ ] `run --baseline --repeat 3`
- [ ] `policy_chunk` 방식 결정 (임시 적재본 유지 / 담당자 방식 교체)
- [ ] `run --repeat 3` (rag, 로컬 RAG 서버)

## 4단계: 결과 정리

- [ ] `datasets/golden_v1_summary.md` (baseline vs rag, 발표용 요약)
