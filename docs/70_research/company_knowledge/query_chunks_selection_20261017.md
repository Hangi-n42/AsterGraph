# 최초 원문 묶음의 표·형제 후보 순회 축소 — 2026-10-17

## 범위와 결과

기존 [#660](https://github.com/Hangi-n42/AsterGraph/issues/660)에서 최초 원문 묶음 `autoschema.chunks`의 표·형제 후보 검색만 줄였다. **한 함수의 9줄 추가/2줄 교체**이며 같은 연속 source_version 그룹 안에 지역 후보 목록 두 개만 만든다. 이미 완료한 list ancestor prefilter·chunks 요청 내 공유·source_context·DOM selector·상태 조회·임베딩 재사용은 재작성하지 않았다.

반복 개발에 사용한 고정 NAV01/D01 저장자료 재생의 전체 평균은 **12.452400→11.491458초(0.960943초, 7.72% 감소)**였다. 그 안에 포함되는 chunks는 **3.728294→2.609319초**, source 복원·문맥·직렬화 배타 구간은 **5.913509→4.848382초**였다. 이 세 시간을 서로 더하지 않는다. 전체 검색/선택·QA messages/schema·저장 run/result/모든 responses 네 쌍은 허용된 시간·새 ID 정규화 후 0 diff다. 새 모델·embedding 호출/로드는 0회이며 독립 평가나 새 의미 품질 검증은 아니다.

기준 HEAD는 `0f35104859838cc11c697901c9b1d84c41703554`다. source는 저장된 `D01_canonical.html`의 parent `9c938e8f67594740867bf757868e2262`, F3 child `eddddac3dd4f4cca99c84fb33d6d3547`이며 3,721블록·3,728passage·7,998 encoder 관계 입력을 사용했다. 실제 모델 대기 포함 QA 성능이나 의미 품질을 새로 평가하지 않았다.

## 먼저 구분한 비용과 계측 한계

같은 저장 blocks의 무계측 chunks 단독 실행을 조회용과 추출 기본 계약으로 각각 보존했다. 시간은 chunks 호출만 포함하고 입력 읽기·hash·출력 JSON 생성/저장/대조는 밖이다.

| 계약 | context/output tokens | target chars | 수정 전(초) | 수정 후(초) | 전체 출력 |
| --- | --- | ---: | ---: | ---: | --- |
| 조회 | 49,152/4,096 | 1 | 3.693209 | 2.637993 | 3,728묶음·36,092 view·30,974,330 bytes 동일 |
| 추출 기본 | 49,152/8,192 | 기본값 1,000 | 3.907187 | 2.832487 | 61묶음·4,245 view·3,666,833 bytes 동일 |

두 출력은 ID·순서·원문·조건/예외·span/context_only·locator·source_reference_map 등 **제외 필드 없이 byte-identical**하다. 조회 출력 SHA256은 `96a856860adb12a55797787740b9b9878ab4e548deaf3a0d30027cc3843bcb60`, 추출 기본 출력은 `9229cc1f23a607cb24bae2cb4bf9b2758ee2de194361e9d04b3b1689b9a5e76d`다. 추출 기본값 외에도 공용 호출부가 1/1,000을 사용함을 확인했고 추출을 실제 재실행하지 않았다.

수정 전 chunks-only cProfile은 별도 1회 실행했다. 진단 벽시계는 **11.146677초**로 무계측 3.693209초의 약 3.02배였다. 진단 출력도 무계측 전체 출력과 같았다. 아래 수치는 계측 오버헤드가 포함된 진단 경로의 포함시간이며 실제 전체 query 구간이나 절감 가능 시간으로 환산하지 않는다.

| 서로 중첩되지 않는 진단 경로 | 진단 포함시간(초) |
| --- | ---: |
| 표 후보 comprehension | 4.989863 |
| 형제 후보 comprehension | 2.112222 |
| 기존 list_parents | 1.933812 |
| emit의 deepcopy | 0.969494 |
| source_text의 packet/문자열/JSON | 0.759867 |
| 자식 목록 후보 | 0.114703 |
| unique/정렬 | 0.069957 |
| split | 0.032989 |
| notes 필터 | 0.008074 |

큰 경로로 확인된 두 후보 순회만 변경했다. 기존 list parent 계산, 정렬/중복 정리, packet·문자열/JSON 직렬화와 복사는 그대로다. 진단의 약 7.1초를 실제 chunks 3.728초에서 빼거나 그만큼 줄일 수 있다고 해석하지 않았다. 추가 profiling·큰 구조 변경으로 범위를 확장하지 않았다.

## 최소 변경과 보존한 선택 의미

각 **연속** source_version 그룹에서 모든 block을 원래 `locator.get('element_path')`별 목록에 담는다. 표 후보는 이 목록 안에서 기존 ID 제외·같은 path·row 0/header·같은 row·rowspan 조건을 그대로 검사한다. row 필드가 있는 후보만 미리 고르지 않는다. 기존에는 row가 없어도 merged_span 조건으로 선택될 수 있으므로 그 후보도 보존했다. 경로 누락의 `None`과 명시적 빈 문자열도 합치지 않았다.

row 없는 block은 원래 부모 path별 목록에도 담는다. 형제 검색은 이 목록 안에서 기존 현재 block의 `' > '` 가드·row 필드 없음·부모 일치 조건을 그대로 적용한다. notes regex, local list의 기본 항목과 예외 연결, 상위 제목/조건·명시 참조·자식 목록은 변경하지 않았다. 그룹과 목록의 순서를 바꾸지 않으며 같은 version이 떨어져 재등장하면 새 목록을 만든다. 같은 이름·중복 ID·다른 parse의 기존 선택/중복 처리 규칙도 바꾸지 않았다.

코드상 선택 조건을 제거하거나 새 의미를 추론하지 않았다. span/context_only 우선순위, source_order 정렬, chunk ID 생성, continuation, 용량 실패, output 필드와 deepcopy도 그대로다. 입력 객체를 수정하지 않으며 새 목록은 한 group을 구성하는 동안만 쓰는 참조 목록이다. 전역/서비스 캐시·프레임워크·새 설정은 없다.

고정 blocks를 계측 밖에서 다시 계산한 후보 방문 수는 표 **12,372,325→4,746,413**, 형제 **13,845,841→7,512**다. 선택된 원문 수가 아니라 comprehension에 들어가는 후보 수이며 실제 선택 결과는 위 전체 byte 대조로 확인했다. 가장 큰 동일 path 목록은 **2,157개**다. 같은 경로 안의 행/header/병합 범위 대조가 남아 있어 경로 index만으로 표 비용이 사라지지 않는다. 모든 표가 같은 path에 모이면 표 후보 대조의 이차 반복도 남는다.

## 동일 전체 조회와 메모리

최신 `query_source_context_repeats_v1/after_repeat1,after_repeat2`의 시작 코드 hash를 확인해 기준선을 재사용했다. helper는 byte-identical한 SHA256 `d10e2440c48c59a67c15ebfbeddaf1934b998b805fa7a2e104c53f7cfbee2b22`, 시작 DB는 `6dcba12174e892fa54c4666438cde09a126a75a5990e1d926ef6e5ab7738ca07`다. 계측 대상 제품 파일 중 `autoschema.py`만 다르다. 새 복사 DB·query ID·근거는 별도 20261017 경로에 보존했다.

| 상태 | 기존 두 조회(초) | 새 두 조회(초) | 평균 전→후(초) |
| --- | --- | --- | --- |
| cold | 12.398, 12.552 | 11.474, 11.531 | 12.475→11.502 |
| warm | 12.397, 12.462 | 11.438, 11.523 | 12.429→11.481 |

| 배타 구간 평균(초) | 기존 cold | 새 cold | 기존 warm | 새 warm |
| --- | ---: | ---: | ---: | ---: |
| repository.get 읽기·역직렬화 — DB 전체 아님 | 1.566 | 1.595 | 1.780 | 1.566 |
| graph/index/rank | 2.772 | 2.796 | 2.448 | 2.728 |
| source 복원·문맥·직렬화 | 5.910 | 4.842 | 5.917 | 4.855 |
| save로 포착한 저장 | 0.228 | 0.232 | 0.229 | 0.232 |
| vector/response 대조·복원 | 0.013 | 0.013 | 0.010 | 0.010 |
| 상태 조회·직접 SQL·decode·commit 등을 포함하는 미분류 | 1.985 | 2.025 | 2.046 | 2.090 |
| **전체 query** | **12.475** | **11.502** | **12.429** | **11.481** |

source 구간은 평균 1.065초 감소했지만 전체 순감소는 0.961초다. graph/index/rank는 2.610→2.762초로 증가했고 get 등 다른 구간도 달랐다. 그 원인을 별도 분리하지 않았으므로 변경하지 않은 구간의 편차를 이번 개선으로 합치지 않는다. `build=1`, `chunks=1`, `source_context=3`, `serialize=1`은 유지했다. query 안의 chunks는 새 cold 2.581/2.616초, warm 2.602/2.639초이며 위 source 구간에 포함된다.

cold는 새 서비스의 첫 query, warm은 같은 서비스의 다음 query다. 매 쌍은 같은 DB bytes로 시작하고 warm에는 직전 query 1행이 남는다. OS 캐시 cold는 주장하지 않는다. 복사·서비스 초기화·사전 hash·사후 artifact 기록은 query 밖이다. 단독 실행/프로파일/검사를 모두 끝낸 뒤 두 쌍을 순서대로 측정했다. 원시 배타 합계 오차는 네 query 모두 0초다. 두 쌍의 제한된 관측으로 통계적 유의성·다른 자료의 상한을 주장하지 않는다.

동일 helper의 process peak RSS 최대는 cold **6,538,264,576→6,541,148,160 bytes(+2.75 MiB)**, warm **6,649,020,416→6,649,233,408 bytes(+0.203 MiB)**였다. 작은 증가가 관측됐으며 메모리 최적화로 표현하지 않는다. chunks-only after helper는 기존 JSON 추가 read/byte 대조가 있어 before와 동일한 메모리 작업이 아니다. 그 단독 process peak 차이를 index 자체의 메모리 비용으로 해석하지 않았다. 지역 목록의 정확한 할당·OS 반환·동시 요청·실제 모델 로드 포함 메모리 상한은 미측정이다.

## 전체 결과와 검사

실제 조회는 ordered vector 입력과 전체 모델 요청이 정확히 일치할 때만 저장 벡터/응답을 복원했다. 실제 graph/rank/PPR/RRF/lexical/context/저장 경로를 실행했고 전체 run/result/모든 responses 네 쌍이 0 diff다. 순위·선택·조건/예외·출처/version/parse/span·QA messages/schema·답변·인용·`succeeded/answered` 상태를 유지했다. retrieval 12개·source_context 33개·passage index 3,728개/848,607 UTF-8 bytes도 유지했지만 개수만으로 동등성을 판정하지 않았다. 새 query 행 외 기존 DB 모든 행·다른 table도 같다.

제외는 시간 7종(`run.started_at/finished_at`, `run.metrics.elapsed_s`, `run.graph_retrieval.elapsed_s/index_elapsed_s`, `run.units[*].started_at/finished_at`)뿐이다. 새 query/request ID만 위치/stage 표식으로 바꾸고 source/claim/version ID·cache 필드·provider response의 과거 시간/parsed payload는 유지했다. cache 제외는 0개이며 재생 usage/elapsed를 새 모델 비용으로 더하지 않는다.

관련 검사 **125개 통과**, frozen 수정 전 모듈과의 differential **31건 전체 동일**이다. 실제 두 target 출력 외에 target 1/1,000과 큰/작은 용량, 같은 version 재등장, 역순, 중복 ID·다른 parse, missing/empty path, 원래 span/context_only, 빈 입력, header/rowspan·row 없는 병합 후보·다른 표·상위 조건·목록 기본/예외·명시 참조·continuation·용량 실패·입력 비변형을 확인했다. 출력의 모든 필드·순서·ID·본문·map과 관련 예외를 그대로 대조했다.

새 7개 검사에서 fixture 실패는 없었다. 순서 검사 중 항상 참인 `sorted(..., key=lambda _:0)` 단언은 실제 v1→v2→v1 연속 순서를 확인하도록 고쳤다. 처음 7개 통과 기록과 수정 후 125개 기록을 구분해 보존한다. 알려진 기존 실패 16건은 이번 경계와 무관해 반복하거나 고치지 않았다. 최대6회 기존 실패 계보를 유지하며 새 의미 실험은 없다.

## 국소 한계와 다음 우선순위

약 1초를 줄인 작은 변경으로 종료하며 추가 자료구조나 직렬화 재작성으로 확장하지 않았다. 남은 배타 평균은 source **4.848초**, graph/index/rank **2.762초**, 미분류 **2.057초**, get 읽기 **1.581초**, save **0.232초**, replay **0.011초**다. chunks **2.609초는 source 구간 안의 포함시간**이다. 원래 묶음 출력·필수 원문·복사/직렬화를 줄이는 것은 이번 방법의 연장이 아니다.

남은 chunks에는 큰 동일 path 목록의 행/병합 대조·list parent·직렬화/복사가 있지만, 이 작은 함수를 계속 줄이는 작업을 즉시 권할 근거는 부족하다. 이번 최적화는 여기서 멈춘다. 추가 작업이 필요하면 위 전체 남은 비용과 실제 사용상의 필요를 기준으로 범위를 고르는 것이 다음 우선순위다. 조정 담당 채팅에 이 한계를 인계하며 현재 사용자 결정이 필요한 사항 없음.

원본/paused DB·407개 frozen 코드·20261016/기존20261017 근거·원래 작업트리·기각 실험/실패 기록·기존 4개 서버를 보존했다. 새 추출/전체 평가/paused 구축 재개/새 이슈·PR/merge/배포는 없다. #660 전체는 미완료로 open 유지한다. raw/DB·전체 묶음·frozen 모듈·재생 helper는 Git에 넣지 않는다.

근거 루트는 `/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_chunks_selection_v1/`다.

- [무계측 수정 전 묶음](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_chunks_selection_v1/before_chunks_receipt.json), [수정 후 전체 묶음 동등성](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_chunks_selection_v1/after_chunks_receipt.json), [별도 진단 프로파일](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_chunks_selection_v1/chunks_diagnostic.json)
- [전체 query 시간/호출/RSS](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_chunks_selection_v1/measurement_summary.json), [포함/배타와 후보 수](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_chunks_selection_v1/phase_detail.json), [반복 1 전체 저장 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_chunks_selection_v1/normalized_comparison_repeat1.json), [반복 2 전체 저장 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_chunks_selection_v1/normalized_comparison_repeat2.json)
- [125개 검사](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_chunks_selection_v1/chunks_boundary_tests.xml), [frozen 경계 31건](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_chunks_selection_v1/boundary_equivalence.json), [원본/frozen/서버 보존](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261017/query_chunks_selection_v1/preservation_after.json)
