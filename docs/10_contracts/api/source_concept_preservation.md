# 부분 재구축의 기존 개념 결과 보존

`GET /api/v1/knowledge/business/source-concept-preservations/{parent_run_id}`는 종료된
`whole_source_v1` 업무 실행의 보존 가능 대상과 미처리 대상을 반환한다.
전체 원문 문맥 정책에서 실제 입력이 확인된 비분할 과거 결과만 지원한다.
다른 문맥 정책은 거절하고, 과거 분할 결과는 기존 `prepare` 검토 대상으로 남긴다.

`POST /api/v1/knowledge/business/source-concept-preservations`는 `parent_run_id`와
GET의 `parent_fingerprint`를 `expected_parent_fingerprint`로 받는다.
원문·생산 계보·후보·그래프·대상·실제 이웃·메시지·선택·입력 fingerprint,
과거 실행 한도·완료 상태·work·binding을 검사한 뒤 별도 `business` 실행에 보존한다.
기준 변경은 충돌이며 같은 요청은 같은 실행을 반환한다. 저장 전 중단은 트랜잭션으로 취소된다.

보존된 concept/unit/work/binding은 원형과 과거 runtime을 유지한다.
이 작업은 현재 runtime의 정확 캐시 재사용이나 새 생성·의미 검수·승인이 아니다.
`new_work_connected=false`, `current_runtime_exact_cache=false`, 새 모델 호출 0을 기록한다.
미검토 `has_concept`만 보존하고 승인 상태를 이월하지 않는다.
변경·신규 대상은 `pending`에 남으며 이 수는 실제 생성 호출 상한이 아니다.

후속 `POST /business/concepts`는 기존 개체 대상 계약이 기본이다.
명시적 `include_events_and_relations=true`에서는 현재 그래프의 사건·관계도 선택할 수 있다.
실제 후속 작업은 기존 `prepare`의 문맥·용량·관계 분할 계약을 사용한다.
완료된 child의 읽기 투영은 부모·snapshot에 저장되지 않으므로,
새 사용 버전의 검수·결정과 동일시하지 않는다.

보존 실행은 `stored_pool`과 원본 생산 실행을 가리키는 review guard를 가진다.
재개·재검수는 이 원형·작업 원장·실패 계보를 유지하며 원문을 다시 추출하지 않는다.
미처리 대상이 있거나 원래 실패가 남으면 `partial`을 유지한다.
