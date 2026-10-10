# 보존 승계 변경의 실제 국소·종합 검증 — 2026-10-11

채택한 `28f7c8deeef423916ede057ea3faf41de2d68d11`의 보존 승계를 실제 제품 `start→assess` 경로로 검증했다. 보존 재사용과 호출 연결은 확인했지만, finding0과 k1의 핵심 오판은 그대로다. 이번 구성의 의미 검증은 실패이며 snapshot·그래프·같은 질문 QA로 진행하지 않았다. 모델의 satisfied/complete와 서버 satisfied·eligible21을 의미 통과로 집계하지 않는다.

실제 실행 `439a9c618e164141a8390a41db28e8fa`의 부모는 `9da0802dc5794b4b9fd6edb196920dd3`다. 신규 local04 unit은 `70737bbf2cba4a45b725e4f569fe6045`, join unit은 `0a8ef483d30344789c0b754674715264`다. 코드·모델·설정·후보·원문·공개 R05 질문과 `r05-guidance-scope-v1`을 동결했다. 기준은 문서의 담당·제외 업무를 종합 안내하고 복합 처리나 용어 대응의 미확인을 명시하는 것이다. 전체 처리 보장이나 전부 보류를 새 완료 기준으로 삼지 않았다.

모델 호출 전에 9da의 실제 neutral1f 입력을 선택했다. 최신 저장 source와 의미17·finding2·1f 이력은 같지만, 최신판의 completeness=complete·finding 해소·연결 review 이력을 추가 cue로 넣지 않기 위해 9da가 실제 사용한 원래 source 입력(completeness=unknown)을 그대로 썼다. b97의 미채택 “제출해야” 재작성은 사용하지 않았다. 최신 9da의 canonical 보존3은 부모 assessment에서 별도로 승계했다. 결정 시점·두 source의 차이·해시는 freeze와 별도 선택 영수증에 보존했다. 정답·b27에 대한 원하는 finding 판정·완성 수정문을 제품 입력에 추가하지 않았다.

기존 국소 11개는 의미키와 전체 messages/schema/reference_map/설정/요청·실행 한도가 정확히 일치하여 기존 제품 캐시로 재사용했다. local04의 입력 차이는 repair_context 제거 하나이며 실제 모델로 실행했다. 조건부 확대 fallback은 0회였다. 이어 실제 결과로 종합 1회를 실행했다. 보존 targets/context/local_preservation_checks가 빠지고, plate local_judgments의 review_unit_ids와 연결 후보5의 input_fingerprint가 바뀌었다. source/source_inspections·원문·후보·공개 요구는 전송값이 같다. 기존 코드의 조건분기로 “수정 대상마다 preservation_checks 재작성” 지시 1줄이 생략됐고, 새 보존 대상0에 맞춰 schema가 바뀌었다. 수동 프롬프트·한도 조정은 없다. 이 복수 입력 변화가 있으므로 보존 문맥 제거만으로 결과의 인과를 설명하지 않는다.

finding0의 원래 지적은 비번호판 변경 이전등록 구비서류의 부재다. 새 해소도 plate_change_documents/c47/b32 한 구간만 선택하고 “번호판 변경 시 구비서류…c47이 정확히 표현”을 이유로 resolved를 반환했다. b27의 공통 신청서·보험·자동차세와 본인 신분증 원문은 존재하지만 해당 해소 근거로 사용하지 않았다. 서로 다른 서류 범위를 바꿔 해소한 동일 오판이다. finding1은 기관표의 5개 업무 body 구간으로 해소했다. 기존과 같은 방향이며 새 개선으로 세지 않는다.

k1은 명지 본소 b139·금련산 b146의 번호판 교부 당일/2~3일을 복합 이전등록 처리의 직접 지지로 supported 처리하고 원래 연결문장을 유지했다. 교부·변경·재발급·재봉인의 대응이나 복합 처리의 구체 미확인은 남기지 않았다. k2도 기존 supported 문장을 유지했다. 정상 직접 제외 k3/k4/k5는 원문 문장·supported·located를 유지했다. k1/k2의 item_ids는 이번 각각의 질문 항목으로 한정됐지만, 핵심 의미 오판의 해소는 아니다.

c47의 구비항목과 지역 번호에 한정된 반납 후 변경 두 의미는 원문·후보가 그대로이며 새 local도 이를 supported/represented로 확인했다. c47/c116/c117 보존3은 실제 active 위치·지문 검사와 최신 판정 승계를 통과했다. 표현 판정12의 상태·후보·지지·오류 투영, 원문 필드 판정12 전체, dependencies와 eligible21은 부모와 같다. dependencies의 null11은 독립성을 확인한 값이 아니다. source17·claims119·blocks171·개념·공개 항목·finding2를 보존했다. 이전 자동 발견·수정 성과를 이번 재검수의 새 성과로 다시 세지 않는다.

| 실제 신규 호출 | 입력 토큰 | 출력 토큰 | 모델 응답 시간 |
|---|---:|---:|---:|
| local04 | 4,738 | 231 | 42.754879초 |
| join | 16,447 | 2,763 | 248.571836초 |
| 합계 | 21,185 | 2,994 | 291.326715초 |

토큰은 provider_reported이며 재사용11개의 과거 비용은 신규 비용에 더하지 않는다. run.metrics.elapsed_s는 316.522570초, 최종 저장·종료를 포함한 driver 시간은 318.508906초다. 측정 환경·입력 변화가 있어 단일 실행을 속도 개선의 인과 증거로 삼지 않는다. 기존 qwen3.8:27b-q4_K_M·temperature0·think=false·timeout1800초·출력8192·컨텍스트49152를 유지했다. 소유 Qwen을 해제하고 /api/ps 모델0을 확인했다.

핵심 오판이 남으면 QA를 억지로 실행하지 않는 사전 중단 조건을 적용했다. snapshot/그래프/QA·새 source 재판정·편집·추출·개념·judge·프롬프트 재시도는 모두0이다. 모델0 preflight와 전체 테스트를 반복하지 않았다. 독립 버스는 총괄이 확인한 기존 성공 기록을 유지하며 새 버스0, 연구 A 새 실험0이다. 이전 실패와 모델0 결과를 덮어쓰지 않았다.

구조화 결과와 재현 식별자는 [동명 JSON](business_preservation_actual_20261011.json), raw 요청·출력·코드·원본/실행 DB·freeze·해시 영수증은 `/Users/hyeongi/.codex/artifacts/business-preservation-actual-20261011/v1`에 보존한다. 이번 구성은 여기서 중단하고 총괄에 실패 위치와 운영 확인을 전달한다. #616/#617/#620은 실제 전체 필수 결과가 미완료이므로 OPEN을 유지한다. 보고·재현 기록만 커밋/푸시하며 새 이슈·PR·merge·deploy를 만들지 않는다. 현재 사용자 결정이 필요한 사항 없음.
