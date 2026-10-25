# 허용 대상 제한 종합의 실제 1회 실행 — 2026-10-26

## 진행 이유와 고정 범위

[출력 대상 계약](business_synthesis_owner_scope_contract_20261026.md)의 무모델 검증 뒤,
사용자가 승인한 입력 용량 확인과 종합 1회만 실행했다.
실행 코드는 원격과 같은 `3835f08aefa0dd43963ce06d38850fa9533b4620`이며 생산 코드·지시·스키마를 추가 수정하지 않았다.
F/G/H 산출물과 원본 DB 8개를 보존하고 G DB의 별도 복사본에 새 run을 등록했다.
완료된 교정·자기 원문 검수는 유지하고, 표현 검수 5개는 메시지·스키마·참조표·설정이 같은 저장 응답으로 재사용했다.
상위 적용성 선택·재교정·개별 검수·추가 judge는 새로 호출하지 않았다.

새 run은 `375d96f925d14fdd94f48c092ec9b5f5`, parent G는 `3b16f56dfa7d41519cc6f3e696259789`다.
G 최종 run과 기존 실패 기록도 복사 DB에 그대로 남겼다.
이번 입력은 실제 after-R checkpoint의 확정 source를 사용하며, H에서 확인한 새 요청 전체와 일치했다.

## 실제 용량 gate

Qwen `qwen3.8:27b-q4_K_M`, digest `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`,
Ollama 0.40.10/Q4_K_M, temperature 0, think=false, timeout 1,800초를 G와 같게 고정했다.
모델 identity/runtime을 준비 및 전송 직전에 확인했다. 문맥은 이번 실행의 49,152이며 다른 QA 설정을 사용하지 않았다.

| 계수/예약 | 토큰 |
|---|---:|
| 실제 메시지의 정확 prompt | 19,766 |
| 별도 스키마 보수 예약 | 1,963 |
| 출력 예약 | 8,192 |
| 안전 여유 | 1,000 |
| 예약 포함 예산 / 문맥 상한 | **30,921 / 49,152** |

기존 정확 계수 계약으로 통과했다. H의 통제 예산 stub은 사용하지 않았다.
스키마 예약은 관측 prompt가 아니며 전체 합계도 보수적 예산이다.
실제 응답의 provider prompt_eval_count는 **19,766**으로 사전 정확 계수와 일치했다.

## 원시 출력과 소비 결과

새 로컬 생성은 **종합 1회**, 원시 응답 1개, 재시도 0이었다.
request ID는 `7589ca28a96e47cab0fc64f57b20d83b`, 종료 사유는 `stop`, failure_kind는 null이다.
과거 G 응답을 새 요청의 캐시로 사용하지 않았다.

- raw checks는 허용된 `batch5:m3` 한 행이다. 범위 밖 owner·중복은 0이다.
- 최상위 dependencies는 **[]**, 즉 변경 행 0개다. 허용 범위 위반은 없지만 독립성을 새로 확인했다는 뜻은 아니다.
  대상 5개에서 행 갱신을 생략했고, 기존 10개 의존성 행과 각 premise_keys=[]가 그대로 보존됐다.
  이번 원시 응답은 개별 premise_keys=null이나 새 참조 끝점의 준수를 실제로 시험한 사례가 아니다.
- 제품 소비 결과는 join_succeeded=true, source_join_succeeded=true다.
  join 오류·국소 실패·assessment 오류·source/meaning/candidate 이의는 모두 없었다.
- 최종 M03 assessment와 공개 항목 1·2·3은 **partial**이다.
  raw satisfied/conjunctions_satisfied도 false다. 구조적 계약 통과를 전체 요구 충족으로 승격하지 않았다.

최종 assessment는 `659def2d45794d81bef5b25b6352bcb1`이다.
실제 receipt에 recheck_assessment_id를 연결하고 기존 규칙대로 **recheck_incomplete**를 저장했다.
현재 제품은 assessment가 satisfied일 때만 rechecked를 기록하며 partial이면 recheck_incomplete를 기록한다.
따라서 이 상태는 이번 종합의 출력 오류를 뜻하지 않는다. 상태 체계 자체는 변경하지 않았다.
제품 assess/save_assessment 경로의 run·요구 current_assessment·receipt를 별도 DB 연결로 재조회해 일치를 확인했다.
추가 재판정·교정·그래프 갱신·사용 승인은 하지 않았다.

## 정상 정보와 보강 2건 보존

기존 G 최종 저장 판정과 이번 I 최종 저장 판정의 checks 10행을 비교했다.
m3의 reason 문구만 달랐고, 상태·기여 위치 등 나머지 필드는 같았다. 다른 9행은 객체 전체가 같았다.
source_checks 10행과 dependencies 10행도 같았다.

소비 전 compact와 비교하면 3행의 claim_support에서 비기여 후보 4개가 빠져 보인다.
이는 기존 attach_candidate_support가 현재 claim_ids에 대해서만 지지 맵을 구성하는 동일한 소비 처리다.
이 4개는 기여 claim_ids에 포함되지 않았고 상태·기여 위치·자기 원문 검수 기록도 바뀌지 않았다.
소비 전·후 층위 차이와 실제 저장 판정 보존을 구분해 두 비교 원장을 함께 남겼다.

m4 보관 권고와 m7 열람 경로는 이번 새 checks에 반환되지 않았다.
저장 R 및 실제 소비에서 기존 새 후보 ID·represented 상태·supported 기록·내용·정확 주소/조건이 유지됐다.
활성 후보의 semantic_status=unknown, review_status=unreviewed, 미해석 상태도 그대로다.
이번 종합이 두 후보를 새로 생성하거나 다시 원문 검수해 성공시킨 결과가 아니다.

현재 199개 주장 전체 객체, blocks/graph/concepts/candidate_reviews/model_identity는 입력과 같았다.
복사 DB의 decisions/snapshots/knowledge_state, 요구의 질문·criterion·revision도 같고 승인·snapshot 전환은 없다.
원본 DB 8개, F 94개/G 134개/H 42개 파일과 각 manifest는 해시가 같다.
기존 parent G 최종 run도 복사 DB에서 변하지 않았다.

## 남은 의미 판단과 비용

모델은 m3의 등심 일반 특성(담백/어떤 요리에도 무난)의 후보 표현 부족을 부분 판정 사유로 들었다.
등록 상품의 등심·카레 용도와 레시피의 등심 지정 후보는 별도로 존재한다.
원래 question/criterion은 상품 부위·용도와 레시피 지정 내용을 비교하고 확정 불가 내용을 구분하도록 요청한다.
일반 특성 표현이 그 질문의 필수 전제인지 이번 실행에서 독립 확정하지 않았다.
따라서 모델의 부분 판정 사유를 질문의 확정 필수 공백으로 채택하지 않는다.
단어 검색의 미발견도 의미상 부재 증거로 확대하지 않았다.
m6 조리법 미저장과 미채택 Scope의 권고→의무 강화 오류 역시 해결된 것으로 계산하지 않았다.

새 provider 입력/출력은 **19,766 / 2,392토큰**, client generate 경과는 **271.595858초**,
저장 응답 재사용·계수·저장을 포함한 단계 wall은 **331.148143초**다.
provider total/load/prompt-eval/eval 원시 ns를 초로 환산하면
270.591383709 / 7.145806667 / 114.441297 / 148.940153초다.
이번 세부 시간은 total보다 큰 값이 없었다. 이전 G의 불일치 원시는 그대로 보존했다.
이 한 사례로 속도 개선을 주장하거나 계측하지 않은 시간 차이의 원인을 추정하지 않는다.

10초 간격 27개 표본에서 Ollama/llama-server 프로세스 RSS 합의 관측 최대는
20,824,506,368바이트(약 19.39 GiB)였다. 통합 GPU 메모리 전체나 확정 peak가 아니다.
종료 후 엔진이 보고한 size/size_vram은 각각 19,829,987,736바이트, context_length는 49,152였다.
이 값도 프로세스 RSS와 구분했다.

닫힌 configuration 7·6/6·remaining 0·no_reset 계보를 유지했고,
이번 명시 승인된 owner 계약 종합 1회를 별도 provenance로 연결했다.
QA/검색/PPR/추출/개념화/임베딩/추가 judge/재시도는 0이다. 기존 H의 194개 검사는 재실행하지 않았다.

## 다음 작업과 결정

이번 범위는 용량 통과·실제 owner 범위 준수·기존 정보 보존·저장 재조회까지 완료했다.
일반 성능 개선, 핵심 질문 충족, 사용 승인은 확인하지 않았다.
다음 최소 작업은 원래 질문과 m3 필수성 판단의 근거를 읽기 전용으로 점검하는 것이다.
이번 결과를 다시 고쳐 생성하거나 새 교정을 자동 시작하지 않는다.
생산 코드 변경 없이 결과 문서만 기록하며 PR·병합·배포·이슈 종료는 없다. 현재 사용자 결정이 필요한 사항 없음.

원시 요청·응답·gate·메모리·소비/저장/보존 원장:
`~/.codex/artifacts/retail-knowledge-pilot-20261018/retail_synthesis_owner_scope_native_20261026_v1/`
