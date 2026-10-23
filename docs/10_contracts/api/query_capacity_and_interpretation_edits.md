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
