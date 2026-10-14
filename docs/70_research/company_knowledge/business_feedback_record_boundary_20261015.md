# 저장 QA 재검토의 중복 관찰·완료 요청 경계 — 2026-10-15

## 범위와 근거

W4의 기록·행동 경계 결함을 수정했다. 저장된 QA 관찰이 중복 주입되면, 같은 정상 교정 판정을 다시 미해결로 만들 수 있었다. 이 수정은 OR 누락 자동 검출이나 새 모델의 의미 판정 개선을 증명하지 않는다. 전체 W4와 #616/#617/#620의 필수 결과는 남아 있다.

- 기준 코드: `373cc5b08a9a5be7ea970ad5e2618dd7bedfcf40`
- 격리 checkout: `/Users/hyeongi/.codex/worktrees/business-feedback-boundary/Civil-Complaints-System`
- 브랜치: `codex/business-feedback-boundary`
- 원본은 읽고 새 DB 복사본에 진단 실행을 저장했다. 기존 테스트·원본 DB·원시 응답을 변경하지 않았다.
- 모델 생성·임베딩 호출은 0회다. 저장된 모델 식별자는 진단용으로 복사했으며 현재 모델을 새로 확인한 증거가 아니다.

## 확인한 결함과 변경

실제 QA `45f21a71e7cb45b0b73902e5d12edf83`, 작업 `museum-4/context1`의 재검토 결과 `7d9dc000ff104510b825411ab62e1552`를 기준으로 재현했다. 해당 source에는 이미 `qa_gap_06873d806a40dd9d6fb02663` 관찰이 있었지만 재검토 worker가 같은 ID를 추가했다. 이전 관찰과 새 관찰은 검증 후 덧붙은 `candidate_binding_valid` 메타데이터 때문에 전체 사전 동등 비교로는 같지 않았다.

저장된 성공 실행 `0710c42c6d88461285423a9d01118240`의 최종 contribution을 고정한 상태에서도, 같은 관찰 2개가 생성하는 중복 resolution은 `finding_resolution_missing_or_duplicate`로 미해결이 됐다. 관찰 1개는 같은 판정으로 해결됐다.

`business_feedback.py`의 두 경계만 변경했다.

1. 검증된 새 QA 관찰을 추가할 때 이미 존재하는 finding ID를 추가하지 않는다. 기존 관찰과 파생 검증 메타데이터를 보존한다. 과거 원본 기록이나 consumer의 중복 판정 규칙은 바꾸지 않는다.
2. 같은 원래 parent·QA·작업 목록·repair 정책의 완료 child를 현재 유효할 때 돌려준다. 원문·입력 버전·공개 항목, 현재 요구 버전과 assessment 주소·입력 fingerprint, 변경안 후보와 무효화 기록을 대조한다. 전체 실행 payload를 리스트에 적재하지 않고 순차 조회한다.

최신 child를 선택한 명시적 재검토, 새 QA, 정책 변경, 실패 결과를 기준으로 한 재시도는 새 실행으로 구분한다. 같은 QA ID를 영구 차단하는 규칙이나 새 강제 실행 옵션을 만들지 않았다. 이 API가 재검토를 허용한다는 사실은 동일 모델·동일 원인 반복 실험을 승인하는 근거가 아니다.

## 검증 결과

| 확인 | 관측 결과 |
|---|---|
| 변경 전 신규 회귀 검사 | 완료 요청 재사용·관찰 중복 방지 2건 실패 |
| 최종 코드의 해당 단위검사 | 34개 통과 |
| 추가 관련 범위 검사 | 147개 통과, 기존 2개 실패 |
| 기준 checkout에서 실패 2건 확인 | 같은 실패 재현 |
| 실제 복사 DB의 동일 완료 요청 2회 | HTTP 200/200, 같은 child, `reused=true`, worker 제출 0회, 기존 행 무변경 |
| 실제 복사 DB의 최신 child 명시 재검토 | 새 child 생성, worker 제출 1회, 모델 직전 source 관찰 1개·전체 source와 검증 메타데이터 보존 |
| 같은 저장 contribution의 중복/단일 관찰 대조 | 중복 2개는 미해결, 단일 1개는 해결 |
| 정상 카드 자료 보존 | 기존 7후보·원문 38의미 보존, 기존 최종 8후보·카드 작업 QA 연결 유지 |
| 버스 자료 고정 회귀 | 과거 snapshot 무효화와 저장된 영향 판정 유지, 새 의미 평가 없음 |
| 보존 | 원본 3DB와 기준 복사 3DB의 SHA-256 동일, 기존 6서버 PID·포트 유지 |

추가 범위 검사에는 해당 단위검사가 포함되므로 검사 수를 합산하지 않는다. 순차 조회 변경 뒤 최종 34개 검사와 실제 자료 API 재생을 확인했다.

명시 재검토 worker 진단은 `RuntimeError: diagnostic_stop_before_model`로 의도적으로 종료했다. 이는 worker가 모델 직전에 전달하는 기록을 관찰한 결과이며, 새 검수·복구·발행·QA까지 완료한 실제 모델 실행이 아니다. 기존 행은 그대로 보존했다.

기존 실패는 `test_repair_omits_only_past_source_history_and_corrects_shared_target_once[maintain/correct]` 두 경우다. 검사에서 기대하는 source context와 현재 `business_run.repair`가 전달하는 요약 context가 다르다. 기준 코드에서도 동일하므로 이번 변경으로 수정하지 않았다. 어느 계약을 바꿔야 하는지는 해당 소유 범위에서 별도로 판단해야 한다.

## OR 판정 경계와 실험 횟수

첫 QA 공백 재검토의 원시 local output부터 status가 `represented`였다. 설명과 `missing_content`에는 다둥이카드 명시 누락을 인정하면서도 전체 표현을 충족한다고 판단한 모순이 있다. normalized final도 `represented`였으므로 서버가 원시 `partial`을 `represented`로 바꿨다는 결론은 성립하지 않는다. 자유문장을 파싱해 임의로 partial·복구로 바꾸는 규칙은 추가하지 않았다.

이번 작업은 기록 경계 원인 수정 1회와 모델 없는 계약·저장 응답 재생이다. 카드 OR의 역사적 의미 조정 횟수를 초기화하지 않았다. c47·K02·NLC-C04의 기존 최소 6회 기록을 유지하며 새 의미 모델 실행은 없었다.

## 증거와 다음 작업

증거 폴더: `/Users/hyeongi/.codex/artifacts/business-feedback-boundary-20261015`

- `isolation-and-baseline.json`: 격리 위치·기준 SHA·원본/복사 DB 해시
- `repeat-qa-before-result.json`: 실제 관찰 중복과 같은 contribution의 해결/미해결 대조
- `record-boundary-after-result.json`: 실제 API 재사용·명시 재검토·보존·고정 회귀 결과
- `or-judgment-boundary-readonly.json`: 원시/정규화 OR 판정 대조
- `final-feedback-tests.xml`: 최종 34개 검사 결과
- `baseline-existing-failures.xml`: 기준 코드의 기존 실패 2건
- `final-preservation.json`: 최종 원본 DB·checkout·기존 서버 보존 확인

조정 세션은 이 수정의 통합과 기존 실패의 소유 범위를 별도로 관리한다. 전체 W4의 의미 품질·자동 검출·교정·QA 필수 결과는 별도 검증이 필요하다. 이번 범위에서 사용자 결정이 필요한 사항은 없다. PR 병합·배포와 새 모델 실험은 수행하지 않았다.
