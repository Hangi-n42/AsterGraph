# 저장 후보에 원래 공개 요구 연결

`POST /api/v1/knowledge/business/runs/{run_id}/requirement-links`

요구·평가가 없는 종료된 `stored_pool`에 기존 공개 요구를 연결하고 별도 검토 준비 실행을 저장한다. 기존 `reassess_run_id` 경로와 달리 모델 작업을 제출하지 않는다.

요청은 `expected_parent_fingerprint`, `reference_run_id`, `expected_reference_fingerprint`, `requirement_id`, `expected_requirement_revision`, `idempotency_key`, `actor`, `reason`이다. fingerprint는 저장 실행 payload의 digest이며 GET 실행 응답의 파생 `counts`는 제외한다.

- 원장의 현재 요구와 과거 참조 실행의 원래 question·criterion·revision·출처 범위가 같아야 한다. 공개 answer_items는 과거 실행에서 가져와 기존 정확 인용 검사를 통과해야 한다.
- 원문·196개 등 실제 저장 주장·그래프·개념·정정·생산자·실패 기록은 그대로 보존한다. 과거 모델 unit의 존재와 새 실행의 모델 호출 0을 구분한다.
- 새 실행의 `requirements`와 `answer_items`는 연결되지만 `assessments=[]`이다. 과거 평가·승인은 참조 ID/hash로만 남고 현재 평가나 승인으로 복제하지 않는다. 요구 원장 자체와 이전 snapshot도 수정하지 않는다.
- 동일 멱등 키의 동일 요청은 기존 자식을 반환한다. 다른 요청 또는 달라진 부모·참조·요구 revision은 충돌이다.
- 기존 재구축 guard와 게시/자격 검사를 재사용한다. 새 후보의 eligible은 실제 평가로만 결정되며 연결 준비만으로 생기지 않는다.
- 이 준비 실행은 `review_draft_only`이다. 직접 원문 QA는 검색·모델 호출 전에 `needs_review`로 반환하고, 사용 결정 API도 차단한다. 다른 기존 원문 QA 정책은 바꾸지 않는다.

기존 화면의 사용·검토 상태에서 원래 요구와 기준, 정확 공개 항목, 미평가·미승인, 과거 참조를 확인한다. 현재 요구 원장의 과거 상태와 이 준비본의 평가 상태를 구분한다. 새 사용 버전이나 활성 snapshot은 만들지 않는다.
