# B1 새 원문 확인 준비 · 2026-10-11

**상태: 준비 완료, 새 native 모델 호출·적재 0회.** 제품 C 자원 반환 이후 별도 실행 배정과 token/runtime preflight가 필요하다. B1 최초 gate=false와 제품 미채택을 유지하며 #655는 열어 둔다. 새 A 비교 완료 0, 완료 누적 6이다.

## 입력과 평가 버전

- 입력: `NIE candidates v2 / union-string-path diff v2 / technical transport v1`.
- 평가: `nie-v2-same-technical-parser-baseline-diff-v1`. baseline/diff에 동일한 `technical_view`를 적용하며 최초 legacy 계약 결과도 별도로 기록한다.
- 국립생태원 [이용안내](https://www.nie.re.kr/nie/main/contents.do?menuNo=200212)의 `div.sub-useGuide` 전체 정규화 텍스트 5,033자, 40블록, 8부모와 표 병합 셀 9개를 모두 전달한다. 전체 HTML과 블록 DOM은 보존한다. 이미지 픽셀·외부 링크의 전문은 미제공이며 채택 후보는 이에 의존하지 않는다. 표 병합 정보는 별도 구조 배열로 전달한다.
- HTML SHA: `7edeb555a1f8009cee22ba2830bbc30b9c7bfc7b51a17e4d9edcfb6b8bd050b8`. 정규화 원문 SHA: `5def13c233ed729abee5960d92a66fbbacb1e94dee85bf4fc4cf7369b895cf10`.
- 검색한 기존 저장 경로에서는 기관/URL/고유 문구 미발견이다. 삭제 대화·모든 저장소·사전학습 비노출 증명은 아니다. 후보는 실제 저장 업무 오류가 아닌 평가용 작성 후보다.

## 모델 출력 전에 고정한 후보

작성과 블라인드 검토를 독립 동결한 v2 라벨 8/8이 일치한다. 포함 8·미확정 0, S4/U2/C2다. C01/C08은 같은 반입금지 규칙의 부분 정상과 상세 정상이다. v1의 C08에는 이 대조가 없었으므로 모델 호출 전에 C08만 변경했다. 원본 v1·gold·blind와 개정 이력을 모두 보존한다. 원문 조건을 삭제해 정상 정답을 만든 것이 아니다.

| 후보 | 기대 | 실제 Event |
|---|---|---|
| NIE-C01 | S | 국립생태원은 주류 반입을 금지한다. |
| NIE-C02 | S | 국립생태원 관람객은 하다람쉼터에서 도시락을 먹을 수 있다. |
| NIE-C03 | U | 국립생태원 관람객은 하다람쉼터에서 도시락을 먹어야 한다. |
| NIE-C04 | C | 국립생태원 관람객은 음식물 섭취 장소로 지정되지 않은 곳에서도 도시락을 먹을 수 있다. |
| NIE-C05 | S | 국립생태원은 생후 36개월(12kg) 이하용 유모차를 에코리움 안내데스크에서 무료로 대여하며, 이 유모차는 에코리움 실내에서만 대여·이용할 수 있다. |
| NIE-C06 | C | 국립생태원은 생후 36개월(12kg) 이하용 유모차를 에코리움 안내데스크에서 무료로 대여하며, 이 유모차는 에코리움 실내와 야외에서 대여·이용할 수 있다. |
| NIE-C07 | U | 국립생태원에서 무료로 대여한 휠체어는 야외에서 이용할 수 없다. |
| NIE-C08 | S | 국립생태원은 안전한 관람을 위해 주류, 버너, 텐트, 그늘막, 공과 자전거·인라인·킥보드·전동자동차 등 소형 탑승기구 및 안내견을 제외한 반려동물의 반입을 금지한다. |

제외안은 별도 보존한다. X01/X04는 U로 판정 가능하다는 검토 의견이 있으며, 제외 이유를 모두 라벨 미확정이라고 쓰지 않는다.

## 고정 호출 계획

| 묶음 | 순서 | 기대 | 새 요청 |
|---|---|---|---|
| normal_detail | X=C01, Y=C08 | S/S | baseline1 + diff1 |
| permission_place | X=C02, Y=C03, Z=C04 | S/U/C | baseline1 + diff1 |
| equipment_scope | X=C05, Y=C06, Z=C07 | S/C/U | baseline1 + diff1 |

baseline3 이후 diff3, 총6 신규·응답재사용0. 각 조건 고유8판정, 전체16출현이다. 동일 원문·부모·후보 순서·system·숫자 라벨 계약·모델·sampling을 유지하고 diff 조건의 user JSON에 문자 차이 객체와 기존 고정 주의문만 추가한다. 이 패키지의 비교이며 순수 문자 연산만의 효과로 분리하지 않는다.

참조 runtime은 `qwen3.8:27b-q4_K_M`, native llama-server, ctx8192, no-context-shift, 단일 슬롯, seed42·temperature0·cache_prompt=false·n_predict2048이다. 참조 파일은 과거 실측값이며 현재 서버 상태를 새로 확인한 기록이 아니다. 실행 배정 후 engine/GGUF/props/token ID를 확인한다. 전체 입력+출력2048이 ctx8192 안에 들어야 한다. 맞지 않으면 문서·후보를 줄이지 않고 실행 전에 중단·보고한다. ctx 변경은 baseline/diff 모두 동일하게 고정하고 최초 호출 전에 명시한다.

## 출력 계약과 통과 기준

공통 JSON의 `differences`, `judgments` 구조를 유지한다. 문구 aliases는 supported→1, unsupported→2, contradicted→3의 고정 1:1 대응만 허용한다. 이유·근거·오류 구절은 수정하지 않는다. 빈 quote는 같은 field의 반대편 유일한 비빈 quote가 변경 전 입력의 단일 insert/delete opcode 전체와 일치할 때만 typed `[p,p)` 좌표를 부가한다. 부분 opcode, 두 빈 quote, 배열 field, 모호한 위치, 알 수 없는 alias는 실패다. Entity 배열 원소 인용에 임의 path/index를 만들어 주는 수리는 없다. 변경된 입력은 실행기의 동결 hash 검증에서 실패시켜야 하며 parser 단독으로 과거 파일의 불변을 증명하지 않는다.

Entity 배열 길이가 다른 새 후보를 그대로 유지하기 위해 string path의 합집합을 사용하고 없는 path와 빈 문자열을 명시적으로 구분한다. 새 입력 계약 버전이며 원래 동일 path B1 4묶음의 diff 객체는 정확히 동일함을 검증했다. 원문 지지·의미 차이를 서버가 대신 판정하지 않는다.

diff의 모든8라벨, 정상4 보존, U/C와 자료 범위, 차이 설명·정확 오류 위치·관련 원문 근거·이유, 공통 기술 계약이 모두 통과해야 gate 통과다. 근거 없는 완전성·면제·금지를 이유에 추가하면 라벨이 맞아도 실패다. baseline도 같은 기준으로 별도 평가하며 개선/동일/회귀를 모두 남긴다. 공통 gold, 계약 실패, 자료 부족, 미확정 응답을 분모에서 빼지 않는다. baseline도 모두 통과하면 추가 효과 0으로 기록한다. 골드 수정·prompt 재시도·후속 seed 호출은 이 계획에 없다. 새 확인 통과도 실제 저장 교정·제품 채택 완료가 아니다.

## 오프라인 검증과 원래 실패 보존

40주소·세 diff 묶음의 모든 문자 구간/원형 복원·조건 간 입력 동일성, 기존 저장 응답8개 기술 계약, 잘못된 계약4개의 거절을 확인했다. 이는 새 의미 판정8개가 아니다.

최초 주소 준비는 `source_text.count(text)==1` assertion으로 실패했다. NIE-B018 문구4회·NIE-B020 문구3회가 다른 블록에 포함됐기 때문이다. 각 고유 `[NIE-Bxxx]` 표식 뒤의 exact text와 블록/부모 순서로 주소를 복구했다. 전역 첫 문구를 임의 선택하지 않았다. 이 좌표는 보존된 추출 원문에 대한 주소이며 기존 company DB의 실제 parse/version 주소라고 주장하지 않는다. 원문·후보·gold·그룹·의미 지시는 그대로다. 실패 receipt를 보존하고 새 의미 개선으로 세지 않는다.

원래 B1은 읽을 수 있는 라벨7/10→10/10이나 최초 엄격 계약2/4와 condition.Y의 부가 추론 오류로 gate=false였다. 별도 기술 계약에서 저장 응답8/8을 수용한 것은 alias/빈 문자 좌표 수용 결과다. 최초 실패·이유·raw·동결 코드/기준은 변경하지 않았다.

시간 표기 정정: 원래 B1 `driver_wall_s=217.881268042`는 finally 진입 시점에 기록되어 후속 종료 tail을 포함하지 않는다. 원래 보고서의 “적재/실행/종료 driver” 문구는 범위가 넓었다. 최초 수치/파일은 보존하며 이 부록에서 범위만 바로잡는다. B2 driver 시간은 실제 종료 이후 기록했다.

## 실제 작성/검토 실행 근거

| 역할 | 실제 세션 | 실제 모델/effort | 누적 input / cached / output |
|---|---|---|---|
| 작성 | 01a12947-fff0-7931-a0bd-6f83d91a701b | gpt-6-astra / xhigh | 1,314,389 / 1,249,920 / 18,960 |
| 블라인드 검토 및 동결 후 gold 비교 | 01a1294f-1052-7652-932b-0300f7ff740c | gpt-6-astra / xhigh | 797,746 / 749,952 / 16,064 |

부모 spawn 기록의 fork_turns=none, 실제 agent path/turn_context model/effort와 마지막 token_count를 대조했다. guardian auto-review 로그를 실제 작성 모델로 사용하지 않았다. 누적 API 카운터는 반복 문맥과 캐시를 포함하며 고유 원문 토큰이나 청구 비용이 아니다. 제품/native 모델 호출0·local 적재0과 별개다. 동일 모델의 별도 fresh 문맥 검토이며 사람/다른 모델 검증 또는 통계적 독립은 아니다. 검토자의 처음 “확인 불가” 기록은 보존하고 부모의 검증 receipt를 추가했다. 로컬 세션의 reviewer 위임 문구는 암호화되어 exact plaintext를 복원하지 않았으며 dispatch 지문과 검토 method/receipt를 보존했다.

## 보존 경로

- 실행 입력·criteria·freeze·source·v1/v2·gold·blind·provenance: `/Users/hyeongi/.codex/worktrees/business-semantic-research/Civil-Complaints-System/data/knowledge/evaluations/business_candidate_diff_confirmation_20261011`.
- 준비 보존 묶음: `/Users/hyeongi/.codex/artifacts/business-candidate-diff-confirmation-20261011/prepared`.
- 같은 이름 JSON은 버전·수치·경로를 구조화한 기록이다. `freeze_manifest.json`의 최초 준비 snapshot은 보존하며 추가 메타데이터/검증/문서는 별도 `preservation_manifest.json`에 담는다.
- 원래 B1/B2 final archive manifest는 모두 불변 검증했다. 준비 코드는 research checkout에만 추가했으며 제품 코드/DB·merge/deploy는 변경하지 않았다.
