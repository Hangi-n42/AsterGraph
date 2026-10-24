# 저장 B의 후 조건 필드 조회

`POST /api/v1/knowledge/business/search`의 `answer_mode=stored_after_conditions`는 기존 B 생산 계약 `source-numbered-steps-conditions-B-v1`의 저장 응답을 읽는다. 새 모델·검색·추출·의미 판단은 실행하지 않는다. 기존 `source_list_comparison`의 A/B 동일 문맥 검사는 그대로 유지한다.

```json
{
  "question": "저장된 후 조건 표시",
  "snapshot_id": "B가 사용한 원래 snapshot ID",
  "retrieval": "explicit_sources",
  "answer_mode": "stored_after_conditions",
  "stored_after_conditions": {"run_id": "저장 B 실행 ID", "unit_id": "저장 B unit ID"}
}
```

질문은 표시 제목이며 조건 선택에 사용하지 않는다. 다른 실행·선택 요구·목록 대조 입력을 혼합할 수 없다. B의 원래 snapshot, 등록 출처·버전·파싱·블록·전체 목록·단계·문자 위치·인용을 검증한다. 원시 공급자 응답·텍스트·parsed, 지시문 해시, 생산 계약 버전, 실행 한도와 정상 종료 기록도 대조한다. A 응답은 요구하지 않는다. 연구 snapshot은 메모리에서 미승인 출처 읽기 범위로만 사용하며 승인 snapshot을 생성하거나 원본을 수정하지 않는다.

저장 그룹의 `kind=action_timing`이고 `condition_quote`가 문자 `후`로 끝나는 기록만 전달 대상으로 고른다. 이는 저장 필드의 표시 범위이며 시간 관계·조건 귀속의 의미 검증이 아니다. 같은 부모 인용 안의 서로 다른 행위는 보존하며 같은 조건·행위 역할의 중복은 미확정으로 남긴다. 미지원·오류 그룹은 `not_consumed_not_absence` 또는 `unresolved`로 보존한다. 빈 결과도 조건 부재를 증명하지 않는다.

기존 응답 계약인 `answer.answer`, `choice=null`, `citations`, `sections`, `limitations`를 사용한다. 본문은 출처 제목·단계를 구분하고 **저장 모델이 반환한 조건/행위, 의미·대상 연결 미확정**을 명시한다. `after_condition_consumer`는 원래 run/unit/step/group, 부모·조건·행위·연결어의 정확 주소, 반환 대상 후보와 목록 이름의 주소를 별도로 보존한다. 대상 연결은 `unverified_stored_model_suggestion`, 의미는 `unverified`, 사람 승인은 `false`다. 대상 문구가 목록 이름과 다르거나 행위 밖에 있어도 저장 모델의 미확정 제안으로만 표시한다. 이를 동일성·행위 대상·부분 관계로 승인하지 않는다. 독립 행위, 생략된 주어, C2 결과를 새로 생성하거나 연결하지 않는다.

출처 제한과 snapshot 변경 무효화가 있으면 본문 없이 `needs_review`를 반환한다. 저장 직전에도 제한·요구 revision·취소·서비스 종료·새 무효화와 원래 snapshot/B 기록 변경을 검사한다. 성공은 `partial` 응답 상태이며 의미적 정답이나 전체 원문 행위의 포괄성을 뜻하지 않는다.

저장 결과는 `GET /api/v1/knowledge/runs/{run_id}`에서 다시 읽는다. 기존 workbench 답변 API는 이 미승인 범위에 한해 `kind=stored_conditions&scope_id={snapshot_id}&answer_id={run_id}`를 받는다. 저장 당시 본문·인용 맵을 그대로 사용하며 빈 그래프와 현재 출처 제한·무효화 상태를 함께 반환한다. 새 화면 선택 메뉴나 기본 답변 모드로 승격하지 않는다.
