# 국소 검토 입력 공통화와 필수 판정 반환 완결성

## 진행 이유와 범위

현재 제품에는 이미 질문의 필수 부분을 별도로 검수하는 지시가 있다. 과거 B2 평가 입력이 그 제품 경로와 달랐고, `requirement_checks`가 생략돼도 기존 선택적 출력 모델을 통과했다. 기존 코드는 누락을 unknown으로 막았지만, 반환 누락 자체는 완료된 모델 응답과 구별되지 않았다.

따라서 기존 지시/packet 생성만 공통 helper로 이동하고, 유효한 필수 대상이 있는 새 국소 요청에 반환 완결성 계약을 추가했다. 원문·후보·의미 판정 기준을 다시 작성하거나 새 검수 단계를 만들지 않았다. 기준 커밋은 `8c5bcadc5769b14abd88cd8b98c61e4003c43fbb`, 작업 브랜치는 `codex/review-request-completeness`다. 기존 PR #674 위의 표현 참조 변경을 포함하는 별도 후속 브랜치이며 main 배포가 아니다.

## 변경

- `business_review.local_review_inputs`를 실제 `_represent`와 고정 입력 평가가 공유한다. full source로 범위를 계산하고 기존 instruction, QA, direct-row, previous_meanings, repair context와 원문 블록 선택을 보존한다.
- `business_run.json_request`는 유효하고 비어 있지 않은 `required_content_targets`가 있는 국소 검토 요청에만 동적 스키마를 적용한다. 목록 필수, 대상 수와 같은 행 수, 허용 의미/범위 ID, 비어 있지 않은 이유를 요구한다. 실제 의미–범위 대응과 중복은 응답 소비 때 추가 검사한다.
- 누락·중복·잘못된 범위는 `required_review_validation`에 구분해 남긴다. 해당 새 unit은 `required_review_incomplete` 실패로 기록하지만, 정상 형제와 전체 의미 검토 결과는 반환한다. 오류 행은 기존 binder에서 unknown/unbound로 보류하며 누락된 의미 판정을 만들어 채우지 않는다.
- `unknown`과 이유를 모두 반환하면 구조적 완결성은 성립할 수 있다. 의미 충족이나 완료·교정 허용을 뜻하지 않는다. 전역 `ContributionReviewCheck`의 선택적 기본값과 과거 저장 응답은 바꾸지 않았다.

적용 경계: 현재 제품 builder는 required content/evidence/bound/current source version을 검증한 뒤 미확정 대상을 제외하므로 유효 형제의 계약은 유지된다. 알려진 과거의 불완전 target 형식은 새 계약을 활성화하지 않는다. 임의로 혼합·손상한 context를 직접 `json_request`에 넣는 별도 호출자는 이 사전검증과 동등하다고 검증하지 않았다.

## 요청 비교와 용량

두 묶음의 후보 7개씩/순서, 전달 블록 32개씩, full source 18개/선택 의미 10개, 필수 범위 ID, 원문 사실·조건·예외, 후보 raw/해석/미확정 상태를 보존했다. 모델은 기존 `qwen3.8:27b-q4_K_M`, context 49,152, output 8,192, safety 1,000으로 고정했다.

| 비교 | B1 | B2 |
|---|---:|---:|
| 이전 총 예산 | 48,447 | 44,307 |
| 현재 제품 경로 + 새 계약 총 예산 | 48,624 | 46,181 |
| 남은 여유 | 528 | 2,971 |
| 이전 context와 동일 | 예 | 아니오 |
| 이전 instruction과 동일 | 예 | 아니오 |

B2의 과거 입력에는 오래된 `requirement_link/requirement_applications`도 들어 있었다. 현재 builder는 원문 의미 10개의 적용 정보를 현재 상태로 전달한다. 적용 근거 binding은 11개에서 41개로 바뀌었으며, 의미/원문/표현 참조 map은 동일하다. 이전 compact source를 강제로 주입하지 않았다. 따라서 B2는 같은 의미 평가 조건의 재실행으로 볼 수 없다.

반환 완결성 지시와 스키마 때문에 **두 최종 요청 모두 이전 요청과 다르다**. 이전 응답의 exact-request cache 재사용은 불가하다. 아래 저장 재생은 응답 소비 계약 검증이며 새 모델 결과가 아니다.

## 검증 결과

- 관련 7개 테스트 파일: 208 passed, 133.78초. 이후 제품 builder 사전검증 경계 4개 추가; 해당 파일 21 passed, 2.41초. 총 고유 검사 212개가 통과했다.
- 기준 커밋의 실제 모듈과 새 모듈을 별도 프로세스로 실행했다. absent target, empty target, 합성 legacy partial target의 전체 요청 3건이 bytes까지 동일했다. 같은 새 코드에서 계약만 끈 비교와 별도 증거다.
- 새 복사 DB 실행 `17da9f177ae64212932f1f3e8b81c062`: 실제 `json_call` → 표현/근거 복원 → 기존 binder/summary → 서비스 저장 → GET 200, 조회 값 완전 일치.
- B1 저장 응답: 표현 참조 22개와 필수 3개 missing을 그대로 보존, 반환 구조 complete.
- B2 저장 응답: 표현 참조 29개와 기존 전체 의미 검토를 보존, 빠진 필수 3개는 `missing` 진단 및 `required_review_incomplete`; 소비 결과는 기존처럼 unknown. 과거 성공 unit 자체는 수정하지 않았다.
- 합성 partial/duplicate/scope collision/explicit unknown 4건: 정상 형제와 전체 의미 결과 보존. unknown 회복 요청 3개는 기존 hold 경로로 보류, 새 교정 dispatch 0회.
- 기존 34개 실행 payload와 나머지 17개 테이블 동일. 주장 199개, 교정 1묶음/변경 2개, 기존 unit 149개, 평가 14개, 기존 metrics `llm_calls=10`과 실패 이력 동일. 새 재생 unit 6개는 모델 생성과 분리했다.
- 보호 파일 1,688개 해시 변경 0개, 기존 서버 29개 PID/시작/명령 변경 0개, 다른 checkout 4개의 HEAD/변경 목록과 모델 점유 상태 동일.
- 새 모델 생성 0회, exact cache reuse 0회. 종전 6/6 및 추가 2/2 호출 한도 소진 상태는 유지했다.

검사 중 실패도 보존했다. 기존 expression fixture의 target 외 형제 설정, unknown fixture의 source_checks 누락, 합성 legacy case 공유 20개 검사에 대한 과도한 gate 적용을 수정했다. 선택 의미 10개를 필수 3개와 혼동한 재생 harness assertion 실패의 DB·로그는 `initial_replay/`에 남겼다. 보호 검사 최초 실패는 Git status 출력의 양끝 공백 처리 차이였으며 원본 파일 해시/서버 변경은 없었다.

## 근거와 다음 작업

로컬 근거 루트: `/Users/hyeongi/.codex/artifacts/retail-knowledge-pilot-20261018/retail_review_request_completeness_20261028_v1`

주요 파일: `REQUEST_COMPARISON.json`, `B2_INPUT_DIFF.json`, `LEGACY_REVISION_COMPARISON.json`, `FINAL_TESTS.txt`, `BUILDER_BOUNDARY_TESTS.txt`, `SERVICE_SAVE_GET.json`, 각 `*_RESULT.json`, `PRESERVATION_VERIFICATION.json`.

다음 의미 검증에는 현재 요청을 고정한 뒤 별도로 승인된 최대 2회 생성이 필요하다. B1 용량 여유는 528토큰이므로 입력이 달라지면 다시 계산해야 한다. 현재 승인 범위의 사용자 결정 사항은 없다. 새 PR·병합·배포·지식 승인·이슈 종료는 수행하지 않았다.

실제 새 요청을 모델이 완결되게 반환하는지, B2의 기존 전체 레시피 과장 판정이 개선되는지는 미검증이다. 저장 응답 재생과 형식 검사 통과를 의미 정확도 개선으로 보고하지 않는다.
