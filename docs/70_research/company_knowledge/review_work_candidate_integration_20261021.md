# R2→G1→W1 후보 경로의 명시 옵션 연결

최신 개별 edge top30 경로에 기존 원문/동일 Head 검색과 검토 작업 후보를 연결하는 기술 검증이다. 새 후보 알고리즘이나 독립 품질 평가가 아니다. 기본값은 `candidate_contract=None`이며 기존 후보 입력을 유지한다.

`BusinessQuery.candidate_contract='r2_g1_w1'`은 `snapshot_id`, `hipporag2`, `graph_variant='full'`, `answer_mode='synthesis'`, 빈 `requirement_ids`, graph context에서만 지원한다. 다른 범위의 명시 옵션은 검증 오류다. 프런트엔드나 기본 활성화는 추가하지 않았다.

- R2는 기존 dense 순위와 원문 BM25의 주장 연결 J0 및 정확 동일 source/parse/Head 주소·entity node의 직접 속성 연결 J1을 RRF k=60으로 결합한다. 원문 기여는 최선 순위 하나만 사용하며 재귀 확장하지 않는다.
- G1은 claim/snapshot/source set별 자식을 만들고 concept를 singleton으로 유지한다. W1은 출처·조건·상태·오류·의미 필드와 유일한 역할/주소가 일치할 때만 검토 작업을 공유한다. 불명확한 자식은 singleton이다. 원주장이나 의미 승인을 합치지 않는다.
- 앞30 검토 작업의 개별 member만 선택 가능하다. G1 앞30 자식의 alias를 유지하고 새 member에만 추가한다. schema는 개별 ID 최대30이며, 기존 `json_call`로 역복원한다. 그룹 전체 seed 확장은 없다.
- R2 점수는 후보 순서에만 사용한다. 후단 seed/PPR에는 기존 dense edge/passage 배열을 그대로 전달한다. `query_scores` 분리는 무모델 진단에서 이 배열을 대조해 주입할 수 있도록 기존 점수 계산을 그대로 옮긴 것이다.
- trace는 `candidate_contract`, `candidate_collection`, `candidate_groups`, `review_work_units`, `work_eligibility`, `candidate_bindings`를 보존한다. bindings는 원주장/출처/조건/해석·오류와 현재 edge를 담고, 원래 생성 graph의 `construction_edge` 상태를 별도로 담는다. accepted와 semantic unknown/unverified는 구분한다.

## 확인한 결과

고정 snapshot57 claim/714 edge/49 passage와 저장 점수를 사용한 제품 API 진단에서, selector 전송 직전에 중단했다. 실제 자율 검색 결과로 해석하지 않는다.

- R2 전체 점수·J0/J1 경로·정렬, G1 전체665 자식, W1 전체661 작업·eligibility·63 member/alias가 저장 결과와 일치했다.
- 제품 `json_request`가 작성한 messages/schema/reference map 및 순서/나머지 필드가 저장 W1 요청과 정확히 일치했다. 기존 모델 설정의 정적 adapter projection도 같았다. 현재 서버 runtime·실제 wire 전송은 검증하지 않았다.
- 최신 개별 후보의 사실12개와 실제 선택4개, G1 member57개를 후보에 보존했다. 제외된 concept16개는 저장 graph에 유지된다. 평가 정상13은 후보13/13이었다.
- 최신 PPR baseline12 목록 중 W1 후보 노출은10/12다. 나머지2개는 원래 selector 후보에도 없었다. 후보 노출 수이며 후단 근거손실 판정이 아니다. 이 목록이나 정답 ID를 제품 입력에 강제로 넣지 않았다.
- 같은 저장 요청의 순수 로컬 0.40.6 계수는 OFF prompt1954+별도 schema162+O8192+safety1000=11308, ON 5140+294+8192+1000=14626으로 C49152 이내다. provider 사용량 측정이 아니다. GGUF와 API 지문 차이는 공식 `GetModelInfo`의 `tokenizer.chat_template` 제외 규칙을 정확히 재현해 기존 지문과 일치시켰다. 최초 불일치 기록도 보존했다.
- 구조·서비스 경계 검사15개와 `git diff --check`가 통과했다. 최초 진단의 passage envelope 비교 오류는 별도 보존하고 소비 주소/quote/claim 연결·원문 검색텍스트를 직접 대조했다. API/후보 성공 후 계수 보완 과정에서 재실행하지 않았다.

모델·embedding·selector·rank/PPR·QA·네트워크 호출은0이다. 개별 alias 역복원/후단 인자 검사는 스텁에서 중단했다. 새로운 선택 이후 정상 의미·조건·출처 전달, 최종 세 핵심 동시 보존, 답변 품질은 미검증이다. 중량 판단 미해결과 기존 ≥19/≥20, closed semantic6/6/no_reset을 유지한다.

## 기반과 후속 경계

구현 기반은 `198160e5e0490adb7d283ccc66ed3924d6d8f32b`이다. main `55f0bf77f89e32992ac3f3c1afcefe4d70a05c7c`에 없는 선행 `ranked_preserved_claims_v2` 조립·원문 참조 순서 및 Ollama0.40.6 counter 변경을 포함한다. main이나 과거 실험 branch를 병합하지 않았다.

현재 범위는 명시 옵션의 기술 연결까지다. 후속 실행에는 현재 runtime 계약과 후단 전달의 별도 확인이 필요하다. 검색 간 재순위 자체는 회귀가 아니다. 같은 검색의 필수 문맥 뒤 선택적 추가 중 첫 용량 초과→마지막 유효 상태 복원은 정상 종료이며, 필수 근거가 들어가지 않거나 복원 후 핵심/정상 의미가 빠지면 실패다.

상세 요청·중단 기록·무호출/보존 영수증은 로컬 `M03_product_review_work_integration_20261021` 아티팩트에 보관한다. 원본 DB·원응답·실험 원시자료는 저장소에 추가하지 않는다.
