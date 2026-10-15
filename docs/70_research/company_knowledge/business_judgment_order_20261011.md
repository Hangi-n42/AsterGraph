# 후보별 판단 후 차이 설명의 정상 보존 대조 — A05

2026-10-11. 새 동결 가설·순서 변경·실제 실행·기각 결정을 갖춘 제한 비교 A05/R39, A 누적5다. 독립 대상은 노출된 c46 한 건, 후보2개다. #654의 Entity 구성 보완, 이전 A01~04의 결과·기준과 제품 후속 기록을 변경하지 않는다. 새 알고리즘·모델 개선·제품 통합 성과로 세지 않는다.

## 실제 결과와 결정

| 항목 | 기준선: differences 먼저 | 신규: judgments 먼저 |
|---|---|---|
| 사전 기대 | S/S | S/S |
| 실제 X/Y | U/S | U/S |
| 정상 원본 회복 | 실패 | 실패 |
| 출력·주소 | 기존 보존 기록 | 실제 최상위/내부 순서·정확 주소 통과(동일 응답 오프라인 복구) |
| 의미 이유 | 세부 완전성과 주장 지지 혼동 | 같은 혼동 및 Y의 모든 조건 포함 과장 유지 |

X는 날인 불필요나 해당 서류만으로 충분하다고 주장하지 않는다. 신규 판단도 날인 세부 미언급을 필수 조건 누락으로 보아 X를 U로 내렸다. Y는 양도증명서 날인 수식을 추가했지만 기존 위임장 날인 세부는 여전히 없는데, 새 이유는 그 조건을 포함한 원문의 모든 필수 조건을 반영했다고 서술했다. 기대 S를 사후 U로 바꾸지 않으며, Y의 S 라벨과 이유의 과장을 분리한다. root의 별도 저장 원문/입출력 대조도 같은 실패를 확인했다. 사람 시험·독립 모델군·공식 점수는 아니다.

사전 gate 실패로 이 구성은 기각·중단했다. 추가 모델·순서 조정·통제 확대·프롬프트 재시도0, 제품 통합·교정·그래프·검색·QA0이다. 먼저 생성된 differences를 판정 접두부에서 제거해도 이 오판이 지속됐으므로 해당 접두부가 이 실패의 필수 원인이라는 가설은 지지되지 않았다. 내부 비교·상대의 세부사항 주목·주장 지지와 완전성 혼동의 다른 원인이나 모든 출력 순서 변경의 불가능은 입증하지 않는다. 남은 설명은 미검증이며 새 방법을 자동 추가하지 않는다.

## 동결·변경·재사용

한 문장만 `출력은 differences와 judgments를 이 순서로 가진 JSON 하나다.`에서 `출력은 judgments와 differences를 이 순서로 가진 JSON 하나다.`로 바꿨다. 원문·부모·candidate raw와 X/Y 순서, 라벨 대응, 내부 judgment 필드 순서, 의미 기준과 evidence-ID 계약은 같다. source/candidates JSON SHA-256은 `50129ba9f363cc1e9d293fef262b3e20718eaf6d4a7203b15a91b054b17a947a`다. 정확 diff·전체 요청은 로컬 ignored 평가 자료이며 기대 라벨·gold·생성 이유를 새 prompt에 넣지 않았다.

기준선 joint 응답1을 재사용했다. 같은 engine/GGUF 전체 SHA·모델 태그·실행 argv/props(동적 media marker 제외)를 확인하고 원 baseline prompt의 fresh token IDs1805개 및 전체 request parameter 일치를 검증했다. 신규 prompt도1805토큰이다. Qwen3.8 27B Q4_K_M, native ChatML/빈 think, T0·seed42·ctx8192·출력2048·단일 슬롯·cache-ram0 등 기존 설정을 유지했다. tag manifest SHA는 `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`이며 설치 모델 layer가 같은 GGUF에 연결됨을 확인했다.

## 형식·하네스 오류·비용 분리

실제 EOS·비잘림·cache0, 최상위 judgments/differences와 X/Y·내부 필드 순서가 맞았다. 원시 응답 저장 뒤 최초 주소 검증은 launcher가 scripts만 sys.path에 넣고 repository root를 누락해 `ModuleNotFoundError: app`로 중단됐다. 이 초기 상태·실패와 실행 driver를 보존했다. root import 경로를 포함한 오프라인 환경에서 같은 frozen parser와 같은 응답을 검증해 주소 계약을 복구했다. 모델 재호출·원시 출력/라벨/프롬프트 수정0이다. 재현 시 `PYTHONPATH`에 repository root와 scripts를 포함하며 저장 응답 parse만 수행한다. 실제 최초 하네스 통과와 복구 후 주소 통과를 동일하다고 쓰지 않는다.

| 구분 | 신규 호출 | 기준선 재사용 | 실제 입력/출력 토큰 | 모델 응답 시간 |
|---|---:|---:|---:|---:|
| 최상위 순서 대조 | 1 | 1 | 1,805 / 552 | 38.267528초 |

모델 시간은 prompt_ms+predicted_ms다. 기준선 과거 비용은 신규 합계에 넣지 않는다. 엔진/GGUF 해시 검증6.012325초는 별도다. completion wall/driver 시간은 후처리 예외 때문에 필드가 저장되지 않아 확인 불가이며 모델 시간이나 서버 보유 시간으로 대체하지 않는다. parser 경계4개(기준선 판단 불변, 최상위 순서, 내부 순서, 잘못된 source ID 거부)가 통과했으나 의미 품질 증거가 아니다.

소유 PID50099의 정확 command를 확인해 SIGTERM으로 종료했고 exit0·11435닫힘·Ollama models=[]를 기록했다. 추가 자원 점유0이다.

## 보존과 공개 경계

로컬 평가 경로는 `data/knowledge/evaluations/business_judgment_order_20261011/`다. 준비/동결·원시 응답·초기 하네스 실패·같은 응답 오프라인 검증·실제 driver·baseline 재사용·독립 대조·자원 종료를 영구 artifact `/Users/hyeongi/.codex/artifacts/business-judgment-order-20261011/final`에 파일별 SHA로 보존한다. [구조화 결과](business_judgment_order_20261011.json), [사전 동결 계획 영수증](business_judgment_order_plan_20261011.md).

새 이슈 설계 공개는 자동 승인 검토 거절 후 직접 사용자 승인을 대기한다. 공개/이슈 재시도·push0이며93d1bad0의 별도5파일 승인 대상은 변경하지 않았다. README 두 변경과 기존 원장 제품 후속8줄은 보존·분리한다. 전체 R05/#616/#617/#620 미완료와 제품 judge 미채택을 유지한다. 다음 작업은 추가 실험 없이 대기다.
