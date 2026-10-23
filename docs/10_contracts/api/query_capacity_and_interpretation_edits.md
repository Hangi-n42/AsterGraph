# 고정 질문 용량 재개와 해석 필드 정정

두 경로는 원래 실행을 보존하고 새 실행을 저장한다. 기존 승인·의미 검증·요구 충족을 자동 승계하지 않는다.

## 필수 입력 용량 실패 재개

`POST /api/v1/knowledge/business/runs/{run_id}/capacity-resumes`

- 대상: `mandatory_capacity`로 실패한 그래프 종합 질문. 완료된 관계 선택 결과와 필수 입력을 그대로 복원한다.
- 요청: `expected_parent_fingerprint`, `expected_snapshot_fingerprint`, `expected_packet_fingerprint`, `context_tokens`.
- 검증: 저장 실행·선택 버전·필수 근거 순서·메시지·스키마·주소 맵·모델 식별자가 같아야 한다. 현재 원문 변경·요구 변경·사용 제한은 재개를 막는다.
- 실행: QA 문맥 한도만 늘린다. 선택기 문맥과 출력 한도는 유지하며 검색·PPR·임베딩·선택을 반복하지 않는다. 실제 입력 토큰 계수가 확인되지 않으면 생성 전에 차단한다.
- 동일 요청은 기존 자식 실행을 반환한다. 답변 저장·인용 검사는 일반 질문의 공통 경로를 사용한다. `answered`는 의미 정확성 보증이 아니다.

## 명시적 해석 필드 정정

`POST /api/v1/knowledge/business/changes/{changeset_id}/interpretation-edits`

- 요청: `expected_revision`, `idempotency_key`, `actor`, `reason`, `claims`.
- 주장별: `claim_id`, `expected_claim_version`, `expected_source_fingerprint`, `changes`.
- 필드별: `meaning_id`, `expected_meaning_version`, `field`, `before`, `after`, `evidence`, `reason`.
- 허용 필드: 현재 해석의 `conditions`, `relation_kind`. 기존 추출 스키마의 값만 허용한다. 원형 문장·Entity·주소·생산자 `interpretation.raw`·양태는 이 경로로 바꾸지 않는다.
- 자기 원문의 실제 인용과 현재 버전을 확인한다. 수정한 의미에는 새 ID를 부여하고 이전 해석, 전후 값, 이유, 행위자, 근거 주소를 보존한다. `actor`는 정정 기록자이며 사람의 사용 승인을 뜻하지 않는다.
- 의미 자체의 원문·범위 주소는 유효하고 오류가 비편집 participant의 주소 미확정에만 한정되면 두 필드를 정정할 수 있다. participant 오류·주소 상태는 보존하며, 이 예외는 주소 복구나 사용 자격을 부여하지 않는다. 의미/원문 인용 오류·누락·범위 이탈은 계속 거부한다.
- 새 후보는 `unreviewed`/의미 `unknown`이다. 과거 검수 응답은 보존하되 현행 exact 검사를 통과하지 못하면 현재 검수로 사용하지 않는다. 영향을 받은 개념만 `needs_review`로 표시하고 생산 기록을 보존한다.
- 모델·토큰 계수·자동 재검수·개념 재생성·승인·새 사용 snapshot 생성은 실행하지 않는다. 정정본의 읽기 화면은 일부 필드 정정과 미검증 상태를 구분한다.
- 같은 멱등 키의 같은 요청은 중복 생성하지 않는다. 같은 키의 다른 요청 또는 오래된 버전은 충돌이다.
- 읽기 화면의 해석 정정 이력은 현재 실행에 추가한 기록만 표시한다. 이전 정정은 부모 실행과 원본 기록에 보존하며, 현재 목록이 비어 있다는 이유로 전체 이력이 없다고 표시하지 않는다.

정정만 저장한 실행에 요구·평가가 없으면 자기 원문 검수만 추가해도 사용 검토 자격은 생기지 않는다. 같은 공개 요구의 원문 적용성·표현 검수 연결과 사용자의 별도 사용 결정이 필요하다.

## 소수 후보의 단일 자기 원문 검수

`POST /api/v1/knowledge/business/runs/{parent_id}/candidate-review-preparations`는 준비만 저장한다.

- 대상은 평가가 없는 종료된 `stored_pool`의 `review_draft_only` 실행이다. 기존 승인·평가가 있는 부모나 다른 제한검토 자식을 새 부모로 삼지 않는다.
- 요청은 `expected_parent_fingerprint`, `requirement_id`, `expected_requirement_revision`, `claim_ids`(중복 없는 최대 3개), `idempotency_key`, `actor`, `reason`이다. 부모 fingerprint는 GET 응답에서 파생 `counts`를 제외한 저장 payload의 digest다.
- 현재 부모·요구·원문 버전과 사용 상태, 저장 pool hash, 후보 출처 범위, 의미·참여자 실제 인용/주소를 확인한다. 미해결 participant 상태는 보존하고 의미 자체의 잘못된 주소를 우회하지 않는다.
- 전체 원장·그래프·생산자·과거 응답과 요구를 복사하되 새 게시/평가/사용 결정은 만들지 않는다. 저장 그래프는 그대로 복사한다. 그래프의 결정적 CPU 재계산과 모델 재추출·개념화는 다른 작업이며 이 준비 경로는 둘 다 하지 않는다.
- 별도 실행에 `candidate_review_scope`와 `phase=prepared`, 동결 요청·입력 fingerprint를 저장한다. 후보 본문과 기존 participant 주소가 가리키는 표제 등의 실제 원문만 입력 문맥에 포함한다. 새 정답이나 의미 판정을 추가하지 않는다. 이 명시적 입력 계약은 기존 일반 검수 요청을 바꾸지 않는다.
- 준비 중 모델 식별 조회·계수·생성·executor 제출은 없다. GET `/api/v1/knowledge/runs/{id}`에서 범위와 동결 요청을 읽는다. 같은 멱등 키의 다른 요청은 충돌이다.

`POST /api/v1/knowledge/business/runs/{id}/candidate-review-execution`은 별도 실행 요청이다. `expected_input_fingerprint`가 필요하며 준비 API와 달리 모델 작업을 제출한다. 실제 모델 실행은 별도 승인과 호출 계약 확인 후에만 수행한다.

- 큐 등록과 실행 직전에 부모·요구·원문·선택 범위를 다시 확인한다. 실제 정정/보존 문맥을 포함한 `candidate_request/json_request`가 저장 packet과 같은지 대조한다. 실행 시 모델 식별과 정확한 입력 계수·용량도 확인한다.
- 기존 `review_candidates`를 선택 후보에 한 번 호출하고 저장 후 종료한다. 자동 원문 조사·적용성·repair·추출·개념화·전체 R/join·QA·게시·사용으로 이어지지 않는다. 사전 계수와 공통 호출 내부 계수는 각각 있을 수 있으며 생성 상한은 1회, 자동 재시도는 없다.
- 성공적으로 검사했더라도 전체 실행 상태는 `partial`이다. `unknown`은 미확정으로 남고, 실행/응답 오류는 `failed`, 취소는 `cancelled`로 종료한다. 이번 새 unit만 종료하며 과거 unit은 변경하지 않는다. 종료/실패한 같은 준비본은 다시 제출하지 않는다.
- `assessments=[]`와 원래 draft guard를 유지한다. 후보 검수 응답만으로 제품 자격이나 새 사용 snapshot을 만들지 않는다. 실제 source/public_scope·제품 자격·별도 사용 결정은 이 API의 범위 밖이다.
