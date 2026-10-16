# 출처·조건 보존 F0~F4 선행 작업 결과 — 2026-10-16

**확정 범위: F1 + 검증된 5열 opt-in F3 + 특정 부채표 F4-b를 통합하고 접점 7개를 검증했다. F2·F4-a는 제품 미채택이다.** 이번 최종 통합의 제품 추가 수정은 알려진 부채표 그래프 주석의 검증용 재구성뿐이다. 새 모델·embedding·원 DB 쓰기·전체 평가는 0회다. 아래 수치는 각 저장 보고서의 범위이며 전체 성공률·정확도·완료 ETA를 산출하지 않는다.

F3의 제한 채택 근거는 두 개념화 대상의 입력 감소와 역할 핵심 보존, 원문 노출 NAV01 한 과제의 회귀 없음이다. 검색·답변 향상이나 다른 자료의 일반화를 확인한 결과는 아니다.

## 1. 포함·제외와 실제 효과

| 단계 | 실제 확인 | 판정·현재 제품 포함 | 남은 한계 |
| --- | --- | --- | --- |
| F0 반복 비용 감사 | 저장된 3,622 target에서 메시지·schema·원문 대응표·저장 실행 계약이 정확히 같은 그룹 **0개**. 이름 중복은 459그룹/1,663 target이나 모두 저장 판단 입력이 다름 | 읽기 감사 완료. 이름만 같은 대상을 병합하지 않음 | 이름 중복 수를 안전한 병합 수나 예상 절감량으로 환산할 수 없음 |
| F1 판단 작업·대상 연결 분리 | 원래 ID·출처·상태를 유지하며 완결 결과의 실행 계약을 확인해 work/binding 연결. 명시 donor 재연결 사례에서 신규 모델 호출 **0회** | **채택·통합됨** | 현재 corpus에서 정확 입력 중복이 없어 대규모 중복 호출 감소는 확인하지 못함. 과거 실행 설정이 불명확한 결과를 새 엄격 계약으로 소급 승인하지 않음 |
| F2 공통 원문 묶음 | 작은 3묶음/6 target에서 호출 6→3, 입력 17,412→14,842, 출력 125→226 | **제품 미채택** | 속도 개선 없음. 구체 태그 소실·역순 변동이 남고 111블록 묶음은 반복 출력 후 잘림. 입력 감소로 회귀를 상쇄하지 않음 |
| F3 원문 구조에 따른 문맥 구성 | 새 단독 생성 2회. 입력 19,844→9,970, 출력 26→34. 역할 핵심·출처 보존과 NAV01 후속 회귀 없음 | **5열 opt-in 제한 채택·통합됨** | 구체 선박 태그 일부 소실. 이 과제에서는 최종 검색·답변이 동일했으며 다른 조회/자료의 영향과 일반화는 미확정 |
| F4-a evidence-only 출력 참조 | 새 생성 2회. 출력 14,334→11,315지만 case42의 Tail 18개가 모두 Head 근거를 선택해 주소 오류 0→18 | **제품 미채택** | 전송 스키마·왕복 성공이 실제 생성의 근거 연결을 보장하지 못함. case16의 부분 효과만 별도 보존 |
| F4-b 표 구조 대응 | 특정 2단 머리글 부채표의 **2행·10필드**, 모델·embedding 0회로 저장·재조회·필드별 원문 연결. 기존 직접 HTML 131행을 포함한 기존 기록 보존 | **제한 채택·통합됨** | 사업전환 열 단위와 주석 적용은 unresolved. 두 행의 정형 전사가 업무 의미 승인·범용 표 처리·새 QA 품질을 뜻하지 않음 |

F1의 재사용 결과는 미검증이면 미검증 그대로다. `has_concept`는 승인된 `is_a`가 아니며, F4-b의 행·필드도 `unreviewed / unknown`을 유지한다. 출처 주소가 존재하거나 생성이 정상 종료됐다는 이유로 업무 의미를 승인하지 않았다.

## 2. 무엇을 통합했고 무엇을 보존했는가

통합 작업트리 `knowledge-reuse-integration`, 브랜치 `codex/knowledge-reuse-integration`에서 공통 기준 `68c796299a679e3b531a6d28db4733f841ab426f` 이후 다음 채택 커밋을 연결했다.

| 채택 원 커밋 | 통합에서의 대응 |
| --- | --- |
| F1 `1f391247c380528aee6ddd86a5f9226906b51bc2` | 같은 커밋을 기반으로 사용 |
| F4-b `2f1301eef352f42d2d4b42135eadb72514d49f80` | `e84673a8032b498f166388da3b4bca3f5e1f8fbf` |
| F3 `a0dfc506bdccc7929e2e100347c6bc08fdb61094` | `e4362cc6b6ad10f8a69d788707213616673f1048` |

F1+F4-b 최초 통합 `a0ed90532680cd8cdd5c5496b5a7ee1ad384aa95`에서는 채택 18파일이 원 커밋과 같았고 추가 제품 수정 없이 6개 접점 검사를 통과했다. 이는 당시 범위의 역사 기록으로 남긴다. 이후 F3를 단일 cherry-pick하고 아래 호환성만 수정했다. 원래 작업트리·F3 frozen 실행·기각 F2/F4-a의 코드·raw·패치·DB는 보존한다.

### 최종 통합의 최소 수정과 검증

정상 부채표 부모+완결 entity child가 조회에서 거부되는 회귀를 수정 전 작은 검사로 재현했다. F4-b가 저장 그래프에 붙인 `construction_method`·필드별 evidence가 F3의 맨 그래프 재계산에는 없었기 때문이다. 통합 브랜치의 `concept_read_view`에서 기존 `annotate_graph`로 검증용 그래프를 동일하게 재구성했다. fingerprint·child·버전·상태 검사를 삭제하거나 모르는 annotation을 무시하지 않았다. 원래 F3 브랜치는 수정하지 않았다.

최종 **7개 검사 통과**: 정상 부채표 부모+완결 child 허용 1건, 부모 raw/필드 근거 변경 거부 2건, 부채표 legacy 개체의 opt-in 문맥 유지 1건, 검증된 5열 선택 1건, 기본/명시 child 조회 2건이다. 다른 target·원문·미승인 상태·저장 부모/child·행/필드 그래프 근거도 보존했다. 수정 직후 검사에서 API가 계산해 붙이는 counts와 DB payload를 혼동한 fixture 비교를 바로잡았고 추가 제품 수정은 없었다.

독립 F1 46개·F4-b 72개·F3 검사 기록은 보존했으며 전체를 재실행하지 않았다. 이번 검사는 로컬 stub·pytest 임시 DB만 사용했다. 최종 커밋·원격 SHA·clean과 재현 diff는 [최종 통합 인계 기록](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/f1_f3_f4b_integration_v1/final_handoff.json)에 남긴다. 검사 통과를 모델 의미 품질이나 실제 검색 개선으로 합산하지 않는다.

## 3. 비용 수치가 뜻하는 범위

| 비교 범위 | 입력 토큰 기존→변경 | 출력 토큰 기존→변경 | 시간·비용 해석 |
| --- | --- | --- | --- |
| F2 작은 3묶음 | 17,412→14,842 | 125→226 | 요청 elapsed 합계 174.198588→221.062403초. 호출·입력 감소의 부분 효과이며 속도 개선은 확인하지 못함 |
| F3 고정 두 대상 단독 생성 | 19,844→9,970 | 26→34 | 입력 -49.76%. 요청 elapsed 149.870276→80.803863초는 다른 시점의 저장 대조군과의 관측. 첫 F3 cold/둘째 warm, 일반 속도 인과를 확정하지 않음 |
| F4-a 고정 두 추출 사례 | 4,471→4,665 | 14,334→11,315 | 입력 포함 18,805→15,980(-15.02%)이나 중대한 주소 회귀로 **동일 의미 효율 향상으로 인정하지 않음** |
| F4-b 두 행 직접 저장 | — (모델 없음) | — (모델 없음) | 실제 모델 호출 0회. 별도 LLM 대조군의 절감량을 측정한 것은 아님 |

F2의 이미 지불한 실패·분할·역순 비용도 보존했다. v2 11회, v3 정순 추가 5회, 역순 1회를 합한 **17호출 / 입력 102,109 / 출력 1,795 / 요청 elapsed 1,075.188884초**다. 위 작은 비교표·재사용 대조군과 겹치므로 이를 다시 더하지 않는다. 큰 묶음의 실패를 제외한 값으로 전체 성능을 보고하지 않았다.

F1 명시 donor 재연결은 신규 모델 0회지만 내부 처리 0.065437초와 전체 서비스 12.009465초를 구분했다. 조회·계획·복사의 기여는 미측정이며 즉시 응답이나 일반적인 속도 개선을 뜻하지 않는다.

F4-a는 절전·복귀가 확인됐다. 두 client elapsed 합계는 1,953.920935초, 드라이버 벽시계 이동은 약 7시간 27분이며 둘 다 순수 연산 시간으로 쓰지 않는다. 과거 engine version 불명과 provider 세부 duration 불일치도 남아 **속도 효과는 판정 불가**다. 다른 단계의 시간과 합쳐 전체 구축 ETA를 계산하지 않는다.

### 이번 비교창의 새 LLM 호출 비용

| 종료 원장 범위 | 새 LLM 호출 | 입력 토큰 | 출력 토큰 |
| --- | ---: | ---: | ---: |
| F2 종료 원장: 실패·분할·역순 포함 | 17 | 102,109 | 1,795 |
| F4-a evidence-only 두 추출 | 2 | 4,665 | 11,315 |
| F3 두 대상 개념 생성 | 2 | 9,970 | 34 |
| NAV01 후속 v3의 필터·답변 | 4 | 18,876 | 923 |
| **범위를 대조해 검산한 잠정 합계** | **25** | **135,620** | **14,067** |

이는 위 네 종료 원장의 새 물리적 LLM 호출만 합한 값이다. 입력은 cache 토큰을 포함하는 provider 보고 수이며 순수 연산량이 아니다. 프로젝트 전체 이력 비용이 아니며, 과거 기준선 재사용·F1 모델 0 재연결·검사 stub·embedding을 더하지 않았다. F2/F3 생성 보고서의 중간 누적 19호출은 이 합계와 겹치므로 별도 재합산하지 않는다.

후속 소비 준비의 v1은 필수 파일 누락으로 LLM·embedding 0회였고, v2는 LLM 0회지만 중복 encoding 2회·178.443879초를 이미 지불했다. 최종 v3는 embedding 호출 경계 5회 중 신규 encoding 4회·저장 vector 복원 1회이며 이를 LLM 호출로 세지 않는다. 실패/계측 불완전 시도의 비용과 frozen 기록을 삭제하지 않았다.

## 4. 의미 보존·회귀와 F3 후속 결과

### F2·F4-a에서 비용과 별개로 기각한 이유

F2는 역할 핵심이 남은 작은 쌍이 있어도 제조현장스마트화자금의 구체 `스마트공장 지원금` 태그 소실, 역순 변동, 긴 묶음의 반복·잘림과 검색 영향 미확인이 남았다. 작은 묶음의 입력 감소를 전체 target 적용 근거로 넓히지 않았다.

F4-a case42는 raw 관계 18개·대상 관계 14개·운송 관계 7개와 제한 문구를 보존했다. 그러나 Tail의 올바른 인용을 registry 1번에 적고도 Scope/meaning/participant에서 Head의 0번만 선택했다. 미선택 인용이 registry나 복사 원문에 있다는 사실은 선택한 주장 근거 보존이 아니다. 변환기가 이 선택을 자동으로 고치지 않았고 제품 주소 검사가 오류 18건을 남겼다.

case16은 2claim·5meaning·16participant에서 환경 지속 가능→스마트팜→수직농법과 두 코드·명칭 대응을 유지한 부분 관찰이다. 입력 포함 토큰은 5,104→4,215(-17.42%)였다. 코드/업종명 레이블의 conditions 필드 값 변화도 보고했으며 생성 필드 전체 동등을 주장하지 않았다. 이 한 건으로 F4-a를 제품에 부분 활성화하지 않았다.

### F3: 생성 두 건과 후속 조회를 구분

F3는 검증된 기존 `테마/분야/품목명/분류코드/업종명` 5열 profile만 opt-in이다. 두 대상 모두 111→17블록이었으며 단순 삭제가 아니라 누락된 같은 품목의 셀·현장 확인 주석을 추가하고 다른 품목 행을 제외했다. 대상·이웃·미검증 Scope는 유지했다. 부채표 등 미지원 구조는 원래 문맥을 유지한다.

Digital 선박의 품목·제품·기술 역할과 무선 통신장비 제조업의 업종·제조 역할 핵심을 보존했다. 다만 기존 `디지털 선박/스마트 선박` 태그가 새 목록에 없어 구체성·검색 영향은 미확정이다. 현장 확인 주석이 실제 입력에 포함됐다는 사실만으로 답변이 그 주석을 올바르게 적용한다고 보장하지 않는다.

후속 NAV01은 같은 질문에서 기존 단독 개념 child와 F3 child를 명시 선택해 조회·답변을 대조했다. `concept_run_id`는 같은 source parent·graph·버전의 완결한 단독 child 하나를 임시 읽기 view에 연결한다. 부모·snapshot·승인 상태를 덮어쓰지 않고 개념은 검색 보조로만 사용한다.

| 후속 확인 항목 | 확인 결과 |
| --- | --- |
| 기존 단독 / F3 실행 | `0c18f0110ecf4cb7b0a89362213faadb` / `2a4414c87b6f4de4bae76f13c5bf23ea` 모두 완료. 두 실제 graph를 사용했고 fallback 없음 |
| 최종 조회·답변·인용 | 서로 다른 has_concept 간선을 선택했지만 최종 retrieval 12개·source_context 33개·답변·인용은 동일. 3개 코드/업종명과 현장 확인 주석이 원문에 대응함 |
| 원문 구간 확보 | 양쪽 모두 사전 고정 필수 7구간 중 직접 검색 **3/7**, 기존 표 문맥 보충 후 최종 모델 입력 **7/7**·인용 지원 **7/7** |
| 후속 모델 비용 | v3 실제 4호출·입력 18,876·출력 923·client request elapsed 합계 122.170686초. 신규 encoding 4회·저장 vector 복원 1회는 별도 |
| 구체 선박 태그 소실의 조회 영향 | 이 NAV01에서는 최종 결과 변화 없음. 다른 질문·자료의 영향은 미확정이며 자율 근거 검색 우위는 확인하지 못함 |
| F3 최종 채택 범위 | 두 개념화 대상의 입력 감소와 이 원문 노출 NAV01의 회귀 없음에 근거한 **검증된 5열 profile opt-in 제한 채택** |
| F3 채택·통합 | 원 커밋 `a0dfc506`→통합 `e4362cc6`, 추가 호환성 수정·최종 7개 접점 검사 완료. 정확한 최종 HEAD는 인계 기록 참조 |

필수 7구간은 원문 버전 `86a31d6b511a46f195963ef5ee52cd96`, parse `aa11c25ea5ba4c7c8e48ed186d4db851`의 표 행 610~612 코드·업종 셀 6개와 현장 확인 주석 1개다. 주소 보고서에서 block ID·구간·실제 원문·locator를 확인했다.

| 원문 위치 | block_order | 직접 검색(양쪽) | 최종 입력·인용 지원(양쪽) |
| --- | ---: | --- | --- |
| row610/c3: 26410 | 2322 | 아니오 | 포함 |
| row610/c4: 유선 통신장비 제조업 | 2323 | 아니오 | 포함 |
| row611/c3: 26429 | 2324 | 포함 | 포함 |
| row611/c4: 기타 무선 통신장비 제조업 | 2325 | 아니오 | 포함 |
| row612/c3: 27211 | 2326 | 포함 | 포함 |
| row612/c4: 레이더·항행용 무선 기기·측량 기구 제조업 | 2327 | 아니오 | 포함 |
| 현장 확인 후 판단 주석 | 3000 | 포함 | 포함 |

따라서 기존 표 문맥 보충이 없던 직접 검색만으로 7구간을 모두 찾았다는 결과가 아니다. 7/7도 이 사전 고정 원문 구간의 커버리지이며 전체 자료 정확도나 일반 검색 성공률이 아니다. `answered` 역시 응답 형식·제공 근거 참조 상태다. 이 한 원문 노출 과제의 동일 답변을 검색·답변 향상으로 세지 않는다.

후속 답변의 client elapsed는 기존 60.099814초·F3 21.722931초였으나, 양쪽의 답변 입력은 동일한 6,994토큰이고 F3에서는 그중 6,990토큰이 provider cache로 재사용됐다. 이 시간 차이는 F3 문맥 선택의 속도 개선 근거가 아니다. 확정된 것은 명시 child 교체가 제품 조회 경로에 연결됐고 이 과제에서 회귀가 없었다는 범위다.

## 5. 중단 상태·미구현과 남은 병목

장기 개념화 run `ee09f60fe2344d9c955769eed38a85a8`은 사용자 중단을 유지한다. 보존 snapshot은 3,622 target 중 응답 완료 922(기존 재사용 174+신규 748), 취소 1, 미시도 2,699다. 완료 922는 미승인 결과이며 의미 검증 완료가 아니다. 직렬화의 `cancel_requested`를 실제 실행 중이나 자동 재개 권한으로 해석하지 않는다. 취소 토큰의 미확인은 0이 아니다.

| 장기 기능 | 구현 상태 |
| --- | --- |
| A의 최소 경계 | F1의 정확한 완결 판단 재사용·출처별 binding은 구현·채택 |
| A의 넓은 공유 | 다른 입력·출처 사이의 정의 적용 판단 공유는 미구현. 같은 이름·임베딩 유사도로 공유하지 않음 |
| B 기업별 용어·공통 개념 대응 | 기업별 범위·정의의 대응 기능은 미구현. 지역 개체·주장을 자동 병합하지 않음 |
| C 부분 재구축 | F1 입력 의존성 기록은 기반 자료이나, 원문 변경 영향·부분 갱신 엔진은 미구현 |

남은 병목은 정확 재사용만으로 없앨 수 없는 서로 다른 판단 입력의 원문 반복, 긴 묶음의 생성 반복·간섭, 출력 참조 선택 오류, 표 주석·단위의 실제 업무 적용 미확정, **다른 질문·자료의 활용과 구체 태그 소실 영향 미확인**이다. NAV01까지의 소비 연결은 확인했으나 기업 전체 운영·다른 자료로 일반화하지 않는다.

관계 embedding의 반복 비용도 후속 우선순위 후보로 남았다. 관계 cache key가 전체 edge 집합에 의존하므로 개념 태그 5개가 바뀐 두 arm에서 각각 7,998관계 인덱스를 새로 계산했다. 이는 현재 코드와 encoding 기록으로 확인한 구조적 반복이며, 이번 통합에서 cache 방식이나 효율 프레임워크를 추가 수정하지 않았다.

기존 실패 계보와 최대 6회 규칙은 유지한다. F4-a evidence-only 변경은 새 변경 1개/생성 2회이며 각 사례의 과거 compact 보존 조정 1회에 새 1회를 더했다. 용량 계보는 별도로 보존하고, 확인 불가 의미·주소 이력을 0으로 바꾸거나 새 6회 예산을 부여하지 않았다. 위 네 종료 원장의 25호출 밖에 있는 장기 구축·과거 모델 실험까지 이번 비용으로 합산하지 않았다.

이번 통합 범위의 구현·검증은 완료했다. 후속 우선순위는 위 제한과 비용을 근거로 별도 결정하며 자동으로 새 모델·전체 평가·효율 리팩터링을 시작하지 않는다. 새 PR·PR 병합·이슈 종료·배포나 장기 실행 재개를 수행하지 않는다. 현재 사용자 결정이 필요한 사항 없음.

## 6. 확인한 근거와 기각 실험 보존 위치

- F0: [읽기 감사 보고](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f0_v1/f0_report.md), [집계·경계 JSON](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f0_v1/f0_summary.json). 현재 corpus의 직접 HTML 131행 수는 이 보존 집계 범위다.
- F1·F2: [채택 계약과 종료 비용 기록](source_scoped_exact_reuse_f1_20261016.md), [F1 인계 receipt](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f1_only_integration_v1/completion_receipt.json).
- 기각 F2: [기존 dirty 상태·비용·보존 hash](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f1_f2_closed_20261016_v1/closure_receipt.json), [재현 패치](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f1_f2_closed_20261016_v1/reproduction.patch). 원래 `source-scoped-knowledge-reuse` 작업트리와 frozen DB/raw는 제품 통합과 분리한다.
- F3: [채택 계약·후속 결과·비용](source_context_f3_20261016.md), [생성 2건 원문 검토](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f3_v1/runtime_v1/result_review_v1/result_review.md), [provider 수치·시간·한계](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f3_v1/runtime_v1/result_review_v1/result_review.json).
- F3 후속: [NAV01 실제 원문 주소·두 arm 검토](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f3_v1/consumer_v1/query_execution_v3/review_v1/review.json), [4호출·encoding·원본 보존 종료 기록](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f3_v1/consumer_v1/query_execution_v3/execution/execution_finished.json), [기존 입력 답변](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f3_v1/consumer_v1/query_execution_v3/execution/results/existing_single.json), [F3 답변](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f3_v1/consumer_v1/query_execution_v3/execution/results/F3_context.json). 실패/비용이 남은 [v1 종료 기록](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f3_v1/consumer_v1/query_execution_v1/execution/execution_finished.json)·[v2 종료 기록](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f3_v1/consumer_v1/query_execution_v2/execution/execution_finished.json)도 유지한다.
- 기각 F4-a: [최종 원문 검토·미채택](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/f4a_evidence_wire_v1/native_v1/source_review_v1.json), [시계·절전 근거](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/f4a_evidence_wire_v1/native_v1/clock_analysis.json), [동결 코드·복사 DB·패치 인계](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/f4a_evidence_wire_v1/native_delivery.json), [전체 보존 패치](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/f4a_evidence_wire_v1/product_change_after_native.patch).
- F4-b: [지원 구조·원문·제품 API 검증](html_debt_ratio_rows_20261016.md), [모델 0·2행·10필드·기존 기록 보존](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/f4b_debt_rows_v1/actual-result.json).
- 통합: [최초 F1+F4-b 범위·6개 접점 검사](reuse_integration_f1_f4b_20261016.md), [당시 커밋·원격 SHA](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/f1_f4b_integration_v1/handoff.json), [이번 F3 추가 전 거부 재현](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/f1_f3_f4b_integration_v1/before_guard.xml), [최종 7개 검사](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/f1_f3_f4b_integration_v1/after_guard_v2.xml).

위 로컬 링크는 이 장비의 보존 근거다. 원시 DB·대형 응답을 문서 저장소에 새로 복사하지 않았고, 과거 보고서의 당시 pending/이력 값을 수정해 최신 결과처럼 만들지 않았다. 이 중앙 문서가 현재 포함/제외와 후속 결과를 구분한다.
