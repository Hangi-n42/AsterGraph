# 업무 요구의 필수 지식·참고 문맥과 교정 대상 연결

## 문제와 범위

복합 원문 의미 전체를 선택한 뒤 `required_for_requirement=true`만 붙이면, 질문이 부위·용도를 요구해도 같은 문장의 중량이나 전체 조리 절차까지 필수 누락으로 확대될 수 있다. source의 인용에 있는 내용을 저장 후보의 표현으로 읽는 문제도 별개다. 기존 item/RequirementLink와 R→G→repair 흐름에 필요한 하위 내용·실제 저장 표현 위치를 연결했다. 원문 의미를 분해·재작성하거나 새 판정 단계를 추가하지 않았다.

기준 main은 `fab7e1fe87960659b2ba386c827f47078d5c2dac`(#673)이고, 별도 작업트리와 `feature/knowledge-review-repair-integration` 브랜치를 사용한다. 관련 이슈는 #616, #620이며 이 PR에서 자동 종료하지 않는다.

## 계약과 소비 경로

1. 기존 항목별 `requirement_applications`에 `required_content`와 정확한 원문 `evidence`를 저장한다. 필요한 하위 내용이 미확정이면 `null`로 남기며 필수성 True를 False로 내리지 않는다. 원문의 문장·조건·예외·기간·연결 전제는 그대로 보존한다.
2. 같은 R 응답의 `checks`는 원문 전체 의미와 참고 잔여를 유지한다. `requirement_checks`는 확인된 필수 하위 내용만 검수한다. 서버가 요구·항목·원문 버전에 묶은 `requirement_scope_id`를 확인한다.
3. `represented_content`는 의미 요약이다. 별도의 `expression_quotes`가 실제 raw/interpretation 필드의 유일한 인용 위치와 후보 버전에 연결된다. source evidence, 인용 메타데이터, 설명문은 저장 표현 위치가 아니다. 이 주소 검사는 의미적 동등성을 자동 증명하지 않는다.
4. 국소 요약은 전체 의미 판정을 `whole_expression_checks`에 보존하고 질문 필수부분을 공통 `checks`로 투영한다. 서로 다른 부분 기여·잔여는 claim_ids/정상 기여/누락/정확 근거/검수 unit으로 같은 G 입력에 전달한다. 생략·null·빈 전제 목록을 서로 바꾸지 않는다.
5. 기존 G가 전체 저장 후보와 정상 부분 기여를 대조한다. 묶음 안의 미발견을 전체 생성 누락으로 확정하지 않으며, 원문 전체의 represented 라벨만으로 필수부분의 남은 후보 대조를 건너뛰지 않는다. R·G·완료 요약·QA에서 사용하는 필수 의미/기여와 repair 대상이 같은 판정을 사용한다.
6. recover에는 정상 기여와 실제 필요한 부족함, 원문 근거, 항목별 필요 이유, scope, 같은 범위의 국소 검수 기록이 함께 연결된다. 저장 raw/interpretation의 같은 출처 위치나 같은 버전의 기여 증언에서 누락 내용이 발견되면 중복 생성 대신 재검수를 요구한다. 존재만으로 충족으로 승격하지 않는다.
7. 원문 조건·예외·기간·전제 변경은 이전 하위 내용 범위를 무효화한다. 과거 저장 실행은 기존 계약으로 조회한다. 새 검수에 과거 응답을 재생해도 없는 하위 내용·표현 위치를 추론해 채우지 않는다. 공개 요구의 과거 recover도 검증된 새 scope 없이 실행하지 않는다.

후보 자기원문 정확성, source의 사실 판단, 질문상 필요성, 실제 저장 표현과 승인 여부는 각각의 기존 책임을 유지한다. 정상 형제 후보와 원응답 모순은 삭제하지 않는다.

## 선행 변경의 선택 통합

전체 브랜치를 병합하지 않고 main의 현재 코드에 필요한 최종 변경만 재구성했다. 아래 원본 SHA의 파일 목록·patch-id 원장은 작업 산출물 `ORIGINAL_COMMITS.json`, 선택 판정은 `COMMIT_MAPPING.json`에 있다.

| 원본 SHA | 문제·선택 파일 | 통합 SHA / 처리 | 근거·한계 |
|---|---|---|---|
| `a48fe9ac03c1032ef8e19d7b392a22b5b043d8f4` + `e9885ab613b9075c8a067ab5f87204b56c876b20` | `model_input_budget.py`, 계수 검사, 0.40.11 계약 문서 | `aacc3ea31e6498323110b4ee279815463423ade0` | 검증된 Ollama 텍스트 계수 호환. 입력 계수는 의미 보존의 증거가 아니다. |
| `6aa179285499eeb8d269f481cabd138903c297db` | `business_review.py`, 국소 검수 검사·문서 | `924a60b80d3c92183bd905f00604ccccee7d9e33` | G 이의 해소가 실제 근거를 요구하도록 지시 일치. |
| `21eb9b0bc46452ed14f59706ed124331947d5e6c` | `business_run.py`, repair 입력 참조 검사·문서 | `924a60b8…` | 교정 입력의 중복 해석 참조. 과거 repair 2건과 재검수 증거가 있으나 Scope 누락·m6 한계는 별도 보존. 일반 R 참조 압축과 구별한다. |
| `3835f08aefa0dd43963ce06d38850fa9533b4620` | `business_review.py`, owner 검사·문서 | `924a60b8…` | G 갱신 행의 소유 의미키를 스키마 Literal로 제한. 기존 list/필수필드 조건 유지. |
| `9b903252c91dc12037a10bef0e0f92f44cf0736e` | models/review/run/use, 관련 검사·문서, `KnowledgeBusiness.tsx` | `924a60b8…` | 필수성·부분 잔여 계약 및 True/False/null 표시. UI는 계약에 필요한 4줄만 채택했다. |
| `50c338b83a22e62320e74ec76ac96ef7a9f6d32b` | review, 국소/owner/모순 검사 | `924a60b8…` | 질문 필요성과 원문 AND 전제 구분, represented+명시 잔여 보류, 정상 형제 보존. 압축 문서의 종속 변경은 제외하고 본 문서에 한계를 기록한다. |
| `7ef908f8386d5f7b0eb459c2aa47690a1418ed15` | 일반 R 입력 참조 압축 | **제외** | 구조 복원·입력 감소는 확인됐지만 실제 응답의 의미 보존은 확인되지 않았고 회귀가 남았다. 기본 경로에 올리지 않는다. |
| `2710660dcd1619748922c59d82d83f668573ad6e`, `b7daf1457005621da4f9588342a4f722d08c2339`, `a94409ad39f6070990455a36a5e9a589d209afd9` | 과거 native 실행·중단·회귀 기록 | **증거만 참조** | 새 실행이나 성공 주장으로 재사용하지 않는다. 원본 기록은 보존한다. |
| `198160e5e0490adb7d283ccc66ed3924d6d8f32b`, `0422be30d16cb6019888a2373e2d56a1911f41a6` | 검색 후보 확장·명시 옵션 | **이미 main / 후속 변경으로 대체** | 재도입하지 않는다. 후속 Event 지원 `0fa4eef92aae956affe61d4865951c9720ca2f23`→`1932309cfc4ed1fe1740df21b85c9a4b6b642bb5`(#671). main의 `review_work_candidates.py`와 이 후속 원본의 diff는 비어 있다. |

이번 하위 내용 계약의 신규 커밋은 `e5203cac08bfb644c54cbbb63f8d2293b0cf2763`이다. 위 `aacc3ea3…`/`924a60b8…` 안전 계약 위에서 models/review/run/source_meanings와 관련 검사만 수정했다. 원본→재구성 커밋→이 신규 확장의 순서를 `COMMIT_MAPPING.json`에도 기록했다. DB 스키마 변경과 새 의존성 추가는 없다. 기존 검색 기본값·Event 지원·승인 스냅샷 정책은 중복 도입하지 않는다.

## 검증 결과

산출물 기준 경로:
`/Users/hyeongi/.codex/artifacts/retail-knowledge-pilot-20261018/retail_knowledge_review_repair_integration_20261027_v1`

### 합성 제품 연결

`test_knowledge_required_content.py`의 합성 JSON producer를 실제 application→R→G→assess→repair→save→재검수→GET 경로에 연결했다. source와 저장 본문이 일치하는 fixture를 사용했다. 가짜 producer 판정은 실제 모델 품질의 증거가 아니다.

- 부위·용도는 저장되고 참고 중량만 없으면 질문 필수부분은 충족, 전체 원문의 참고 잔여는 유지된다.
- 용도만 없으면 기존 부위 지식을 그대로 두고 용도만 repair→저장→재검수한다. 재검수 후 반복 repair가 없다.
- 필수부분이 전혀 없으면 빈 정상 기여와 정확한 누락·근거·범위가 repair 대상에 연결된다.
- 원문 인용의 수량은 저장 표현으로 세지 않는다. 실제 한 필드의 의역과 여러 후보/해석 필드의 정상 결합은 위치 검사를 통과한다.
- 전체 원문의 과대한 represented가 있어도 필수부분이 남으면 두 번째 후보 묶음을 대조한다. 두 묶음의 서로 보완적인 잔여가 같은 G 요청에 남는다.
- 이미 저장된 용도를 놓친 합성 R/G 응답에는 중복 recover를 차단하고 재검수 보류를 남긴다. 충족으로 승격하지 않는다.
- 원문 조건·예외·기간·전제 변경은 이전 적용성/하위 내용 scope를 재사용하지 못한다. 참고(False) 행은 새 필수부분으로 잘못 묶지 않는다.

최초 통합 검사는 337 통과/3 실패였다. 2건은 이전 합성 응답에 새 하위 내용 계약이 없었고, 1건은 전역 call 차단이 가짜 backend 토큰 검사를 막은 harness 충돌이었다. 원기록을 보존하고 합성 fixture를 보완했으며 실제 `ModelClient.generate`/socket 차단으로 옮겼다. 해당 72개 재검사는 통과했다. 국소 missing 요약의 누락 본문 유실은 별도 재현 후 수정했다.

최종 통합 검사는 25개 파일 **474개 통과**, 331.62초다. `FINAL_INTEGRATION_TESTS.json/.log`에 실제 모델 backend 0/네트워크 연결 0과 실행 코드 SHA-256을 기록했다. 최종 커밋 전 현재 코드가 이 검사·실제 과거 응답 재생의 실행 해시와 일치함을 확인했다.

### 과거 실제 응답 재생과 데이터 보존

고정된 baseline R2와 참조 입력 R2의 **과거 실제 응답** 두 종류를 새 복사 DB에서 소비했다. 고정 E/적용성과 국소 결과를 실제 assess/save/GET/completion/repair 소비 경계에 주입했다. 새 G 판정이나 전체 후보의 새 의미 검증을 실행한 결과는 아니다.

- 새 run: `b8de48640d5941ffa5dcd9d505cbfa91`, `3a325a1406944825868d593e49e33f23`.
- 원응답의 represented+명시 잔여 3개와 근거 없는 전제 변경을 보존·차단했다. 필요한 3개 의미는 True를 유지하지만 과거 응답에 하위 내용/표현 위치가 없으므로 `unknown`이다. 임의의 새 정답을 채우지 않았고 완료 상태는 `partial`이다.
- 원본 run `5689dfa06cfd47f6a0757b44e4fa7618`의 지식 199개, 교정 bundle 1개 안의 changes 2개, 과거 unit 141개, assessment 14개, 상속 metrics `llm_calls=2`를 그대로 보존했다. 이 metrics의 2는 이번 새 호출이 아니다.
- 적격 156/차단 43이 전후 동일하며, 정상 형제·저장 교정·raw·원문·과거 assessment·승인/스냅샷/knowledge_state가 유지됐다. repair는 새 proposal dispatch 전에 멈췄다.
- 보호 대상 1,053개 파일의 해시 변화 0. 새 모델/네트워크/JSON 판정 dispatch는 모두 0이다. 결과·실행 코드 해시는 `replay/RESULT_REPORT.json`, 보호 원장은 `replay/FINAL_PRESERVATION.json`에 있다.
- 과거 저장 실행의 실제 GET 전체와 14개 assessment의 completion 재계산이 원계약과 동일하다. `LEGACY_API_READ.json`에 별도 기록했으며 새 계약 필드를 과거 저장 응답에 소급 주입하지 않았다.

이 199개 DB와 과거 `retail_enabled_execution_20261024`의 196개/스냅샷44 검증은 별도 계보다. 후자의 기존 검색·QA 성과를 이번 새 검수의 성과로 합산하지 않는다.

### 화면

원본 공유 node_modules에 쓰지 않고 이 작업트리에서 기존 main lock으로 독립 설치했다. 프런트 렌더/편집 11개, 타입 검사, 해당 컴포넌트 lint가 통과했다. 실제 `KnowledgeBusiness`를 임시 Next 화면에서 열어 True=해당, False=해당하지 않음, null=판단 불가를 함께 확인했다. `FRONTEND_UI.png`/`FRONTEND_UI_STATE.txt`/`FRONTEND_RESULT.json`은 합성 표시 계약의 증거이며 실제 업무 판정·승인 화면의 증거가 아니다. 임시 route와 검증 서버는 정리했다.

## 실행 한계와 다음 작업

새 추출·임베딩·R·QA·G·repair 모델 호출은 **0회**다. 과거 닫힌 계보는 configuration 7 / 6/6 / remaining 0 / no_reset=true를 유지한다. 모델 프롬프트·스키마의 새 하위 내용 의미 판단 성능, M03 개선, 검색·질문 품질 향상은 확인하지 않았다.

후속 native 검증에는 별도 승인이 필요하다. 승인되면 최신 모델/설정/토큰 계수 계약과 실제 입력 수용량을 먼저 확인한다. 새 하위 내용 적용성 1회 + 고정 후보 R 1회, 총 2회가 첫 의미 대조의 최소 계획이다. 전체 M03·G·repair 완료 검증은 포함하지 않는다. 입력/출력 한도와 retry 0을 실행 전에 고정한다. 스키마/소유 범위/원문 주소/실제 본문 바인딩 실패, represented+잔여 모순, 근거 없는 AND나 조건·예외·기간 손실 시 중단한다. 닫힌 계보를 자동 초기화하거나 기존 승인을 재사용하지 않는다.

현재 코드 검토·PR 생성에 추가 사용자 결정은 필요하지 않다. main 병합·배포·승인 지식 전환과 새 native 실행은 수행하지 않는다.
