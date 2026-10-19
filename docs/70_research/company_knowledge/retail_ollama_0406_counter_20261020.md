# Ollama 0.40.6 계수 호환과 고정 M02 QA 한 쌍

2026-10-20. 검증된 두 메시지 텍스트 경로에만 0.40.6 계수 호환을 추가했다. 입력·한도를 바꾸지 않고 저장된 선택 응답의 후속 QA를 각 1회 실행했다. **계수 호환은 채택하고, relation_refs의 답변 효과는 M02 부분 개선으로 제한한다.** main 자율 검색·전체 M02·M03 해결을 뜻하지 않는다.

## 변경 이유와 범위

기존 계수기는 Ollama 0.40.3만 검증 대상으로 허용해 0.40.6에서 보수적인 `utf8_bytes/2+output+1000`으로 돌아갔다. 이 추정으로 직전 연결참조 QA 입력이 57,395로 계산돼 49,152 guard에서 차단됐다. 당시 provider 실제 초과 여부는 미확인이었으며 그 기록을 보존했다.

공식 태그의 [0.40.3 renderer](https://github.com/ollama/ollama/blob/eab97e9f92b9a25c2d52d2cc6c1b1c99bd9fae21/model/renderers/qwen35.go)와 [0.40.6 renderer](https://github.com/ollama/ollama/blob/2476d5ead197abe04629651028f83d48dc75d2b2/model/renderers/qwen35.go)를 대조했다. 이번 system→user 두 메시지, 텍스트, think=false 경로는 같은 trim·prefix·빈 think block을 사용한다. [prompt 구성](https://github.com/ollama/ollama/blob/2476d5ead197abe04629651028f83d48dc75d2b2/server/prompt.go)과 [chat completion 전달](https://github.com/ollama/ollama/blob/2476d5ead197abe04629651028f83d48dc75d2b2/server/routes.go)에서 schema format은 메시지 prompt와 별도다.

설치 바이너리 revision도 2476d5e와 일치하지만 `vcs.modified=true`여서 완전히 동일한 공식 바이너리라고 주장하지 않는다. 실제 local manifest/config/layer content address, qwen3.8 renderer, GPT2/qwen35 tokenizer metadata·no-BOS·vocabulary/merges를 검증했다. 계수 검증에서는 추론 모델 가중치를 초기화하지 않고 tokenizer metadata로 로컬 BPE 계수기를 구성했다.

제품 버전 gate를 바꾸기 전에 기존 helper로 저장 native 네 건을 계수했다. provider `prompt_eval_count`와 모두 차이0이었다: union QA 25,255, 동일 엔진 baseline QA 20,084, all30 selector 1,825, relation_refs selector 4,610. 추가 probe는 없었다.

변경은 `model_input_budget.py`의 검증 버전 집합에 0.40.6을 추가하고 renderer 계약명에 실제 버전을 남기는 것뿐이다. 0.40.3 동작, local identity 검증, 메시지 제한과 보수 fallback을 유지한다. history/media/tools/다른 engine을 새로 허용하지 않는다. counter/client/union 관련 검사43개가 통과했고, 미검증 0.40.4·0.40.5·0.40.7 거절과 실제 공용 guard의 경계 차단도 검사했다.

## 그대로인 입력과 실제 용량

기준은 bd0370dc의 opt-in union이며 후보30은 미채택 e155 실험에서 동결된 것이다. all30_v1과 relation_refs_v1의 완료 선택 응답 및 직전 PPR·union 입력을 재사용했다. 새 선택·PPR·임베딩·추출을 실행하지 않았다.

기존 두 QA_request의 messages/schema/alias가 재구성된 요청 및 실제 native wire와 정확히 일치했다. source·문맥·QA 지시·모델 digest·temperature0·think=false·ctx49,152·output8,192·timeout1,800을 유지했다. 제공 claim 수에 따른 citations enum/maxItems15→19는 기존 입력 계약의 차이이며, 메시지만의 순수 효과로 해석하지 않는다.

| 항목 | all30 기준선 | relation_refs |
|---|---:|---:|
| 기존 보수 guard 추정 | 48,251 | 57,395 |
| 검증된 prompt 계수 / 실제 provider | 24,976 / 24,976 | 30,776 / 30,776 |
| 별도 schema 예약 | 166 | 182 |
| 출력 / 안전 예약 | 8,192 / 1,000 | 8,192 / 1,000 |
| 새 공용 guard 합계 | 34,334 | 40,150 |

schema 예약은 실제 prompt 토큰에 합쳐 관측한 값이 아니며 기존 보수 여유 정책이다. 이 두 입력은 변경 없는 예산으로 실제 실행됐고, 예측 prompt 수가 신규 응답에서도 정확히 맞았다. 이를 모든 입력의 fallback 과대추정이나 다른 버전 지원으로 일반화하지 않는다.

## 실제 QA 의미와 미해결

| 항목 | all30 기준선 | relation_refs |
|---|---|---|
| 태안 제조원 | 제공 근거 부족으로 미답 | 태안시니어클럽 태안콩두부, 직접 제조원 claim 인용 |
| 태안 보관 | 제공 근거 부족으로 미답 | 냉장보관, 태안 보관 claim 인용 |
| 가마솥 제조원 | 늘마루 협동조합 유지 | 유지 |
| 가마솥 온도·개봉 후 보관 | 0~10℃·밀봉·냉장·가급적 빨리 섭취 | 유지; 태안에 온도 전용 없음 |
| 공통 재료 | 두부만 답함 | 두부만 답함 |
| 전체 재료가 없다는 limitation | 실제 입력과 충돌 | 같은 실패 지속 |
| 김치찌개 조건부 간장 OR 소금 설명 | 명시 안 함 | 명시 안 함 |
| 제공 claim 인용 / 출처 | 4 / 3 | 6 / 4 |

양쪽 `reviewed_meanings.evidence`에는 MFDS의 두부·간장·다진 마늘·고춧가루·소금 등을 포함한 전체 재료 인용이 이미 있다. 그러므로 전체 목록이 없다는 limitation은 **근거 활용·범위 오독**이며 자료/검색 부재로 분류하지 않는다. 공통 재료 나열만으로 간장과 소금 모두 항상 의무라고 단정한 오류를 추정하지 않지만, 모델이 조건을 활용했다는 증거도 없다.

제조원·보관을 포함한 실제 인용 claim과 source/version/block/span/quote를 대조해 주소 오류0을 확인했다. `answered`는 형식·제공 ID 검사 상태이며 전체 의미 성공이 아니다. 인용은 전역 배열로 문장별 대응 계약이 아니다.

relation_refs의 ‘두부조림에 사용 가능한 제품으로 해석할 수 있으나 특정 제품 지정 근거는 없다’는 문장은 모델의 추론·한계 표현이다. 명시 원문 사실이나 상품 대체가능성 검증으로 승격하지 않는다. 신규 답변의 limitations에는 q3/q4 내부 별칭도 남았다. 재생성이나 인접 제품 수정으로 숨기지 않았다.

## 실제 비용과 보존

| provider 관측 | all30 | relation_refs |
|---|---:|---:|
| 입력 / 출력 토큰 | 24,976 / 219 | 30,776 / 326 |
| client 요청 시간(초) | 167.492158 | 232.741555 |
| load 시간(초) | 5.859777 | 5.107358 |
| prompt cache 토큰 | 0 | 0 |
| 종료 / 잘림·빈응답·실패 | stop / 없음 | stop / 없음 |

각 arm은 상주 모델0에서 시작했다. 응답 후 API의 모델 size/size_vram은 각각19,829,987,736 bytes, context49,152였다. 이는 provider 보고값이며 RAM/VRAM을 더해 두 배로 세지 않는다. 각 arm이 로드한 모델만 empty-prompt unload 관리 요청으로 해제했고 서버는 재시작하지 않았다. unload2회는 QA/probe 생성이 아니다. OS/파일 cache와 bit 단위 연산 동일성은 통제하지 않아 두 시간으로 일반 속도 성능을 주장하지 않는다. 금액 비용은 산정하지 않았다.

신규 QA2·재시도0·repair0·selector/PPR/embedding/추출/probe0이다. 저장 입력·원본 DB·이전 실패·동결 코드는 별도 위치에 보존하고 복사 DB와 새 run을 사용했다. raw/DB/큰 응답은 Git에 포함하지 않는다. 계보 narrow≥11/broad≥12, 전체·잔여 unknown, semantic6/6 closed/no_reset을 유지한다. 이번 호환/후속 QA를 새 선택 변형으로 세거나 초기화하지 않는다.

## 채택과 다음 경계

검증된 counter 호환 변경은 채택한다. relation_refs+union은 이 노출된 M02의 선택→근거→QA 부분 효과와 제한 통합 후보로 보존한다. 공통 재료 활용 실패 때문에 전체 M02는 미완료이며 main의 자율 후보 확보·M03·일반화를 검증하지 않았다. 기본 경로 반영·병합·배포는 하지 않는다. 다음 통합 판단은 이 잔여와 출처별 정상 보존을 분리해 검토해야 한다. 현재 승인 범위 완료에 사용자 결정이 필요한 사항 없음.

로컬 증거는 `retail-knowledge-pilot-20261018/ollama_0406_counter_QA_v1_20261020/`의 `native0_counter_contract_validation.json`, `QA_execution_manifest.json`, 각 arm native wire/response/run/receipt, `paired_answer_evidence_review.json`, `answer_citation_source_mapping.json`, `pre_git_preservation.json` 및 최종 인계에 보존한다. 원문/입력 해시는 직전 `M02_relation_refs_downstream_v1_20261020/` 기록과 연결된다.
