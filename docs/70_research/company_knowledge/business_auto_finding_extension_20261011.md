# 어린이박물관 자동 finding의 실제 편집과 주소 복원

2026-10-11. 제품 `feature/business-requirement-answer-flow`, 시작 HEAD `b1c4e8990b3e2781a3c988a39c0857bda65a0cc3`. 기존 #616/#617/#620 후속이며 완료·병합·배포를 뜻하지 않는다.

## 결과

연구의 실제 자동 SC03·SC04 판단을 원 라벨·이유·오류 위치 그대로 기존 교정에 전달했다. 두 후보는 연구용 AI 작성 변형이며 제품이 자율 추출한 오류 후보가 아니다. 반복 노출된 개발 사례다. 각 generic 편집을 실제 한 번씩 수행했고 재시도는 0이다. SC03은 현장 답사 희망자로 주체를 한정했고, SC04는 취소 의무를 취소 허용으로 바꿨다. 두 첫 제안은 Scope 주소 검증에 실패해 원 저장 지식을 바꾸지 못했다.

SC03에 한정한 문자 주소 복원을 추가하고, 원 응답을 새 DB/run에서 모델 호출 없이 재처리했다. Event·Entity·모델 Scope 의미 필드를 바꾸지 않고 실제 선택된 동일 문장의 모든 위치를 보존하여 `applied_awaiting_recheck`로 저장했다. 이후 직접 후보 검수와 AI 원문 대조에서 수정문의 정확성을 확인했지만, 모델의 수정 전후 보존 판단은 실패했다. 전체 요구 재검수·승인·운영 검색·실제 QA 완료는 없다. SC04는 문맥 유래 Entity와 Scope 의미 기록 모순이 남아 재처리하지 않았다. 유용한 표현 제안, 주소 저장, 후보 정확성, 정상 보존, 전체 요구 충족을 하나의 성공으로 집계하지 않는다.

## 고정 입력과 라벨 경계

국립중앙박물관 어린이박물관 예약 안내의 2026-10-10 21:07:12 UTC 저장 원문을 사용했다. 전체 8블록·2,745문자와 관찰된 부모 문맥 6개를 보존했다. 현재 웹 안내 전체를 새로 확인한 결과가 아니다. HTML SHA256은 `1be3dac9ef2cdfe2e465919eea1cb20080d327ef8ea94b7af60b0d5d8f665a04`, 텍스트 SHA256은 `5677311e4b2d4d034b90b04ed3f293c1db9b80185e761ac3dbfaf4f709df9731`이다.

자동 SC03은 모든 관람객에게 사전 승인을 확대했고 SC04는 예약 취소를 의무화했다. 연구 기대 U에 대해 자동 판단은 두 건 모두 C였다. 원 numeric label 3/decoded C와 원 이유를 assessment·targets에 그대로 보존했고 서버가 U로 고치지 않았다. SC03 이유의 ‘현장 답사 희망자에 대해서만’과 SC04 이유의 ‘원문과 양립할 수 없는 반대 내용’은 원 모델 주장이다. 이를 검증된 원문 사실로 승격하지 않는다.

공개 요구는 `어린이박물관의 사전 승인·예약 취소·비예약자 동반 입장과 증빙서류 안내는 무엇인가?`, revision 1이다. 원문 대상·조건·허용·의무와 구체 미확인을 구분하는 기준을 고정했다. 정답 Entity/Event·기대 교정문·gold·원문 정답 해석을 편집 입력에 제공하지 않았다. source meanings는 빈 목록이다. SC01 다자녀 동반 입장과 SC02 증빙서류 일부 정상 목록은 저장된 실제 S 응답을 재사용해 no-op를 확인했고 새 편집 호출은 0이다.

실제 편집에는 기존 관련 블록 선택 결과만 들어갔다. SC03은 b4/b7/b8, SC04는 b1/b2/b3 각 3블록이다. 전체 8블록·부모 문맥은 원형과 B2 전달 파일에 남았다. `qwen3.8:27b-q4_K_M`, 동일 digest/설정, context 49,152, 최대 출력 8,192, think=false, temperature=0을 유지했다.

## 전달 결함과 최소 변경

기존 Event 전용 편집기는 원 Entity의 실제 문자 발생을 먼저 열거한다. `모든 관람객`과 `개인 예약자`가 원문에 없으면 편집 호출 전에 반환했는데, 이미 그 task가 generic 경로에서 빠져 실제 편집 요청이 사라졌다. 지원 가능한 원 Entity 주소가 없는 task를 기존 generic 편집에 남기도록 사전 분기를 6줄로 추가했다. 지원 가능한 후보는 기존 native 경로를 그대로 사용하고, 실제 native 모델 실패 뒤의 추가 fallback/재시도는 만들지 않았다. 원 라벨과 이유를 전달하는 계약도 유지했다.

준비 v1/v2 및 비모델 실패들을 보존했다. v2에서는 연구 문서 전체 오프셋을 제품의 DOM 블록별 오프셋에 그대로 사용해 SC03 관련 원문이 모델 요청에서 빠졌다. v3은 원 텍스트·라벨·이유를 유지하며 오프셋을 기계적으로 블록 기준으로 옮겼고, 원 주소와 변환 주소를 case별 map에 기록했다. 이 준비 실패를 제품 의미 판단 실패로 세지 않았다.

## 첫 실제 호출과 저장 실패

| 사례 | 실제 run / unit | 모델 제안 | 첫 저장 결과 |
|---|---|---|---|
| SC03 | `7f01d8c480aa4d509f041ecf0e35a327` / `66e8bb8d4ebc4dd68bbaf7b1c5b5c06c` | Event는 원문의 현장 답사 승인 문장, Entity는 어린이박물관·현장 답사를 희망하시는 분들 | b4와 b7의 동일 문장에 Entity 발생이 각각 있어 전체 발생 수 2를 모호함으로 거절. Event selector 누락도 기록 |
| SC04 | `5cb4659544ad4ecd96a7482b832fc451` / `8d720137da17498eb2affbc82f8c1dcb` | 취소 의무를 허용으로 수정, Entity는 어린이박물관·개인 예약자 유지 | 선택한 취소 문장에 두 Entity 문자열이 없어 거절 |

SC03 모델 75.912093초, SC04 55.911945초, 합 131.824038초다. 호출 driver는 131.885377초이며 준비·대기·검토 전체 시간은 아니다. 2026-10-11 04:39:18 UTC 소유 모델을 unload했고 `/api/ps`의 models=[]를 확인했다.

SC04 Scope는 modality=`permission`인데 relation_kind=`obligation`이다. 주소 실패와 별개의 의미 기록 모순이다. relation_kind와 modality는 Scope의 canonical meaning ID·저장 interpretation 및 후속 compact_interpretation/local_interpretations 모델 문맥에 유지된다. 현재 graph 경로에는 relation_kind만으로 승인하거나 edge를 바꾸는 분기가 없다. 주소를 보완해도 이 모순은 없어지지 않으므로 의미 승인으로 계산할 수 없다. B2는 whole raw Entity/Event를 비교하며 이 Scope를 검증한 결과가 아니다.

## SC03의 제한된 기술 복원

모델이 명시적으로 선택한 서로 다른 위치의 원문 인용들이 같은 source version에서 **원 raw Event 전체와 문자상 동일**하고, 각 Entity가 그 문장 안에 한 번씩 존재할 때만 중복 위치를 모두 보존한다. 한 위치를 임의로 고르지 않는다. 모든 Entity selector가 해당 문장으로 연결돼 확정되었을 때, 누락된 Event endpoint도 그 문장의 정확 위치로만 복원한다. 다른 문장·조건·같은 이름만 있는 여러 참조·한 인용 내부의 반복·다른 source version은 기존 unresolved를 유지한다.

원 모델 Scope는 interpretation.raw에 보존한다. Entity의 동일 문장 중복 위치와 누락 Event의 literal binding은 `address_restorations` 3개로 분리된다. 모델의 원래 오류 receipt/response/DB를 덮어쓰지 않는다. Scope의 분류·주체·행위·조건·허용·의무를 서버가 새로 작성하거나 수정하지 않는다.

재처리 run은 `0fce1f98d3414cdf81aa683525415bd5`다. 원 Event/Entity/Scope, 8원문 블록·질문 및 다른 3후보가 동일하고 신규 모델 호출은 0이다. 저장 후보는 unreviewed/unknown이며 approval=none이다. participation edge 2개는 unreviewed로 생성됐다. 각 참여자와 Event에 b4/b7의 두 원문 주소가 모두 남는다. 같은 이름이라도 다른 부모 블록의 주소 집합이나 다른 source version을 가진 후보는 그래프 노드가 합쳐지지 않음을 검사했다. 이는 지식 의미·검색 품질·답변 성공의 증거가 아니다.

## 재현 기록과 검사

로컬 `data/knowledge/evaluations/business_auto_finding_extension_20261011/`에 v1/v2/v3 준비·주소 변환·정상 no-op·동결 요청·원 실패·actual DB/원 응답·모델 해제·clean B2 제안후보와 실제 저장 전후를 각각 보존했다. `sc03_address_replay/`는 원 응답 재처리의 별도 DB/run·restoration·원 오류·driver·hash 기록이다. 준비 실패와 첫 실제 실패를 삭제하지 않았다. B2 제안 파일에는 whole Entity/Event·전체 원문·부모·runtime genealogy만 제공하고 자동 이유·라벨·gold·저장 오류 설명을 넣지 않았다.

전용 주소/Scope/Event/결합 검사 53건이 통과했다. 그 전 실제 dispatch 결함은 변경 전 실패를 재현하고 Event/semantic_edit 22건이 통과했다. C 관련 5모듈 141건 및 추가 정상 관계 대조 19건은 별도 검사 시점의 수치이며 서로 더해 고유 테스트 수나 자동 품질 분모로 사용하지 않는다.

독립 보존본 `/Users/hyeongi/.codex/artifacts/business-auto-finding-extension-20261011/first-edits-and-sc03-address-replay-v1`의 107파일 3,999,575bytes를 모두 SHA256 대조했다.

## 같은 공개 요구의 원문 조사와 후속 경계

저장된 SC03과 다른 3후보를 그대로 둔 새 사본 run `28e3bcb1631d4958a5743eafe8c70900`에서 기존 v8 원문 조사 4묶음을 실제 한 번씩 실행했다. 공개 질문·criterion·revision 1과 8원문 블록은 같다. 실제 원문 의미는 38개, 필수 표시는 32개, findings는 9개이며 네 국소 조사 모두 complete와 오류 없음이다. 전체 source completeness는 unknown이다. 신규 raw 추출·표현 검수·graph/search/QA는 이 단계에서 0이다.

모델 시간 합계는 631.156127초, driver는 633.565028초다. `museum_source_actual/`에 원 응답·네 unit·source·run·DB·호출량·해제를 보존했다. 소유 모델 해제 뒤 models=[]를 확인했다. C 실험 회수 후에도 이 네 source 요청의 messages/schema/주소/한도는 실행 전 동결본과 정확히 같다.

새 출력은 마스크 안내를 질문의 direct_answer로 필수화하고 requested_fact를 일반 예약·입장 안내로 확대했다. 동일 자체 해설·수업 금지는 batch2에서는 background/false, batch4에서는 필수/true다. b8에는 2026 단체 달력, 2020 선택 날짜와 사용자 미방문 팝업의 2022~2023 예약 제한 기간이 함께 있다. 이 팝업 기간을 모든 이용자의 현재 일반 제한으로 적용할 근거는 확인되지 않는다. 원문 존재와 질문 필수성·현재 적용성을 분리한 대조는 `museum_source_scope_review.json`에 남겼다. source의 required/status/날짜/이유를 서버가 수정하지 않았다.

기존 v9/v10 선택 및 v13 사실·적용성 분리 실험은 이전 실제 의미 gate에 미달해 기본 미채택이었다. 이를 새 해결책으로 재실행하지 않았다. 현행 v8의 32 필수 의미는 28묶음이며 이 모두를 후속 호출하지 않았다. `assess(previous_run=...)`의 제한 재검수는 동일 입력의 이전 실제 R scope/fingerprint가 필요하다. 이번 박물관에는 그 이전 R가 없다. 이전 판정 조작·질문 축소·서버 gold 필터로 검수 범위를 줄이지 않는다.

기존 `candidate_request`와 `review_candidates`로 정상 SC01/SC02와 저장 SC03의 자체 원문 정확성 및 실제 before/after 정상 보존을 한 호출에 확인하는 입력을 준비했다. 자동 관련 선택은 b4/b7이고, 새 source 의미·기대 label·교정 정답을 넣지 않았다. 출력 예산을 포함한 추정은 18,812이며 context 49,152/출력 8,192에 들어간다. 이 direct receipt는 질문 필요성을 판단하지 않고 v8 전체 요구 검수를 대신하지 않으므로 전체 질문 적격성·운영 graph/search/QA 완료로 승격할 수 없다. SC04는 원형과 unresolved를 유지한다.

source4와 준비 자료의 독립 보존본은 `/Users/hyeongi/.codex/artifacts/business-auto-finding-extension-20261011/source4-and-candidate-preparation-v1`이다. 20파일 2,657,586bytes를 모두 SHA256 대조했다. C 회수 뒤 Scope/주소/Event/semantic edit/결합 관련 6모듈 76개 검사가 24.38초에 통과했다. 이는 이전 검사들과 합산한 고유 누적 수가 아니라 해당 시점 실행의 고유 수다.

## 실제 직접 후보 검수 1회와 보존 판단 실패

연구 자원 반환 뒤 동결한 입력을 한 번 실행했다. run `e26e27b343a7426f8eccea4fb0da8ee2`, receipt `70f73315db5146a8976b9896bcc1d362`, unit `7f5b96ed34c5448eaa938d0a78eed254`다. 실제 입력 4,534/출력 274토큰, 모델 43.272595초, driver 43.522939초다. 원 계약 오류는 없고 세 후보의 exact direct receipt가 현행 요청 검사를 통과했다. 원문·네 후보·질문·실제 교정 이력·graph는 모두 같다. 2026-10-11 05:31:30 UTC 소유 모델을 해제했고 models=[]를 확인했다. 재시도·추가 편집·전체 R·QA는 0이다.

모델은 SC01/SC02/수정 SC03을 모두 supported로 반환했다. supported 이유 세 개는 빈 문자열이며 현재 계약은 이를 허용한다. 근거 ID·주소 일치와 의미 검증을 구분한다. 실제 원문·필드를 대조하면 SC01의 4자녀 이상·현장 증빙·사전 예약 가족 5명·동반 입장 조건이 유지된다. SC02의 가족관계증명서 포함은 비배타적 일부 목록이며, 다른 인정 서류가 있다는 이유로 오류 처리하는 회귀는 없었다. SC03 raw Event는 선택한 원문 문장과 같다. Scope도 현장 답사 희망자·방문 전·유선 및 서면·사전 승인을 유지하고 다른 관람객의 의무 부재나 금지를 추가하지 않았다. 이 한 개발 사례의 현재 표현 정확성을 확인한 AI 대조이며 공식·사람·일반화 품질 결과가 아니다.

그러나 `preservation_checks.status=preserved`의 **수정 전후 비교는 부정확**하다. before는 Entity가 모든 관람객이고 conditions/references는 비어 있으며 interpretation도 없다. `before_normal_meanings`에 쓴 현장 답사 희망자와 현장 답사 조건은 잘못된 일반 범위를 좁힌 정정 내용이다. 넓은 대상 집합에 하위 대상이 포함되므로 문자에 없다는 이유만으로 두 항목을 각각 독립 의미 오답으로 세지 않는다. 누리집 참조는 before에 전혀 없던 신규 정보다. 정정·신규 참조와 기존 정상 내용을 구분하지 않고 모두 변경 없이 보존된 것처럼 설명한 자동 보존 receipt는 기준에 미달한다. 이 한 receipt의 실패를 세 독립 오류로 합산하지 않는다. 원 preserved 응답과 다섯 번 중복한 after ID를 수정하지 않았다. 주소가 실제 현재 후보를 가리키므로 기존 `preservation_valid`의 기술 위치 검사는 통과하지만, 의미상 정확한 보존 비교 gate는 실패다.

실제 before에서 원문이 지지하는 어린이박물관·방문 전·유선 및 서면·사전 승인 핵심은 after에 남아 있다. 유용한 교정과 해당 내용 유지의 AI 원문 대조는 인정하되, 모델 preserved라는 이유로 정상 보존 검증을 완료하지 않는다. 실제 `eligibility`는 eligible=[]이고 SC03에 `normal_meaning_preservation_unconfirmed`가 남는다. direct receipt를 요구 representation에 이식하거나 원질문을 줄여 승인하지 않았다.

최종 직접 검수 원형·DB·동결 입력/코드·실행 전 평가 기준·기술 준비 실패·원문 평가·해제 기록은 `/Users/hyeongi/.codex/artifacts/business-auto-finding-extension-20261011/direct-candidate-review-v1`에 독립 보존했다. 24파일 2,126,921bytes를 모두 SHA256 대조했다. 보존 비교 오류를 독립 세 오답으로 세지 않는 범위 설명은 `direct-candidate-review-qualification-v1`에 추가 보존했고 최초 gate와 원 응답은 덮어쓰지 않았다. 구조화 보고에 두 manifest를 연결했다. 전체 A 확장의 새 native 호출은 편집 2회·source 4회·direct 후보 검수 1회, 합 7회이며 B2 연구나 C join 호출은 이 수에 넣지 않는다.

같은 공개 요구와 운영 graph/search/QA는 미완료다. 원 SC03/SC04 U/C 오판, SC04 저장 실패, source의 질문 밖 필수 전파, 모델 보존 비교 실패를 모두 유지한다. 이번 A 코드 경계는 교정 작업 전달과 문자 주소 복원이며, 새 source 선택이나 보존 judge를 채택한 변경이 아니다. 추가 반복은 하지 않았다. 현재 사용자 결정이 필요한 사항 없음.
