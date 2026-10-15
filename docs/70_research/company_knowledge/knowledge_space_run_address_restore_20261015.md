# 연속 공백 개수 차이의 원문 주소 복원 — 2026-10-15

진행 중인 원본 복구 run `a84da99f524e4c2c89c53e39d5081303`은 수정하지 않았다.
완료된 첫 역할 11개 응답만 분리하여, 모델 호출 없이 기존 `store_extraction`으로 70개 주장을 재생했다.

## 원인과 변경

`claim_5b4142770dd43795c7f88d2f`의 Tail은 `그 외 기타 분류 안된 화학제품 제조업`이다.
제공된 원문 셀은 `그 외 기타 분류 안된  화학제품 제조업`으로, `안된` 뒤의 공백 개수만 다르다.
원문 block `6148208fe390485fac5d1721d7da9955`, section 74/table 2/row 16/column 1,
source version `86a31d6b511a46f195963ef5ee52cd96`, parse `aa11c25ea5ba4c7c8e48ed186d4db851`의 `[0,22)` 구간이다.

정확 인용 매칭을 우선한다. 정확 매칭이 없을 때만 같은 literal-space 경계를 유지한 고유 구간을 찾고
원문 char span/quote를 저장한다. `matching_method=space_run_length_only`로 방법을 기록한다.
참여자 복원은 해당 인용에만 새 규칙을 적용하고, 실제 선택된 근거의 방법을 표시한다.
기존 exact 인용의 참여자 처리와 원시 후보·Scope.raw·모델 응답은 유지한다.

## 확인된 결과와 한계

관련 경계 검사 47개가 통과했다. 공백 경계/문자 차이, 반복 인용 모호성, view 밖 위치,
상위 인용 구간, exact 우선, 혼합 참조와 공백 없는 정상 참여자를 확인했다.
실제 분리 DB의 baseline `56e46e4d59c648f5b28edcf4eaa5551c`와 replay `cb1003388ecf4e6f82b93d919f93fa86`를 다시 읽어 저장 payload를 대조했다.
주소 오류가 있는 주장은 4개에서 3개로 줄었고, 1개 Tail만 정확 원문 주소로 바뀌었다.
나머지 1,464개 주장, 2,628개 관계, 2,769개 노드는 동일하다. 전체 2,770개 노드/2,629개 관계 수도 동일하다.
누락 관계를 신설한 결과가 아니라 `unresolved_item_address` 끝점을 정확 원문 identity로 연결한 결과다.
진행 DB의 graph는 종료 때 재구성되므로 running graph의 누락을 이 오류의 인과 근거로 사용하지 않는다.

이 결과는 자동 의미 교정·사람 승인·검색/답변 개선 증거가 아니다. 다른 원인의 3개 오류는 그대로 남았다.
원본 복구가 끝나면 새 최종 복사 DB에서 동일 응답과 정확 repair view를 재생해 확인된 주소만 갱신할 수 있다.
과거 claim과 unit 검사 기록은 보존하고 신규 주소 갱신 기록을 구분해야 한다.

재생 자료는 `data/knowledge/evaluations/w1_space_run_replay_20261015_v1/`에 있다.
최초 in-memory receipt와 도구 오류 기록을 보존했고, 실제 저장 증거는 `storage_followup.json`에 구분했다.
존재하지 않는 parses 테이블, 신규 run INSERT 누락, graph의 target/tail 조회 오류는 재생 도구의 준비 오류이며 모델 재시도가 아니다.
과거 W1 조정 1회와 이번 실행 코드 2종을 합쳐 같은 주소 복원 계열을 보수적으로 3/6으로 기록했다.
원본 source-role 용량 조정 횟수에는 더하지 않는다. 새 모델 호출은 0회다.
