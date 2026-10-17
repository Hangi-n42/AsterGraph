# 원문 문맥 구성·DOM 직렬화의 반복 계산 축소 — 2026-10-17

## 범위와 결과

기존 [#660](https://github.com/Hangi-n42/AsterGraph/issues/660)의 다음 범위로 **문맥 안의 주소 후보 검색·중복 초기값 생성과 한 DOM 직렬화 안의 같은 selector 조회**만 줄였다. 제품은 `graph_retrieval.source_context`, `source_reader.serialize` 두 함수의 16줄 추가/13줄 삭제다. 원문·부모·제목·표·조건·예외를 줄이거나 선택별 문맥 결과를 공유하지 않았다.

동일 NAV01 저장자료 재생에서 전체 평균은 **17.157722→12.452400초(4.705322초, 27.42% 감소)**, source 복원·문맥·직렬화 배타 평균은 **10.616153→5.913509초**였다. 전체 saved run·result·모든 response 네 쌍은 허용된 시간·새 ID 정규화 후 0 diff다. 새 LLM/embedding 호출과 모델 로드는 0회이며 실제 모델 대기 포함 QA 성능이나 새 의미 품질을 평가한 결과는 아니다.

기준 HEAD는 `bb038ff88f59ba713fe14ab4f0d16fa33792c535`다. parent `9c938e8f67594740867bf757868e2262`, F3 child `eddddac3dd4f4cca99c84fb33d6d3547`의 동일 질문·3,721블록·3,728passage·7,998 encoder 관계 입력을 사용했다. 이미 완료한 chunks 공유·build 공유/주소 조인·임베딩 재사용·상태 전용 조회는 재작성하지 않았다.

## 비용 원인과 최소 변경

최신 저장 계측의 첫 `source_context`는 chunks를 포함해 5.48~5.90초, 그 안 chunks는 3.70~4.00초였다. 선택 단계의 두 번째 호출은 2.22~2.46초, 최종 12개 선택의 호출은 약 0.0067초였다. DOM serialize는 약 2.02~2.04초였다. 기존 계측과 코드를 대조해 반복 계산을 특정할 수 있어 추가 profiling·기준선 재실행은 하지 않았다. 호출 3회가 모두 같은 결과라고 가정하지 않았다.

문맥 구성은 context-only 블록마다 전체 context를 `next(...)`로 훑었다. 새 코드는 기존 첫 순회에서 `(source_version_id, block_id)`별 context 후보 목록을 만든다. 이 목록 안에서 **원래 span list 비교와 첫 일치**를 그대로 실행한다. 정확 span hash index로 바꾸지 않아 같은 주소 후보의 span 필드 접근·오류, list와 tuple의 비교, falsey 첫 ID도 기존대로다. 기존 코드가 parse를 별도 비교하지 않는 이 lookup 규칙도 그대로 유지했다. 본문·다른 parse를 근거로 새 병합을 하거나 적용성을 판단하지 않는다.

기존 `views.setdefault`는 같은 view가 있어도 `source_packet/reader_locator` 기본값을 매번 계산했다. 이제 view key가 처음 생길 때만 계산한다. 동일 주소·span의 첫 본문·locator·parse 기록을 보존하고 `supports_context_ids`는 원래 target 순서로 계속 누적한다. 선택이 바뀌면 새 호출에서 새 목록과 view를 만든다. 기존 context 항목에 locator를 붙이는 동작은 유지하며 blocks·bundles는 바꾸지 않는다.

DOM serialize는 같은 soup에서 여러 record의 공통 CSS prefix와 heading selector를 반복 조회했다. 한 `serialize`의 지역 dict에 `soup.select` 결과만 보관한다. 빈 결과·여러 node가 나오는 결과·selector 문법 오류도 보관하지만 len 검사·직접 부모 identity 확인·heading 범위·표 좌표 검증은 그대로다. selector 문법 외 예외는 기존처럼 전파한다. 선택 결과 목록이나 soup를 수정하지 않으며 캐시는 호출 밖으로 남지 않는다. 다른 parse/version의 `for_service` 문서마다 `serialize`가 새 dict를 만든다.

전역/서비스 캐시·설정·범용 준비 객체는 추가하지 않았다. 첫 일치와 결과 삽입 순서, `chunks=1`, `source_context=3`, `build=1`, `serialize=1`은 유지한다. 원래 `source_context_bundles`의 수명·지연 계산·실패 경계·QA 전 해제는 변경하지 않았다.

## 같은 입력의 시간 비교

기준선은 20261016의 `query_run_status_projection_v1/after_repeat1,after_repeat2`다. 시작 HEAD와 계측 대상 제품 hash가 일치함을 확인했다. helper는 byte-identical한 `d10e2440c48c59a67c15ebfbeddaf1934b998b805fa7a2e104c53f7cfbee2b22`, 시작 DB는 동일 SHA256 `6dcba12174e892fa54c4666438cde09a126a75a5990e1d926ef6e5ab7738ca07`다. 변경된 계측 대상 제품 파일은 위 두 모듈뿐이다. 새 artifact·복사 DB·run ID는 별도 20261017 경로에 보존했다.

| 상태 | 기존 두 조회(초) | 새 두 조회(초) | 평균 전→후(초) |
| --- | --- | --- | --- |
| cold | 17.068, 17.005 | 12.398, 12.552 | 17.037→12.475 |
| warm | 17.315, 17.242 | 12.397, 12.462 | 17.279→12.429 |

| 배타 구간 평균(초) | 기존 cold | 새 cold | 기존 warm | 새 warm |
| --- | ---: | ---: | ---: | ---: |
| repository.get 읽기·역직렬화 — DB 전체 아님 | 1.572 | 1.566 | 1.785 | 1.780 |
| graph/index/rank | 2.752 | 2.772 | 2.461 | 2.448 |
| source 복원·문맥·직렬화 | 10.491 | 5.910 | 10.741 | 5.917 |
| save로 포착한 저장 | 0.226 | 0.228 | 0.223 | 0.229 |
| vector/response 대조·복원 | 0.012 | 0.013 | 0.009 | 0.010 |
| 상태 조회·직접 SQL·decode·commit 등을 포함하는 미분류 | 1.985 | 1.985 | 2.059 | 2.046 |
| **전체 query** | **17.037** | **12.475** | **17.279** | **12.429** |

별도 함수 포함시간 평균에서 선택 단계의 `source_context`는 **2.333528→0.362639초**, DOM serialize는 **2.034518→0.809335초**였다. `source_context` 3회 합에서 그 안의 chunks 시간을 제외한 나머지는 **4.194332→0.833868초**다. 첫 호출은 chunks를 포함하므로 5.698012→4.193602초이고 최종 선택 호출은 0.006722→0.005920초다. 포함시간을 위 배타 구간 총계에 더하지 않는다. 수정하지 않은 chunks의 3.843930→3.728294초나 graph/미분류 편차를 이번 개선으로 주장하지 않는다.

각 쌍은 같은 DB bytes에서 새 서비스로 시작했다. cold는 첫 query, warm은 같은 서비스의 다음 query이며 warm에는 직전 query 1행이 남는다. OS 파일 캐시 cold는 주장하지 않는다. 복사·서비스 초기화·사전 hash·사후 artifact 기록은 query 밖이다. 모든 검사와 별도 CPU 작업을 끝낸 후 두 쌍을 순서대로 측정했다. 원시 배타 합계 오차는 네 query 모두 0초다. 측정 날짜·환경이 다른 두 쌍의 관측으로 통계적 유의성·다른 자료의 상한을 주장하지 않는다.

## 메모리·동등성·위험 경계

초기화와 두 query를 포함한 process peak RSS 최대는 cold **6,563,463,168→6,538,264,576 bytes(-24.0 MiB)**, warm **6,675,251,200→6,649,020,416 bytes(-25.0 MiB)**였다. 이번 관측에서 증가하지 않았지만 작은 차이를 일반적인 메모리 개선이나 상한으로 해석하지 않는다. 지역 후보 목록과 selector 결과는 각 함수 호출 동안만 보유한다. DOM이 호출 밖에 남지 않는 약한 참조 검사도 통과했지만 OS 반환·세부 할당·동시 요청·실제 모델 로드 포함 메모리는 측정하지 않았다. 이전 상태 조회 변경의 약 0.5 GiB peak 증가를 해소했다고 주장하지 않는다.

전체 검색순위·선택·주소/source/version/parse/span·조건·예외·부모·표 머리글/병합·continuation을 포함하는 전달 입력·QA messages/schema·저장 run/result/모든 responses가 네 쌍 모두 정확 일치했다. ordered vector 입력과 전체 모델 요청이 정확히 일치할 때만 저장 자료를 복원했고 실제 graph/rank/PPR/RRF/lexical/context/저장 경로를 실행했다. retrieval 12개, source_context 33개, passage index 3,728개/848,607 UTF-8 bytes도 유지됐지만 개수만으로 보존을 판정하지 않았다. 새 query 행 외 기존 DB 모든 행·다른 table도 그대로다.

비교 제외는 `run.started_at`, `run.finished_at`, `run.metrics.elapsed_s`, `run.graph_retrieval.elapsed_s`, `run.graph_retrieval.index_elapsed_s`, `run.units[*].started_at`, `run.units[*].finished_at`의 시간 7종뿐이다. 새 query/request ID만 위치/stage 표식으로 바꾸고 cache 필드 제외는 0개다. provider response의 과거 시간·parsed payload도 비교했으며 재생 usage/elapsed를 새 모델 비용으로 합산하지 않는다. `succeeded/answered`는 기존 저장·형식·근거 참조 상태이며 의미 품질 보증은 아니다.

관련 검사 **109개 통과** 후, 같은 block/path가 다른 parse 또는 다른 version에 속할 때 문서를 격리하는 **2개 검사도 추가 통과해 최종 서로 다른 111개 통과**다. 제품은 두 함수 그대로이며 보완 검사 때문에 성능 측정을 반복하지 않았다. 기존 실제 표/제목/부모/예외/continuation·다중 버전·capacity/실패 저장·빈 결과·다른 요청·원문 변경·객체 비변형·QA 전 해제 검사를 재사용했다. 알려진 기존 실패 16건은 이번 변경 경계가 아니므로 재실행하거나 고치지 않았다.

frozen 수정 전 두 모듈과의 differential **16건은 제외 필드 없이 전체 출력/순서/예외가 일치**했다. 중복 주소의 다른 span/본문/locator/parse에도 첫 view와 지원 대상 순서를 보존했다. 작은 fixture에서는 같은 note의 packet 호출 **6→2회**, DOM selector 호출 **24→10회**를 계수했다. 이는 작은 fixture의 수치이며 실제 NAV01의 호출 수로 바꾸어 보고하지 않는다.

새 검사 최초 실행의 1개 실패는 bare `h2` 경로를 parser의 `h2:nth-of-type(...)` 경로로 가정한 fixture 오류였다. 기존 heading 검증은 `h2:` 형식에서 범위를 확인하므로 fixture만 수정했다. 제품 검증 판정은 바꾸지 않았고 원 실패 XML·수정 전 semantic 8개 통과 기록도 보존했다. 기존 최대6회 실패 계보를 유지하며 새 의미 실험은 없다.

## 남은 병목과 보존 자료

남은 평균 **12.452초**는 source 복원·문맥·직렬화 **5.914초**, graph/index/rank **2.610초**, 미분류 **2.016초**, get 읽기 **1.673초**, save **0.228초**, replay **0.011초**다. 현재 가장 큰 단일 함수 관측은 한 번의 **chunks 약 3.728초**이며 위 source 구간 안에 포함된다. 후속 확인 대상은 그 안의 표·목록·예외 문맥 선택과 묶음 직렬화 중 실제 큰 계산이다. 이번에는 chunks를 추가 수정하지 않았으며 필수 원문을 줄이는 방법은 제외한다. 다음 범위는 조정 담당 채팅에서 결정하며 현재 사용자 결정이 필요한 사항 없음.

원본 DB·paused DB·407개 frozen 코드·20261016 원본 근거·기존 결과/기각 실험·원래 작업트리·기존 4개 서버를 보존했다. 새 추출/전체 평가/paused 개념화 재개/새 이슈·PR/merge/배포는 없다. #660 전체는 미완료로 open 유지한다. raw/DB·frozen 모듈·재생 helper는 Git에 넣지 않는다.

새 근거 루트는 `/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_source_context_repeats_v1/`다.

- [시간·호출·RSS 집계](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_source_context_repeats_v1/measurement_summary.json), [포함 함수/배타 구간 구분](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_source_context_repeats_v1/phase_detail.json)
- [반복 1 전체 저장 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_source_context_repeats_v1/normalized_comparison_repeat1.json), [반복 2 전체 저장 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_source_context_repeats_v1/normalized_comparison_repeat2.json), [frozen 경계 16건](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_source_context_repeats_v1/boundary_equivalence.json)
- [109개 검사](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_source_context_repeats_v1/context_boundary_tests.xml), [version/parse 격리 2개](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_source_context_repeats_v1/version_parse_tests.xml), [원본·frozen·서버 보존](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_source_context_repeats_v1/preservation_after.json)
