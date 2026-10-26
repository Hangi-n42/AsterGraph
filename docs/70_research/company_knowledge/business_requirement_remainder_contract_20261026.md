# 공개 요구 적용성과 부분 누락 보강 계약 — 2026-10-26

## 진행 이유와 범위

M03 감사에서 원문 블록 읽기 범위가 질문 필수성으로 승격되고, 근거 있는 부분 누락도 잔여 필드가 비어 있으면 보강 대상으로 연결되지 않는 두 경계를 확인했다.
사용자가 승인한 계약 수정·무모델 검증·커밋·push만 수행했다. 관련 범위는 기존 [#616](https://github.com/Hangi-n42/AsterGraph/issues/616), [#620](https://github.com/Hangi-n42/AsterGraph/issues/620)이다.

기준은 `2710660dcd1619748922c59d82d83f668573ad6e`이고 당시 원격 main은 `fab7e1fe87960659b2ba386c827f47078d5c2dac`였다.
`22ae39dd`의 공개 범위, `49f04cd4`의 부분 누락 보강, `373cc5b0`의 QA 최종 기여 판정, `5089c6c2`의 저장 블록 범위 확장을 재사용했다.
별도 `codex/requirement-remainder-contract` 브랜치와 worktree를 사용했다.
이전 owner 제한·교정 입력 압축 등 선행 변경을 재구현하지 않았다.

## 변경 계약

- 읽은 블록과 그 블록에서 연결한 의미는 검수 범위로 남긴다. 그 목록을 질문 필수 목록으로 취급하지 않는다.
- 공개 요구에는 기존 `apply_requirement`와 `RequirementLink`를 재사용한다. 원문을 다시 추출하지 않고 원래 question/criterion의 항목별 적용성·직접 답변·필수 전제·참고를 기록한다.
- `source_checks.required_for_requirement`는 `true`/`false`/`null`이다. 구조화 적용성이 없거나 미확정이면 `null`이고, 참고로 낮춰 만족시키지 않는다. 필수 의미의 전제가 참고라는 모순도 미확정으로 남긴다.
- 완료·행동·교정·표 누락 보강·저장/조회가 같은 필수성 소비 함수를 사용한다. 완료 계약은 `required-meaning-completion-v3-read-application`이다. 구기록의 계약 표시는 바꾸지 않는다.
- 참고의 단순 partial/missing/unknown과 독립 후보의 오류는 기록·해당 후보 보류를 유지한다. 필수 의미·필수 전제·실제 답변 claim과 연결된 오류나 미확정, 정상 의미 보존 실패는 완료를 막는다.
- 공개 항목의 완료 증거는 항목별 실제 필수 의미와 R 기여 위치다. 성공한 E 블록 읽기는 후보 표현 완료가 아니다.
- 일반/QA 기여 출력의 `represented_content`, `missing_content`, `missing_evidence` 반환 계약을 공통화했다. 설명문에서 잔여 내용을 만들어 채우지 않는다.
- 필수·미확정 partial과 QA가 명시한 최종 판정은 실제 종합 행을 요구한다. 정확한 잔여·전체 후보 대조·기여 후보의 자기 원문 지지가 있어야 `recover`다. 부족하면 해당 의미의 이유 있는 `hold`다.
- 참고 partial의 잔여 필드 부족도 개별 hold다. 공통 ID·중복·귀속·원문 주소 검사를 먼저 통과해야 하며, 잘못된 새 출력은 검증 성공으로 인정하지 않는다.
- 적용성은 실제 메시지·스키마·참조·고정 요구 revision·설정·모델 identity와 완료 응답/결정 지문이 같을 때만 재사용한다. 주소/버전/인용/상태 검사는 완화하지 않았다.
- 화면은 필수성 `null`을 “판단 불가”로 표시한다. 사용·승인 소비에서 미확정을 참고로 누락시키지 않는다.

## 검사와 한계

합성 fixture는 계약 경계 검사이며 실제 M03의 의미 정답이 아니다.
같은 블록에 필수·참고·미확정을 섞은 뒤 실제 `assess` → 행동 → 서비스 저장 → API GET → 완료/교정 선별을 확인했다.
정확한 부분 누락은 기존 ID를 `contributing_claim_ids`로 보존하고 실제 교정 입력의 잔여 내용·인용·재사용 후보로 전달됐다.
빈 필드·없는 인용·미확정 적용성은 hold로 남겼다. 일반/QA의 공통 계약, 잘못된 상태·주소·ID, 공유 claim/전제와 독립 후보 오류도 검사했다.

핵심 범위 123개와 QA/공통 주소 경계 11개가 통과했다.
확대한 최종 회귀는 421개 중 420개가 통과했고, 한 source-scope fixture에서 후보 두 개 중 하나의 검수 기록을 빠뜨려 대체 경로의 2항목 스키마에 기존 4과제 응답을 반환했다.
생산 검사를 유지하고 fixture가 실제 검수 후보 둘과 외부 후보를 모두 제공하도록 정정했다. 실패 경계와 공유 fixture 파일의 **39개가 통과**했으며 `CANDIDATE_FIXTURE_TESTS.xml`에 기록했다.
전체 7분 검사를 반복 실행한 것으로 집계하지 않는다. 123/11/39개를 합산해 독립 검사 수로 주장하지 않으며 최초 실패 로그도 보존했다.

변경 컴포넌트와 그 import 범위의 TypeScript 검사, 해당 파일 ESLint, `git diff --check`를 통과했다.
전체 프런트 TypeScript 검사는 설치된 공용 의존성에 `cytoscape`가 없어 `KnowledgeGraph.tsx`에서 실패했다. 변경 컴포넌트 검사와 구분하며 패키지 설치·인접 코드 변경으로 범위를 늘리지 않았다.
서버를 시작/재시작하지 않았고 변경 화면의 실제 브라우저 검증은 수행하지 않았다.

검사 중 소켓 접속을 차단했다. 실제 저장 재생에는 소켓과 `ModelClient.generate` 차단도 적용했다.
새 native·임베딩·선택·PPR·QA·추출·교정·검수 호출은 0회다.

## 실제 저장 자료와 복사 DB

산출물 루트:
`/Users/hyeongi/.codex/artifacts/retail-knowledge-pilot-20261018/retail_requirement_remainder_contract_20261026_v1`

I DB는 `mode=ro&immutable=1`, `PRAGMA query_only=ON`으로 열어 SQLite backup으로 복사했다.
실제 `business_run.assess`의 행동/완료 소비와 서비스 저장 → `/knowledge/runs/{id}` GET → 요구 current_assessment 재조회를 검증했다.
이때 새로운 적용성·R 응답은 실행하지 않았다. 기존 R 판정을 명시적인 `historical_consumer_replay_only` 어댑터로 소비했으며 강화 계약의 새 native 성공으로 집계하지 않는다.

| 항목 | 결과 |
|---|---|
| 복사 DB | 산출물 루트의 `service-final/knowledge.db` |
| 새 run | `06b6e849e1974554a064bb8f652d45ed` |
| 새 assessment | `17feae580ee846ee95049b4df1ced974` |
| 원래 I parent run | `375d96f925d14fdd94f48c092ec9b5f5` |
| M03 | `partial` |
| 필수성 미확정 | 기존 자료에 구조화 적용성이 없는 10개 의미 |
| 행동 | maintain 72 / hold 2 / recover 0 / correct 0 |
| 실제 교정 선별 | `False` |
| 정상 객체 | 199개 전체 불변; 기존 교정 2개 포함 |
| 보존 | blocks/graph/concepts/candidate_reviews, parent run, decisions/snapshots/knowledge_state 불변 |

구 I raw는 송신용 alias 스키마로 검증했다. `e9` 같은 짧은 원문 참조는 유효하며, 새 필수 문자열 두 필드가 없다는 오류만 남는다.
기본 EvidenceQuote와 alias의 표현 단계 차이를 원문 주소 결함으로 해석하지 않는다. 빈 잔여 근거를 생성하지 않았다.
F/G/I 자료의 이전 표현·부족 정보는 `HISTORICAL_CONSUMER_READINESS.json`에 별도로 남겼다.

원본 DB 8개, F/G/H/I 산출물, 동결 worktree의 app 파일을 포함한 보호 파일 760개의 해시가 같았다.
`configuration=7`, `round=6/6`, `remaining=0`, `no_reset=true`를 유지하며 이번 수정 승인을 별도 계보로 기록했다.
새 승인·snapshot·배포·이슈 종료는 없다.

## M03에서 해결한 것과 남은 것

해결한 것은 범위/필수성의 소비 결함과 일반 partial의 실행 계약이다.
상품·레시피 핵심 후보는 전달됐고, “등심은 담백해 어떤 요리에도 무난”의 독립 claim 누락은 현재도 남는다.
그 누락이 원래 질문의 필수 전제인지는 이번 무모델 작업에서 확정하지 않았다.
m6 조리법의 기존 미저장도 새로 해결하지 않았다. 정상 객체 보존·스키마·서비스 통과를 실제 의미 개선이나 M03 완료로 계산하지 않는다.

## 후속 최소 호출 명세 — 준비만 완료

첫 적용성 요청은 `FIRST_APPLICATION_REQUEST.json`에 고정했다. 원문 34블록과 기존 10의미 × 원래 3항목, 총 30조합을 한 요청으로 처리한다.
보수 예산은 **38,569 / 49,152**지만 정확 prompt 계수와 현재 runtime/renderer 확인을 하지 않았으므로 **native gate 통과는 아니다**.
이 예산은 `utf8_bytes/2 + output + 1000`이며 정확 토큰 관측값이 아니다. 실제 실행 전 별도 승인과 정확 용량 확인이 필요하다.

| 단계 | 새 호출 수와 조건 |
|---|---|
| 적용성 | 1개 요청 준비. 결과가 없는 상태에서 m3 필수성을 미리 정하지 않음 |
| 원문 재추출·선택·임베딩·PPR·QA | 0 |
| 자기 원문 | 기존 후보 풀 64/64 완료 receipt 확인. 원문/후보/요청이 같을 때만 재사용 |
| 새 R | 적용성 결과와 실제 bounded packet 예산 뒤 산정. 과거 5묶음을 새 호출 수로 대입하지 않음 |
| join | 필요한 R 완료 뒤 1개. 변경 요청에는 과거 응답을 새 성공으로 재사용하지 않음 |
| 교정 | 실행 가능한 대상이 없으면 0, 있으면 bounded 요구 교정 1개 |
| 참여자 선택 | 0을 유지. 문자 위치가 모호하면 차단 |
| 저장·GET | 모델 호출 0 |
| 교정 후 자기 원문·R | 실제 새/변경 후보와 공유 의미 packet 수를 산정. 정상 불변 후보는 정확 재사용 |
| 교정 후 join | 교정을 적용하고 재검수가 필요한 경우 1개 |

미확정 적용성, 원문/잔여 근거 부족, 후보 전체 대조 실패, 주소/참조/설정 불일치, 용량 초과 시 해당 단계에서 중단한다.
재시도·문맥 상향·기존 실패 횟수 초기화·없는 필드 보충은 계획에 없다.
이번 승인 범위의 구현·무모델 검증을 완료한 뒤 커밋·push하고 원격 SHA를 확인한다. 현재 사용자 결정이 필요한 사항 없음.
