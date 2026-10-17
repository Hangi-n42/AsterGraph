# 조회 미분류 시간의 재분할 진단 — 2026-10-17

## 결론과 범위

기존 [#660](https://github.com/Hangi-n42/AsterGraph/issues/660)의 **구조적 병목 확인은 완료했으며 제품 속도 개선은 실행하지 않았다.** 제품 코드는 기준 `9f8e5a89275f74170b9425eef950418ee6d38c93` 그대로다. 진단과 기준선은 추가 계측·측정 시점이 달라 시간·메모리 차이를 개선/회귀나 인과 효과로 해석하지 않는다. 새 진단 cold/warm에서 기존 미분류에 해당하는 평균 2.029537초 중 상태 확인이 **1.939968초(95.59%)**, 나머지는 **0.089568초**였다. 이 비율은 새 진단 내부의 비율이며, 이전 미분류 평균 2.057407초의 정확한 비중으로 바꾸어 보고하지 않는다.

나머지 약 0.09초를 위해 구조를 확대하지 않았다. 단순 SQL 치환은 기존 오류/중복 키/단락 의미와 달랐고, 새 상태 column·원장·cache는 migration과 여러 쓰기 경로/트랜잭션 일관성까지 검토해야 한다. **이번 범위에서 안전성과 효과를 확인한 작은 제품 변경이 없다는 판단이며 최적화가 불가능하다는 결론은 아니다.**

## 진단 방법과 보존

반복 개발에 사용한 동일 NAV01/D01 snapshot·질문·모델 설정·저장 벡터/응답을 사용했다. `query_chunks_selection_v1/after_repeat1,after_repeat2` 네 조회의 제품 hash와 시작 DB hash를 재확인했다. 원 helper SHA256 `d10e2440c48c59a67c15ebfbeddaf1934b998b805fa7a2e104c53f7cfbee2b22`는 byte-identical하게 보존하고, 별도 진단 helper **`1f850622a2f5cc038bb1ed99ef5f5d6ea3589f0436ec21298c6784aadc7f8bd7`**를 만들었다. 원 Times·query·입력 대조·재생·저장 로직은 그대로이고 추가 clock 설치와 진단용 mode metadata만 달라졌음을 역변환 assert로 확인했다. 두 helper hash가 같다고 표시하지 않는다.

기존 주요 배타 구간은 유지했다. 상태 함수, 잔여 connection scope, 접근제한 확인, 요청/schema·copy·encode를 추가로 구분했다. 원 connection context manager에 그대로 위임해 반환·commit·rollback·예외를 유지했다. SQLite/DB/cursor/SQL 구현을 교체하거나 per-row SQL 계측을 추가하지 않았다. 기존 get/save 등의 중첩 구간은 잔여 scope에서 배타적으로 빠진다. 잔여 connection scope는 직접 SQL/fetch/decode·준비·commit이 섞인 범위이며 순수 SQL 엔진 시간이라고 부르지 않는다.

먼저 임시 DB에서 상태/terminal/missing/malformed/array/null/중복 status 키의 8개 결과·예외와 commit/rollback/원 예외 전파를 확인했다. 그 뒤 검사와 분리해 진단 cold/warm 한 쌍을 실행했다. 제품 수정이 없으므로 동일 helper 네 조회와 기존 전체 경계 125개를 다시 실행하지 않았다. 기존 16개 baseline 실패도 이번 범위 밖으로 미재실행했다. 진단 중 새 fixture 실패는 없으며 기존 최대6회 실패 계보를 유지한다.

## 미분류의 새 구성

| 추가 배타 구간 | cold(초) | warm(초) | 평균(초) |
| --- | ---: | ---: | ---: |
| 실행 상태 확인 `has_active_runs` | 1.886598 | 1.993339 | **1.939968** |
| 잔여 connection scope — 직접 SQL/fetch/준비/commit 혼합 | 0.022980 | 0.022177 | 0.022578 |
| 접근제한 확인 — import/SQL 등 포함 | 0.012708 | 0.000134 | 0.006421 |
| 요청/schema 생성 | 0.000622 | 0.000517 | 0.000569 |
| query 경계의 deepcopy | 0.000201 | 0.000197 | 0.000199 |
| query 경계의 encode | 0.000028 | 0.000030 | 0.000029 |
| 여전히 미세 분리하지 않은 Python/조립/정리 등 | 0.067926 | 0.051617 | 0.059771 |
| **기존 미분류에 해당하는 합계** | **1.991063** | **2.068010** | **2.029537** |

원시 배타 합계 오차는 두 query 모두 **0초**다. 위 합계와 기존 get·graph·source·replay·save 구간을 합치면 각 query 전체 시간과 일치한다. 같은 비용을 중복 합산하거나 누락한 시간이 없다. 다만 마지막 0.059771초의 세부 함수와 잔여 connection scope의 SQL/commit/객체 해제 비중은 더 나누지 않았다.

진단 전체 query는 cold **11.448944초**, warm **11.281058초**, 평균 **11.365001초**였다. 기존 동일 helper 네 조회 평균은 **11.491458초**다. 제품이 동일하고 추가 clock·측정 시점이 다르므로 이 차이는 **성능 개선으로 채택하지 않는다.** 진단 오버헤드의 정확한 크기도 따로 분리할 수 없다.

동일하게 초기화와 앞선 조회를 포함한 진단 process peak RSS는 cold **6,516,916,224 bytes**, warm **6,626,033,664 bytes**였다. 직전 기준선의 cold/warm 최대는 각각 6,541,148,160/6,649,233,408 bytes다. 제품 변경이 없는 다른 시점·진단 조건의 관측이므로 메모리 개선/회귀나 인과적 할당 차이로 해석하지 않는다. 동시 요청·OS 반환·실제 모델 로드 포함 메모리 상한은 미측정이다.

## 상태 판정에 남은 비용과 기각한 지름길

변경되지 않은 시작 DB는 **38행**, run payload 합계 **1,333,098,518 UTF-8 bytes**다. 이전 행수/크기 영수증과 현재 DB SHA256 `6dcba12174e892fa54c4666438cde09a126a75a5990e1d926ef6e5ab7738ca07`의 일치를 확인했다. 현재 상태는 별도 column이 아니라 이 큰 payload의 top-level 값이다. Python에 보내는 상태 결과는 작지만 SQLite가 원 JSON의 유효성과 최상위 키를 읽고 해석해야 한다. 이는 논리적 입력 크기이며 물리 디스크 I/O byte 수를 계측한 결과가 아니다.

같은 정상 원장을 read-only로 열어 각 부분만 독립 단발 측정했다. `json_valid`만 조회한 값은 **1.039104초**, `json_each/json_group_array`로 상태만 투영한 값은 **1.037079초**였다. 두 번째는 안전성 검증을 의도적으로 제외한 정상 자료 진단일 뿐 제품 후보가 아니다. 서로 다른 SQL/시점이므로 둘을 더해 전체 1.939968초로 환산하거나 정확한 지분으로 해석하지 않는다. 파일/페이지 cache·SQLite 내부 parse/할당·텍스트 처리 비용은 아직 분리하지 않았다.

작은 메모리 DB의 실제 관측으로 다음 지름길을 기각했다.

- `json_extract`만 사용하면 `{"status":"failed","status":"running"}`에서 첫 `failed`가 나왔다. 현재 제품은 마지막 `running`을 사용해 실행을 차단한다.
- 검증 없이 `json_each`만 사용하면 trailing comma가 있는 `{"status":"failed",}`를 정상 status로 받았다. 현재 제품은 기존 Python fallback의 `JSONDecodeError`를 유지한다.
- active 행 뒤에 손상 행이 있으면 단순 SQL 투영은 현재 행을 반환하기 전 prefetch에서 `OperationalError`가 났다. 현재 제품은 원래처럼 active에서 단락해 실행을 차단한다.

따라서 검증/마지막 중복 키/fallback/조회 순서를 잃는 치환을 속도 개선으로 채택하지 않았다. 상태 column·별도 원장/cache를 추가하려면 기존 데이터 이전, 시작/종료/취소/복구 등 여러 writer의 원자적 상태 갱신과 조회 일관성을 검토해야 한다. 새 JSON parser도 이 범위의 작은 변경이 아니다. 이 판단은 검토한 지름길의 기각이며 모든 SQL 대안이나 향후 설계의 불가능성을 증명하지 않는다.

## 결과 동등성과 다음 범위

진단 두 조회의 전체 saved run/result/모든 responses는 기준선과 **0 diff**이며 기존 DB 모든 행·다른 table도 동일했다. 조건·예외·출처/version/parse/span·순위·선택·QA messages/schema·답변·인용·저장 상태를 유지했다. 모델 요청과 ordered vector 입력이 정확히 일치할 때만 저장 자료를 복원했다. 제품 코드 hash는 전후와 기준선 모두 동일하다.

제외한 것은 기존 시간 7종(`run.started_at/finished_at`, `run.metrics.elapsed_s`, `run.graph_retrieval.elapsed_s/index_elapsed_s`, `run.units[*].started_at/finished_at`)과 새 query/request ID의 위치/stage 치환뿐이다. cache 제외는 0개이며 provider response의 과거 시간/parsed payload도 비교했다. helper hash 차이는 계측 변경 기록으로 명시했고 정규화 항목을 늘려 결과를 맞추지 않았다.

현재 성능 기준은 제품이 바뀌지 않은 직전 **11.491초**다. 남은 기존 배타 구간은 source **4.848초**, graph/index/rank **2.762초**, 미분류 **2.057초**, get 읽기 **1.581초**, save **0.232초**다. 이번 진단은 그 미분류의 주원인이 상태 판정이라는 점을 좁혔다. source 안의 chunks **2.609초는 포함시간**이며 여기에 다시 더하지 않는다.

이번 작업은 제품 patch 없이 진단 근거로 종료하며, 나머지 약 0.09초를 위해 기능/스키마를 확대하지 않는다. 후속 후보는 상태가 거대한 payload 안에만 있는 저장 구조를 분리할지 검토하는 것이다. 상태 전이·모든 writer·취소/동시성·기존 원장 migration·누락/손상 fallback을 함께 검증해야 하며 이번에 구현하거나 효과를 확정하지 않았다. 상태 cache로 바로 대체하는 계획도 아니다. 현재 사용자 결정이 필요한 사항 없음. 새 모델/embedding 호출·로드, 재추출/전체 평가/paused 구축 재개/새 PR·merge·배포는 0회다. 기존 #660 전체는 미완료로 open 유지한다.

원본/paused DB·407개 frozen 코드·기존 결과/실패/실험·원래 작업트리·기존 4개 서버를 보존했다. 새 DB/run/helper/원시 결과는 Git에 포함하지 않으며 기록 루트는 `/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_residual_partition_v1/`다.

- [진단 분할·합계·RSS](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_residual_partition_v1/diagnostic_summary.json), [helper 변경과 두 hash](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_residual_partition_v1/helper_changes.json), [위임/commit/rollback/오류 사전 확인](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_residual_partition_v1/instrumentation_preflight.json)
- [상태 부분별 read-only 관측](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_residual_partition_v1/status_components.json), [기각한 SQL 지름길의 실제 차이](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_residual_partition_v1/rejected_shortcuts.json), [전체 저장 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_residual_partition_v1/normalized_comparison_repeat1.json), [원본/frozen/서버 보존](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_residual_partition_v1/preservation_after.json)
