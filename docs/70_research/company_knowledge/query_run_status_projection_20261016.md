# 실행 중 상태 조회의 전체 JSON 복원 축소 — 2026-10-16

## 범위와 결과

기존 [#660](https://github.com/Hangi-n42/AsterGraph/issues/660)의 실행 시작·조회 차단 경계에서 상태 하나를 확인하려고 모든 run payload를 Python 객체로 복원하던 비용을 줄였다. 공통 repository helper 15줄과 같은 시작 계약의 guard 15곳만 변경했다. 고정 NAV01 저장자료 재생의 전체 평균은 **22.131→17.158초(4.973초, 22.47% 감소)**였다. 전체 saved run·result·response 네 쌍은 허용된 시간·새 ID 정규화 후 0 diff이며 기존 DB 행과 다른 table도 그대로다.

새 LLM/embedding 호출·모델 로드는 0회다. 저장 입력·벡터·응답을 재생한 비용 비교이며 실제 모델 대기 포함 QA 성능이나 새 의미 품질을 측정하지 않았다. **시간은 감소했지만 측정 process peak RSS 최대는 약 0.5 GiB 증가**했다. 메모리 절감으로 보고하지 않는다.

기준 HEAD는 `3d2ea222def2f7116de5e41d0048378e7e44d20a`다. parent `9c938e8f67594740867bf757868e2262`, F3 child `eddddac3dd4f4cca99c84fb33d6d3547`의 동일 NAV01 질문·3,721블록·3,728passage·7,998 encoder 관계 입력을 사용했다. 그래프 조인·원문 문맥/DOM·모델 설정·추출·개념화 로직은 수정하지 않았다.

## 변경 경계와 오류 보존

현재 Python 런타임의 SQLite는 **3.53.4**이며 JSON 기능의 실제 동작을 사전 확인했다. 프로젝트의 workbench도 이미 `json_extract`를 사용한다. 새 의존성·설정·스키마·상태 원장·전역/서비스 캐시는 추가하지 않았다. [SQLite 공식 JSON 문서](https://www.sqlite.org/json1.html)의 기존 `json_valid`, `json_each`, `json_group_array` 기능을 사용한다.

`KnowledgeRepository.has_active_runs(db)`는 `json_valid`의 CASE 안에서 top-level `status` 값만 모아 Python으로 전달한다. 정상 저장기가 dict를 JSON으로 쓰는 payload에서는 큰 units/response/claims/blocks를 Python 객체로 복원하지 않는다. SQLite 내부에서는 전체 JSON을 읽고 해석하므로 파일 읽기·C 내부 메모리가 사라지는 변경은 아니다.

중복 status key는 목록의 마지막 값을 사용해 기존 `json.loads`의 마지막-key 판정을 유지한다. 명시적 null·숫자·bool은 기존처럼 비활성이고, object/array는 실제 검사에서 JSON 타입을 유지해 기존 set membership의 `TypeError`를 낸다. malformed JSON·상태 누락·최상위 비객체 등은 원래 `repository.get(... )['status']`로 fallback해 기존 오류를 보존한다. Python이 받던 NaN/Infinity도 이 fallback에서 처리한다. 오류를 idle로 바꾸지 않는다.

단순 `json_extract SELECT`는 다음 손상 행의 SQL 평가가 cursor의 현재 행 반환보다 먼저 실패하는 경우가 실제 probe에서 확인됐다. CASE와 Python fallback은 원래 lazy `any`의 단락 평가를 유지한다. 앞에 active가 있으면 뒤의 손상 행을 Python에서 해석하지 않는다. parse `service.start`의 과거 eager 목록은 뒤의 손상 JSON도 먼저 해석했으므로 이 비표준 ledger에서는 `JSONDecodeError` 대신 `KnowledgeConflict`가 먼저 날 수 있다. **두 경로 모두 새 실행을 차단**하며 이 차이를 별도 검사했다.

연결한 15개 guard는 `service.start`, business `run/use/edit/checkpoint/changes/concepts/projection/html_rows/feedback`, `extraction`, `search`, `discovery_run`, `discovery_analysis`, `ontology_run`이다. 기존 closed 조건·오류 문구·service lock·DB connection/transaction·`BEGIN IMMEDIATE`·run 삽입·executor 제출 위치를 유지했다. 시작 복구, 실제 전체 run 조회/목록, `find_parse`, `shutdown`과 취소 상태 전이는 전체 payload가 필요하므로 그대로다. Python json import가 이 치환으로만 불필요해진 3곳도 제거했다.

## 별도 상태 비용과 query 측정

같은 원본 DB를 read-only로 열어 상태 경계만 각 1회 독립 process에서 실행했다. DB 38행의 payload는 총 **1,333,098,518 UTF-8 bytes**였고 양쪽 모두 active=false였다. hash·import·행 수 집계는 시간 밖이다. 원래 Python 전체 복원은 **5.926569초**, 새 helper는 **1.822282초**였다. 단독 process peak RSS는 **3,117,973,504→3,470,360,576 bytes**였다. 단발 관측이며 전체 query의 미분류 시간에서 이 값을 산술 차감하거나 정확한 비중으로 환산하지 않는다.

전체 query 기준선은 직전 `query_graph_address_join_v1/after_repeat1,after_repeat2`다. 시작 HEAD와 기준선의 계측 대상 제품 파일 hash를 확인해 재사용했다. 같은 helper를 byte-identical하게 복사했으며 SHA256은 `d10e2440c48c59a67c15ebfbeddaf1934b998b805fa7a2e104c53f7cfbee2b22`다. 계측 변경·추가 cProfile·기준선 전체 재실행은 없다. 두 새 쌍 모두 시작 DB hash는 `6dcba12174e892fa54c4666438cde09a126a75a5990e1d926ef6e5ab7738ca07`다.

| 상태 | 기존 두 조회(초) | 새 두 조회(초) | 평균 전→후(초) |
| --- | --- | --- | --- |
| cold | 22.169, 22.247 | 17.068, 17.005 | 22.208→17.037 |
| warm | 21.990, 22.117 | 17.315, 17.242 | 22.054→17.279 |

| 배타 구간 평균(초) | 기존 cold | 새 cold | 기존 warm | 새 warm |
| --- | ---: | ---: | ---: | ---: |
| repository.get 읽기·역직렬화 — DB 전체 아님 | 1.676 | 1.572 | 1.488 | 1.785 |
| graph/index/rank | 2.765 | 2.752 | 2.640 | 2.461 |
| source 복원·문맥·직렬화 | 10.539 | 10.491 | 10.674 | 10.741 |
| save로 포착한 저장 | 0.228 | 0.226 | 0.226 | 0.223 |
| vector/response 대조·복원 | 0.012 | 0.012 | 0.009 | 0.009 |
| 상태 조회·직접 SQL·decode·commit 등을 포함하는 미분류 | 6.988 | 1.985 | 7.016 | 2.059 |
| **전체 query** | **22.208** | **17.037** | **22.054** | **17.279** |

cold는 새 서비스 첫 query, warm은 같은 서비스의 다음 query다. 매 쌍은 동일 DB bytes에서 시작하고 warm에는 직전 query 1행이 남는다. OS 파일 캐시 cold는 주장하지 않는다. 복사·서비스 초기화·사전 hash·사후 artifact 기록은 query 밖이다. 모든 검사와 단독 비교를 끝내고 실제 query 두 쌍을 순서대로 실행해 테스트/다른 CPU 작업과 겹치지 않았다. 같은 ordered vector text hash와 전체 요청 messages/schema/설정을 정확히 대조한 경우만 저장 자료를 복원했고 실제 graph/rank/PPR/RRF/lexical/context/저장 경로를 실행했다.

모든 query의 원시 배타 합계 오차는 0초다. 미분류 평균은 **7.002→2.022초**였지만 전부 상태 조회라고 단정하지 않는다. 단독 경계 비용과 query 구간 감소는 측정 환경·범위가 달라 같은 값이 아니다. 수정하지 않은 구간의 편차도 개선으로 해석하지 않는다. `build=1`, `chunks=1`, `source_context=3`은 전후 동일하다. build의 새 cold 포함시간 0.324/0.328초와 warm 0.143/0.145초도 보존하되 포함시간을 위 배타 표에 더하지 않는다. 두 쌍의 제한된 관측으로 통계적 유의성이나 다른 자료의 상한은 주장하지 않는다.

## 메모리와 검사 한계

초기화와 두 query를 포함하는 process peak RSS 최대는 cold **5,991,415,808→6,563,463,168 bytes(+545.5 MiB)**, warm **6,118,539,264→6,675,251,200 bytes(+530.9 MiB)**였다. 단독 상태 비교에서도 증가가 관측됐다. SQLite 내부 JSON 해석이 사용하는 임시 메모리, 이후 할당·반환·단편화 등 세부 원인은 분리 측정하지 않았다. 요청 밖 상태 캐시는 없지만 RSS가 즉시 반환된다고 보장하지 않는다. 동시 요청·실제 모델 로드 포함 메모리·임의 크기 ledger의 상한은 미측정이다.

새 경계 검사 **98개 통과**다. 정상/비표준 상태·malformed/누락·top-level shape·중복키·escape·중첩 status·NaN/Infinity, 단락 평가, 작은 fragment만 Python 해석, 조회 무쓰기, 같은 transaction의 미커밋 상태 변화/rollback, 15개 caller의 queued/running/cancel_requested 차단·closed 단락·lock 내부 호출을 확인했다.

기존 관련 16모듈은 **321개 통과, 16개 실패**였다. 실패 16개만 변경 전 `3d2ea222`의 별도 app+configs export에서 다시 검사해 **전부 같은 오류 서명으로 재현**했다. 기존 Builder/inspection 계약, fixture의 `recipe/units/requirements` 누락 등이므로 이번 제품 변경으로 고치지 않았다. 합계는 서로 다른 **419개 통과, 기존 실패 16개 유지**이며 전체 검사가 통과했다고 표시하지 않는다. 두 검사 실행의 native model 진입 차단 기록도 시도 0이다.

baseline export의 최초 검사 준비는 app만 복사해 configs 누락 collection error가 났다. HEAD의 configs를 추가한 보완본으로 대조했고 원 오류/스크립트/XML도 보존했다. 이는 새 의미 평가나 모델 실패가 아니다. 기존 max6 실패 계보를 유지하며 새 의미 실험은 없다.

## 결과 보존과 남은 병목

전체 saved run·result·모든 response 네 쌍이 정규화 후 0 diff다. retrieval 12개, source_context 33개, passage index 3,728개/848,607 UTF-8 bytes, 순위·PPR/RRF·선택·전달 입력·답변·인용·`succeeded/answered` 저장 상태를 유지했다. 새 query 행 외 모든 기존 DB 행·다른 table도 같다. `answered`는 기존 형식·근거 참조 검사 상태이며 의미 정확성 보증은 아니다.

시간 제외는 `run.started_at`, `run.finished_at`, `run.metrics.elapsed_s`, `run.graph_retrieval.elapsed_s`, `run.graph_retrieval.index_elapsed_s`, `run.units[*].started_at`, `run.units[*].finished_at`의 7종뿐이다. 새 query/request ID만 위치/stage별 표식으로 바꿨고 source/target/claim/version ID는 그대로다. cache 제외는 0개이며 provider response의 과거 시간·parsed payload도 유지했다. 재생 usage/elapsed를 새 모델 비용으로 더하지 않는다.

남은 평균 **17.158초** 중 source 복원·문맥·직렬화 **10.616초**, graph/index/rank **2.606초**, 미분류 **2.022초**, get 읽기 **1.678초**, save **0.225초**, replay **0.010초**가 관측된다. 다음 후보는 가장 큰 선택별 문맥 조립/DOM의 기존 필수 원문 보존 비용이며 조정 담당 채팅에서 별도 범위를 결정한다. 원문 내용·필수 제목/부모·예외를 줄이는 것은 이번 방법의 연장이 아니다. 실제 모델 대기는 여전히 미측정이며 복구/목록/shutdown의 전체 payload 처리도 이번 범위 밖이다. 현재 사용자 결정이 필요한 사항 없음.

원본 DB·paused DB·407개 frozen 코드·이전 결과/기각 실험·원래 작업트리·기존 4개 서버를 보존했다. #660 전체는 미완료로 open 유지한다. 새 추출/전체 평가/paused 개념화 재개/새 이슈·PR/merge/배포는 없다. raw/DB·baseline export·replay helper는 Git에 넣지 않는다.

근거 루트는 `/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_run_status_projection_v1/`다.

- [단독 기존 상태 경계](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_run_status_projection_v1/status_boundary_before.json), [새 상태 경계](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_run_status_projection_v1/status_boundary_after.json), [query 시간·호출·RSS](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_run_status_projection_v1/measurement_summary.json)
- [반복 1 저장 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_run_status_projection_v1/normalized_comparison_repeat1.json), [반복 2 저장 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_run_status_projection_v1/normalized_comparison_repeat2.json)
- [새 검사 98개](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_run_status_projection_v1/status_tests.xml), [기존 검사 결과](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_run_status_projection_v1/existing_boundary_tests.xml), [기존 실패 16건 변경 전후 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_run_status_projection_v1/test_failure_audit.json), [원본·frozen·서버 보존](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_run_status_projection_v1/preservation_after.json)
