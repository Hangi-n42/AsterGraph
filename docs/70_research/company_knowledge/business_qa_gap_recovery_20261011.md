# 저장 QA 공백의 제한 재검수 연결과 P2 미복구 기록

2026-10-11. 출발 커밋 `49f04cd4d67b23e27cdf3796e19ea80c4c1eca2a`. 기존 `feature/business-requirement-answer-flow`에서 수행했다.

이 문서는 첫 2회 호출의 실패 기록이다. 이후 확인된 계약 결함 수정과 실제 P2 복구·같은 질문 QA 결과는 [후속 완료 보고](business_qa_recovery_use_20261011.md)에 기록했다. 아래 결과와 미구현 표시는 첫 비교 종료 시점 기준이며, 실패 raw와 당시 동결 코드는 그대로 보존한다.

**결과: 제품의 QA→재검수 연결은 구현·검사했으나 P2 카드 선택지는 복구하지 못했다.** 실제 모델 2회에서 표현 완료 오판이 남았고 `maintain`으로 끝났다. 신규 후보·복구·자기원문 검수·QA는 각각 0건이다. 정상 후보 7개와 원문 의미 38개는 그대로 보존했다. 전체 목표는 미완료다.

## 진행 이유와 제품 변경

이전 `P2_R_actual`은 가족관계증명서가 “포함된다”는 후보를 증명서 **또는** 카드라는 전체 선택지의 표현으로 잘못 판정했다. 별도 실제 QA는 카드 선택지가 저장 지식에 없다고 지적했지만, 이 관찰을 표현 재검수로 전달하는 제품 진입점이 없었다. 종합 검수에는 과거 공개 작업의 원문·후보 버전 유효성 표시도 없었다.

- 이 단계의 `POST /knowledge/business/runs/{run_id}/answer-rechecks`는 저장 QA 실행 ID와 기존 공개 task ID만 받았다. 정답 문장·의미키·판정을 호출자가 지정할 수 없다. 후속 버전은 의미 판정과 별개인 `repair` 실행 정책을 추가했다.
- `business_feedback.start`는 성공한 실제 QA 출력과 해당 unit, 원래 snapshot/run, 현재 원문·후보·질문·요구·공개 작업·기존 의미·정확 근거 주소를 대조한다. 일반 실행 ID를 QA ID로 주면 입력 오류로 처리한다. 원본을 변경하지 않고 복제 실행에 관찰 출처와 버전 receipt를 저장한다.
- 한 task의 기존 의미가 하나로 연결된 경우에만 원래 `unconfirmed` 문자열을 미검증 표현 관찰로 전달한다. 여러 의미에 걸친 관찰은 `deferred`로 보존한다. QA 문장으로 의미를 추정하거나 후보 오류·원문 반증·자동 복구를 만들지 않는다.
- worker는 기존 `assess(focus)`→필요한 부분 `reassess_challenges`→`repair`→새 후보 자기원문 검수→재검수→변경안 저장 경로를 사용한다. 미해결 QA 관찰 자체는 원문 재판정 사유가 아니다. 실제 R이 활성 의미의 원문 오류를 발견하면 기존 부분 재판정을 사용한다. 전체 요구 완료로 승격하지 않는다.
- `public_work_records`가 QA와 R에 같은 원문·후보·요구 binding, original unit, 과거 기록이라는 authority를 제공한다. 과거 scope 객체는 보존한다.

## 고정 입력과 실행 경계

새 실행은 기존 P2 DB를 복사했다. 별도 QA DB에서 원래 QA와 snapshot을 원형 그대로 가져오고, 이미 존재하는 원래 검수 실행은 전체 행 일치를 확인했다. 이 import는 분리된 진단 DB를 합치는 준비 작업이며 제품이 임의 QA 응답을 입력받는 기능은 아니다.

| 항목 | 식별자·범위 |
| --- | --- |
| 직전 P2 실행 | `739e39283b3e4247b3c5eab48c9c6d8e` |
| 실제 저장 QA | `45f21a71e7cb45b0b73902e5d12edf83` |
| QA 원래 snapshot | `49820ce73c3243559ba9cae4bdf72199` |
| QA 원래 검수 실행 | `8c361d3e524b4edc8a6e21983c40c5c2` |
| 연결 task | `museum-4/context1` / 개인 증빙서류 |
| 기존 의미 | `batch2:multi_child_proof_documents` |
| 새 실행 | `7d9dc000ff104510b825411ab62e1552` |
| 새 assessment | `eeb0ede8d04442b387580b534a390d1f` |
| 유지 입력 | 원문 8블록, 의미 38개, 후보 7개, 기존 공개 항목과 요구 |

공개 질문은 “어린이박물관의 사전 승인·예약 취소·비예약자 동반 입장과 증빙서류 안내는 무엇인가?” 그대로다. 현재 QA 후보 풀과 원래 snapshot/run의 전체 객체를 별도로 대조했으므로, 더 오래된 scope의 `candidate_binding_valid=false`만으로 실제 QA 관찰을 버리지 않았다. 이 false는 과거 scope 판정의 유효성에 관한 정보다.

잘못된 단체 비예약 입장 관련 QA 관찰 `museum-3/context2`는 기존 의미 3개에 걸쳐 있어 `deferred`가 됐다. 이는 주소 모호성에 대한 native0 경계 확인이다. 시스템이 해당 QA 문장의 의미 오류를 판별했다는 증거는 아니다.

## 실제 판단과 행동

| 단계 | 확인 결과 | 행동 효과 |
| --- | --- | --- |
| 표현 검수 local | QA 관찰을 받았다. 카드 명시가 없고 증명서 하나를 부분적으로 표현한다고 설명하면서도 `represented`를 반환했다. | 이전 전체 표현 오판 유지 |
| 종합 검수 join | QA 관찰을 `resolved`로 수용하고 “부분 표현”이라고 설명했다. 그러나 `checks=[]`를 반환했다. | 명시적인 partial/missing 변경 행 없음 |
| 정규화·행동 | 기존 local `represented`가 유지돼 `maintain`이 남았다. | recover 0, 새 후보 0 |
| 원문 재판정 | 실제 활성 원문 의미의 오류 이의가 없었다. | 추가 원문 모델 호출 0 |
| 후속 활용 | 복구 효과가 없어 새 후보 자기원문 검수와 새 QA를 실행하지 않았다. | 같은 질문에서의 개선은 확인하지 못함 |

`resolved`는 관찰에 답했다는 표시이며 잔여 표현이 저장됐다는 증거가 아니다. join의 설명과 행동 필드가 어긋난 상태를 성공으로 세지 않았다. 모델 이유 문장에서 “부분”을 검색해 서버가 강제로 `partial/recover`를 만들지도 않았다.

binding 표시를 추가했지만 join 이유에는 단체 취소 후보가 없다는 범위 밖 서술이 여전히 남았다. 현재 후보 7개에는 이전 P1에서 복구한 단체 취소 후보 3개가 있다. 따라서 과거 기록의 지위 표시만으로 현재 전체 상태에 대한 오판이 해소됐다고 주장할 수 없다. 실제 local에는 전체 7후보가, join에는 기존 선택 경로의 관련 5후보가 제공됐다. 실행의 후보 풀과 각 모델 호출에 전달된 범위는 구분한다.

기존 `represented` 행의 설명은 종합 입력에서 축약되며, local raw의 `represented_content/missing_content`는 partial 행에만 정규화해 전달하는 기존 계약이다. 이번 local의 자기모순과 join의 `checks=[]`가 최종 `maintain`으로 이어진 정확한 경계를 후속 검토 대상으로 남겼다. 이 기록은 다음 수정이나 효과를 이미 검증했다는 뜻이 아니다.

## 회귀·비용·한계

- 관련 검사 63개 통과, 133.59초. 최초 59통과/1실패는 조회 API가 붙이는 파생 `counts`를 저장 원본과 비교한 테스트 문제였으며 DB 원본 직접 대조로 수정했다. 검사 통과는 모델 의미 개선 증거가 아니다.
- 정상 7후보 전체 객체, 원문 38의미, 기존 candidate review receipt 및 현재 요청·설정에 유효한 자기원문 검수 결과가 모두 동일하다. 7개 모두 기존 `supported` 결과를 정확 재사용했다. 새 의미 검수 성공으로 계산하지 않는다.
- 기존 bus QA 2개는 현재 코드에서 messages/schema/reference map과 답변 렌더링이 정확히 일치했다. 원본 DB SHA-256 `b85204999c9069cd629eab8a322454d3886adaf2830cea2fe7baa112c9d1165f`, 변경 없음, native 0. 버스 의미 성능을 새로 평가하지 않았다.
- 실제 모델 호출 2회: 입력 19,256 / 출력 1,564토큰, 모델 197.861705초, driver 205.636636초. 단계별 모델 시간은 local 91.452614초, join 106.409091초다. 사전 계획의 6회는 복구가 발생했을 때 예상한 경로이며 실제 호출 수가 아니다.
- 코드 11개 파일과 입력·driver를 실행 전에 동결했고 실행 후 11개 모두 일치했다. 기존 원본 DB 2개, 원래 run/QA/snapshot도 그대로다. 실행 전후 Ollama `/api/ps`는 비어 있다.
- 두 경계를 함께 변경한 단일 개발 사례다. 종합 설명은 QA의 부분성 지적을 수용하는 방향으로 변했지만, 표현 상태·복구·저장 행동 개선은 0이다. 이 설명 변화와 행동 실패를 분리하며, 일반 정확도나 두 변경 각각의 인과 효과를 산출하지 않는다. 100% 정확도나 기존 정상 사례의 ceiling을 완료 gate로 사용하지 않았다.
- 같은 실패가 확인돼 모델 재시도·새 QA·P1/버스/전체 재추출을 반복하지 않았다. 병합·배포·인간 승인은 수행하지 않았다. 변경안 저장은 전체 지식 승인이나 HITL 증거가 아니다.

## 증거와 다음 작업

작업 증거: `data/knowledge/evaluations/business_qa_gap_recovery_20261011/`.

- `plan.md`, `plan_addendum_before_native.md`, `preparation/provenance.json`, `preparation/bindings.json`, `preparation/false_qa_counterexample.json`: 사전 기준·실제 QA 연결·보류 경계.
- `freeze.json`, `frozen_code/`, `preflight/packets.json`, `actual/request1.json`, `actual/request2.json`: 동결 코드·요청·스키마·참조 입력.
- `actual/run.json`, `actual/knowledge.db`, `actual/new_assessments.json`, `actual/new_claims.json`, `actual/new_repairs.json`: 실제 raw·정규화·저장·행동.
- `semantic_result.json`, `actual/request_ledger.json`, `actual/code_integrity_after.json`, `bus_control_boundary.json`, `tests_boundary.log`: 보존·실패·비용·회귀 검사.
- 독립 보존본: `/Users/hyeongi/.codex/artifacts/business-qa-gap-recovery-20261011`의 manifest와 최종 커밋 receipt. 기존 실험 보존본은 변경하지 않는다.

다음 작업은 coordinator가 이 실패를 기존 #616/#617/#620 및 연구 원장과 연결하고, 종합 검수의 명시 판정 누락과 표현 완전성 판단을 후속 범위로 결정하는 것이다. `contract_review_readonly.md`에 이의가 있는 의미만 필수 최종 기여 행을 받는 미구현 계약 검토를 별도로 남겼다. 이번 세션은 반복 실험으로 확장하지 않는다. P2의 실제 저장→자기원문 지지→같은 공개 질문 활용은 여전히 미완료다. 현재 사용자 결정이 필요한 사항 없음.
