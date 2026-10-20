# 명시적 원문 목록 대조 API v1

## 목적과 범위

기존 `POST /api/v1/knowledge/business/search`에 `answer_mode=source_list_comparison`을 추가한다. 호출자가 지정한 두 목록 필드를 코드로 전수 분할·동일명 대조하고, 같은 snapshot에 저장된 모델 조건 기록과 지정 상품 사실을 연결한다. 질문은 저장·표시용 제목이며 목록·상품·조건 선택에 사용하지 않는다. 기본 synthesis 및 기존 검색 경로의 동작을 바꾸지 않는다.

이 경로는 새 모델·선택·PPR·임베딩·추출·자유 QA를 실행하지 않는다. 새로운 `business_query` 실행만 저장하며 기존 조건 실행, 원문, snapshot, 승인·검토 기록을 수정하지 않는다. 자동 원문 선택, 일반 조건 해석, 승인 지식 생성은 지원하지 않는다.

## 요청

`BusinessQuery`의 `snapshot_id`, `question`, `answer_mode=source_list_comparison`, `retrieval=explicit_sources`, `list_comparison`을 지정한다. `source_run_id`, 요구 강제 선택, `answer_items`, 선택지, 원문 토큰 상한은 이 모드에서 허용하지 않는다.

`list_comparison`은 다음 명시적 입력을 받는다.

| 필드 | 의미 |
| --- | --- |
| `contract` | `quantity-line-fields-v1` |
| `fields` | 서로 다른 두 원문 버전의 필드 2개. 각 필드는 `field_label`, `source_version_id`, `parse_run_id`, `block_id`, `start_char`, `end_char`, `quote` 필수 |
| `condition_run_id`, `condition_unit_id` | 같은 snapshot의 종료된 실행과 성공한 `source_list_conditions` unit |
| `products` | 선택 사항. 각 상품의 `type_claim_id`, `manufacturer_claim_id`, `storage_claim_id` |

필드는 등록된 한 줄 `label: value` 블록의 값 전체여야 한다. snapshot에서 제외된 블록, 등록 parse와 불일치하는 주소, 부분 필드, 잘못된 문자 위치는 거부한다. 기존 사실의 위치 없는 인용도 부모 원문에서 유일한 경우에만 정확 위치로 결속한다. 공용 `exact_evidence`의 첫 위치 선택을 이 경로에서 사용하지 않는다.

목록 파서는 균형 괄호 바깥 쉼표, 선택적 `재료소개 재료량(...)` 머리글과 명시적 수량 접미사만 지원한다. 정수·소수·분수 및 고정 단위 `kg, mg, g, mL, ml, L, l, 개, 모, 컵, 큰술, 작은술, 뿌리, 장, 인분`, `약간`을 사용한다. 괄호·숫자·중복 이름·수량·원문 순서·구분자를 보존한다. 경계가 모호하면 답변을 만들지 않는다. 동일명은 Unicode 문자열 일치이며 동의어·필수성·의무·상품 지정을 추론하지 않는다.

## 저장 조건 기록 소비

실제 저장된 `unit.response.text`와 `parsed`가 일치해야 한다. 실제 제공 `messages`와 `reference_map`을 역결속하여 원문·목록 항목의 모든 위치와 값을 다시 확인한다. 별도 artifact의 조립 답변·정답 목록·진단 결과는 제품 코드의 입력이 아니다.

새 소비 계약은 `stored-list-condition-addresses-v1`이다. 원래 `condition_validation`은 그대로 기록하고 수정하지 않는다. 반환 `quote`를 넓히거나 원래 `related_item_refs`에 자기 항목을 강제로 넣지 않는다. 주 항목과 관련 항목은 별도 역할로 기록한다.

긍정 연결 범위는 다음을 모두 충족하는 **제한된 한국어 조리 구문**이다.

- 반환된 조건·행위·연결어·quote가 같은 실제 제공 부모에서 각각 유일한 정확 조각이다.
- 같은 원문 버전의 이름 두 개가 `이나/나/또는/혹은`으로 연결된다.
- `면`으로 끝나는 조건 뒤 공백 또는 쉼표만 두고 두 이름의 선택 행위가 이어진다.
- 행위 전체가 `이름 + 연결어 + 이름 + 으로/로 + 간을 한다/맞춘다`에 정확히 맞는다.
- 전체 문장의 선행 주어·후행 문구·부정·제외를 잘라 버리지 않는다. 여러 문장, 다른 주어, 부정, 반복 조각, 비인접 행위, 다른 출처, 지원 밖 구문은 `unresolved`로 남긴다.

긍정 상태 `source_linked_stored_model_record`는 **정확한 원문 연결을 확인한 저장 모델 기록**이다. 전체 의미 검증이나 사람 승인이 아니다. `not_stated`는 `stored_not_stated_not_unconditional`로 보존한다. 조건 없음·무조건 사용으로 승격하지 않는다. 저장 모델이 놓친 다른 행위 시점·조건을 코드가 보충하지 않는다.

## 상품 사실과 인용

상품 참조는 현재 snapshot의 서로 다른 사실 3개여야 한다. 동일 등록 원문 버전의 제품명·식품 유형·제조원 역할/업체 행 그룹·보관 취급 값 전체를 확인한다. 식품 유형의 문자열이 계산된 공통 이름에 있어야 한다. 상품명·질문·특정 검증 사례명으로 분기하지 않는다. 제조원과 업체명의 행 그룹이 다르거나 보관 문구가 부분 인용이면 거부한다. 보관 조건은 저장 해석을 재서술하지 않고 원문 값 전체를 표시한다.

`source_reference_map`에는 목록 필드·entry/name/quantity 및 조건·상품의 전체 보존 주소를 둔다. `answer.sections`의 각 본문 단위에는 실제 사용 `citations`, 적용 `source_version_id` 및 항목/사실 참조를 둔다. `answer.citations`는 섹션 인용의 합집합이다. 미서술 수량·전체 entry 주소를 최종 인용 사용으로 집계하지 않는다. 조건 본문은 실제 등록 출처 제목과 목록 번호를 표시한다.

## 저장·재조회와 상태

기존 검색 진입의 사용 제한, snapshot 무효화, 요구 revision 검사를 통과해야 한다. 저장 직전에도 사용 제한·요구 revision·새 무효화·취소·서비스 종료를 재검사한다. 실패 실행은 종료 상태로 저장하며 실행 중인 행을 남기지 않는다.

저장 절차 완료 시 `run.status=succeeded`, `answer_status=partial`이다. 부분 상태는 조건·예외 전체의 의미 완전성을 검증하지 않았다는 뜻이다. `units=[]`, `metrics.llm_calls=0`, `execution_boundary.semantic_approval=false`다. 실행이 성공했다는 상태를 의미 정확성 또는 요구 충족 승인으로 사용하지 않는다.

기존 `GET /runs/{run_id}`, `GET /workbench/answers?kind=source_graph&scope_id=...&answer_id=...`를 사용한다. workbench는 당시 저장된 `source_reference_map`으로 근거를 읽는다. 원문은 기존 source/version blocks 및 raw API에서 확인한다. 별도 DB schema나 공개 endpoint를 추가하지 않는다. UI 입력 기능과 자율 검색은 이번 범위에 포함하지 않는다.

## 2026-10-20 검증 범위

기준 main은 `55f0bf77f89e32992ac3f3c1afcefe4d70a05c7c`이다. 기존 서버·원본 DB와 분리된 작업 위치와 복사 DB에서 기존 knowledge router를 실제 HTTP로 호출했다. 새 모델·검색·index 생성·외부 socket 연결을 실패·기록하도록 차단했다.

고정 원문의 두 필드는 12/11개 항목, 동일명은 두부·다진 마늘·고춧가루·간장·소금 5개였다. 저장 조건 기록 중 2개 행은 같은 조건/행위/연결어 3개 고유 주소를 반복 참조한다. 독립 확인 2건으로 세지 않는다. 나머지 21개 행은 조건 미확인으로 유지했다. 상품 2개의 제조원·보관 문구를 보존했다. 저장 모델이 놓친 `끓으면` 행위 시점은 보완하지 않았다.

POST → 저장 → GET run → workbench에서 답변·전체 map 85개·실제 인용 37개가 일치하고, 등록 blocks/raw에서 85개 주소를 확인했다. 이는 이 고정 입력에서의 API 연결·보존·주소 검증 근거이며 다른 원문 일반화·전체 조건 이해·기본 QA 개선·사람 승인의 증거가 아니다.

신규 파서/소비 테스트 47개가 통과했다. 이를 포함한 관련 경로 검사 158개도 통과했다. 최초 확장 관련 검사는 178개 통과·기존 business 검사 7개 실패였으며, 동일 기준 main에서 같은 7개와 전체 오류를 재현했다. 기대값이나 기존 실패를 수정하지 않았다. 사용자용 문구 수정 후 신규 47개를 재검사했다.

실행 증거와 전체 보고는 로컬 artifact `M02_source_list_service_v1_20261020`에 보존한다. 원래 raw/invalid, semantic 6/6 closed, no_reset 및 누적 호출 lineage를 유지한다. 주 범위는 [#668](https://github.com/Hangi-n42/AsterGraph/issues/668), 답변 인계 관련 범위는 [#620](https://github.com/Hangi-n42/AsterGraph/issues/620)이며 이 문서는 이슈 완료·PR·배포를 선언하지 않는다.
