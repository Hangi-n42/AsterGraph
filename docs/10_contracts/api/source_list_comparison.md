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

## 선택적 저장 시점 소비

`list_comparison.timing_run_id`와 `timing_unit_id`를 함께 지정하면 기존 A 조건 기록을 유지하면서 저장된 시점 기록만 별도로 읽는다. 두 필드가 없으면 기존 답변·섹션·인용·제한 문구가 유지된다. B의 미반환 선택 연결을 생성하거나 A를 B로 덮어쓰지 않는다. 새 모델·검색·계수기·producer 의존성은 없다.

지원 생산 계약은 `source-numbered-steps-conditions-B-v1`이다. `business_query`의 동일 snapshot 및 종료 상태, 성공한 `source_step_conditions` unit, 고정된 지시문 계약, 요청/실행 한도와 recipe 일치, 정상 종료, 원시 공급자 텍스트/저장 text/parsed 일치를 검사한다. 표시용 질문 문자열은 비교·분기하지 않는다. 실제 A/B 입력은 B의 기계적 `method_steps`/`method_prefixes`를 제외하면 같은 원문 버전·목록 필드·항목값·문자 위치여야 한다. 항목 ID 문자열만 같은 것으로 충분하지 않다. 단계 번호·부모·주소·전수 순서·prefix를 포함한 전체 문자 복원과 출력 단계 계약도 확인한다.

새 소비 계약은 `stored-leading-step-timing-v1`이다. 제한된 표면 구문만 소비한다.

- 실제 반환 `kind=action_timing`만 읽는다. 원문 번호 단계의 선두에서 번호+주격조사로 시작하고 `면`으로 끝나는 조건, 목록과 문자 그대로 같은 대상 이름 및 목적격조사, 한 단어의 행위 술어가 직접 이어져야 한다.
- 특정 번호·질문·재료명·상태/행위 문구를 분기하지 않는다. 여러 절·동의어·대체 관계·새 조건은 추론하지 않는다. 뒤집힌 순서, 중복 대상/인용, 서로 다른 출처, 없는/모호한 인용, 단계 전체로의 확대, 부정·인용·전언의 후행 범위는 미확정으로 남긴다.
- 반환 quote·조건·행위·대상·원래 번호 참조를 각각 유일한 정확 주소로 보존한다. 번호에 인접한 원래 주격조사를 포함한 문맥과 같은 조리방법의 앞 번호 본문도 제시한다. 이는 원문의 숫자/문맥 연결이며 참조의 상태·인과 의미를 새로 해소한 결과가 아니다.
- 나머지 `use_condition`, `unqualified_action`, 불완전 그룹은 `not_consumed_not_absence`로 기록한다. 전체 조건 없음·무조건 사용·의미 승인으로 바꾸지 않는다. A의 기존 OR는 A에서만 소비한다.

타이밍 옵션이 유효하지 않으면 타이밍만 `unresolved`로 남기고 정상 A의 목록·OR·상품 사실을 유지한다. 개별 시점의 모호함은 해당 기록만 미확정으로 남긴다. 입력 타입도 경계에서 검사하므로 손상된 response/raw/message가 정상 A 결과를 없애지 않는다. 시점을 소비해도 `semantic_status=unverified`, `human_approval=false`, 전체 `answer_status=partial`을 유지한다.

새 `answer.sections.kind=stored_timing`은 출처 제목, 반환된 실제 연속 구절, 원문 참조와 앞 번호 문맥을 보여준다. 해당 섹션에 원래 run/unit·step/group provenance와 실제 인용을 저장한다. 기존 조건·상품 섹션의 내용·인용은 바꾸지 않는다. `timing_consumer`는 별도 계약·오류·미소비 기록을 보존하며 `execution_boundary`에 기존 `condition_support`와 새 `timing_support`/`timing_status`를 함께 기록한다. 옵션이 없는 실행에는 새 경계 필드를 추가하지 않는다.

고정 자료의 무모델 실제 HTTP 전후 비교에서 목록12/11·공통5·기존 OR·두 상품 제조원/전체 보관조건을 동일하게 보존하고, 저장된 시점 하나를 추가했다. POST → 저장 → GET run → workbench의 답변/인용/상태와 모든 source/version/parse/block/span을 대조했다. 원래 A의 invalid와 B의 raw/평가기준은 수정하지 않았다. 이는 저장 기록의 제한 소비·보존 검사이며 새 모델 성능·일반 의미 해석·자율검색 성과가 아니다. 후속 시점, 일반 기름의 특정 종류 귀속, 복합 행위의 전체 대상 등 기존 미완료도 해결한 것으로 계산하지 않는다.

## 통합 브랜치의 저장 답변 화면

`workbench/answers`는 저장된 `condition_consumer`와 `timing_consumer`가 있는 경우 원형을 함께 반환한다. 저장 답변 화면은 `explicit_sources`를 명시적 원문 목록 대조·저장 결과로 표시하며, 이 방식의 `provided_ids`를 새 모델 입력이나 그래프 검색 결과로 설명하지 않는다. 기존 검색 방식과 알 수 없는 방식의 표시 규칙은 유지한다.

조건·시점 펼침에는 원래 생산 실행/단계, 기록된 생산 상태와 소비 상태, 의미 미검증·사람 승인 여부, 항목별 상태 및 미소비 수를 구분한다. 생산 상태가 소비 기록에 없으면 미기록으로 표시한다. `not_stated`는 무조건 사용이 아니고 `not_consumed`는 조건 부재가 아니다. 원문 근거는 기존 `source_reference_map`의 버전·처리 기록·블록·문자 범위를 사용하며 주소 일치를 의미 승인으로 바꾸지 않는다.

이 연결은 원래 snapshot의 저장 결과 재사용이다. 사람의 결정으로 생성되는 새 snapshot은 기존 same-snapshot 검사를 ID 치환으로 우회해 사용할 수 없다. 새 사용 범위의 실제 원문·목록·조건·상품 사실 결속은 별도로 확인해야 한다.
