# 그래프와 원문 주소의 후보 대조 축소 — 2026-10-16

## 범위와 결과

기존 [#660](https://github.com/Hangi-n42/AsterGraph/issues/660)의 남은 비용 중 `graph_retrieval.build` 안의 **그래프↔원문 주소 대조만** 줄였다. 고정 NAV01 저장자료의 실제 조회 경로 재생에서 전체 평균은 **29.128→22.131초(6.997초, 24.02% 감소)**, graph/index/rank 배타 평균은 **9.895→2.703초**였다. 그 안에 포함되는 build 평균은 **7.490→0.146초**였다. 포함시간과 배타시간을 합산하지 않는다.

수정 전후 실제 전체 그래프는 속성·키·순서를 포함한 **18,671,200 bytes가 완전 일치**했다. 전체 saved run·result·모든 response도 허용된 시간·새 ID 정규화 후 네 조회 모두 0 diff다. 새 LLM/embedding 호출과 모델 로드는 0회다. 저장자료의 비용 감소이며 새 의미 품질이나 모델 대기 포함 QA 성능을 측정한 결과는 아니다.

기준 HEAD는 `0e29038fa50723e11c486aa6dd3a2d1806108ecc`다. parent `9c938e8f67594740867bf757868e2262`, F3 child `eddddac3dd4f4cca99c84fb33d6d3547`의 동일 질문·3,721블록·3,728passage를 사용했다. 전체 graph 24,697edge와 encoder 관계 입력 7,998개는 별개다. 전체 run 상태 읽기·선택별 문맥 조립·모델 설정·새 병합 규칙은 변경하지 않았다.

## 최소 변경과 의미 보존

원문 passage pool을 완성한 뒤 `(source_version_id, block_id)`별 목록을 만든다. claim의 evidence는 해당 주소 후보만 대조하고 기존 source/version/parse/span/claim 중복 판정은 그대로 실행한다. 최종 `passages.values()`에서 목록을 만들기 때문에 동일 passage ID가 dict에서 덮어써지는 경우도 기존 순서·중복 의미를 보존한다.

claim→passage 연결을 마친 뒤 claim별 passage 역목록을 만든다. 각 그래프 노드는 관련 claim 후보의 합집합만 검사하되, **원래 passage 순서로 정렬**해 mention edge 삽입 순서를 유지한다. 기존 linked claim 교집합과 정렬, 검증된 분류·부채비율 행의 자체 evidence 구간 제한은 유지한다. 모든 목록은 한 build 호출의 지역변수다. 전역·서비스 캐시나 저장 필드는 추가하지 않았다.

claim evidence에서 `parse_run_id`가 누락되면 기존 fallback처럼 해당 주소의 모든 parse 후보와 대조한다. 명시적 `None`은 parse가 `None`인 passage만 연결한다. 반면 검증된 행의 node evidence는 기존 `ref.get(...) == loc.get(...)`를 유지하므로 누락 parse가 `None`으로 비교된다. 이 두 규칙을 합치지 않았다. 구간은 엄격한 겹침(`<`)만 연결하며 인접 경계는 연결하지 않는다. legacy quote 기반 passage 생성·첫 evidence 보존도 변경하지 않았다.

## 기준선과 실제 시간

직전 `query_context_bundle_reuse_v1/after_repeat1,after_repeat2`의 제품 파일 hash가 시작 HEAD와 모두 같아 두 cold/warm 쌍을 재사용했다. 새 실행과 다른 측정 대상 제품 파일은 `graph_retrieval.py` 한 개뿐이다. 기준선 재실행·추가 cProfile·새 모델 실험은 하지 않았다.

재생 helper는 기준선의 기록 보정본과 **byte-identical**이며 SHA256은 `d10e2440c48c59a67c15ebfbeddaf1934b998b805fa7a2e104c53f7cfbee2b22`다. 두 쌍 모두 시작 DB hash는 `6dcba12174e892fa54c4666438cde09a126a75a5990e1d926ef6e5ab7738ca07`다. 저장 vector의 ordered text hash와 요청의 전체 messages/schema/설정을 정확히 대조한 경우만 복원했다. 실제 graph/rank/PPR/RRF/lexical/context/저장 경로를 실행했다.

| 상태 | 기존 두 조회(초) | 새 두 조회(초) | 평균 전→후(초) |
| --- | --- | --- | --- |
| cold | 29.022, 28.870 | 22.169, 22.247 | 28.946→22.208 |
| warm | 29.479, 29.141 | 21.990, 22.117 | 29.310→22.054 |

| 배타 구간 평균(초) | 기존 cold | 새 cold | 기존 warm | 새 warm |
| --- | ---: | ---: | ---: | ---: |
| repository.get 읽기·역직렬화 — DB 전체 아님 | 1.609 | 1.676 | 1.661 | 1.488 |
| graph/index/rank | 9.921 | 2.765 | 9.870 | 2.640 |
| source 복원·문맥·직렬화 | 10.363 | 10.539 | 10.553 | 10.674 |
| save로 포착한 저장 | 0.224 | 0.228 | 0.223 | 0.226 |
| vector/response 대조·복원 | 0.012 | 0.012 | 0.009 | 0.009 |
| 직접 SQL·decode·commit 등을 포함할 수 있는 미분류 | 6.817 | 6.988 | 6.994 | 7.016 |
| **전체 query** | **28.946** | **22.208** | **29.310** | **22.054** |

cold는 새 서비스의 첫 조회, warm은 같은 서비스의 두 번째 조회다. 매 쌍은 동일 DB bytes로 시작하고 warm에는 직전 query 1행이 남는다. OS 캐시 cold는 주장하지 않는다. 복사·서비스 초기화·사전 hash·사후 artifact 기록은 query 밖이다. 측정 중 다른 검사나 제품 수정을 병행하지 않았다. 원시 배타 합계 오차는 모든 조회에서 0초다. 전후 측정 시점은 다르며 수정하지 않은 구간의 편차를 개선으로 해석하지 않는다. 두 쌍의 제한된 관측으로 통계적 유의성·다른 자료의 상한을 주장하지 않는다.

기존·새 모든 조회에서 `build=1`, `chunks=1`, `source_context=3`이다. build 포함시간은 기존 cold 7.347/7.439초·warm 7.570/7.601초에서 새 cold 0.148/0.145초·warm 0.145/0.146초였다. 별도 전체 그래프 capture의 단발 시간은 진단용으로만 보존하고 위 실제 조회 시간과 혼합하지 않았다.

측정 process의 peak RSS는 초기화와 두 query를 포함한다. cold 최대 6,025,150,464→5,991,415,808 bytes(-32.2 MiB), warm 최대 6,176,604,160→6,118,539,264 bytes(-55.4 MiB)였다. 세부 메모리 원인·OS 반환·동시 요청 메모리·모델 로드 포함 메모리는 측정하지 않았다. 후보 목록의 수명은 build 호출 안이지만 임의 입력의 메모리 상한을 보장하지 않는다.

## 전체 동등성과 검사

실제 snapshot을 원래 제품의 `concept_read_view`로 읽고 수정 전 build를 한 번 저장한 뒤 같은 snapshot으로 새 build를 실행했다. 8,715노드·24,697 keyed edge·7,998 encoder edge·3,728passage 모두 일치한다. graph attrs, ordered nodes, keyed edges와 attrs, adjacency 순서, 반환 edges, passage dict/claim_ids, ignored를 **제외 필드 없이** 비교했다. 양쪽 전체 SHA256은 `b88c50184ccd502992acb7d0ff978af2e836acb99b654640c33a0ba0c5859a30`다.

frozen 원 build와 합성 differential 22건도 전체 직렬화/순서/예외가 일치했다. 같은 block ID의 다른 source/version/parse, parse 누락과 명시적 None, 겹침과 인접 구간, 중복 claim ID·ref·node claim, 동일 passage ID 덮어쓰기, 분류·부채비율 행의 구간 제한, entity/entity_event/full, unlinked/legacy, 빈 snapshot과 변경된 snapshot을 확인했다. 기존 실제 표 행 fixture와 reviewed-evidence 검사까지 **124개 통과**다.

최초 새 검사에서는 event/concept successor까지 passage 순서로 간주한 기대값 오류 4건이 있었다. 제품 수정 전에 passage successor만 비교하도록 고쳐 원 build에서 7개가 통과했고, 이후 3개 검사를 추가했다. 실패 XML·수정 후 XML 모두 보존한다. semantic 실패나 새 평가 시도로 계산하지 않는다. 기존 max6 실패 계보를 유지하며 새 의미 실험은 없다.

전체 saved run·result·response는 네 쌍 모두 정규화 후 0 diff다. retrieval 12개, source_context 33개, passage index 3,728개/848,607 UTF-8 bytes, messages·schema·순위·선택 근거·답변·인용·`succeeded/answered` 저장 상태를 보존했다. 새 query 행 외 모든 기존 DB 행과 다른 table도 일치한다. `answered`는 기존 형식·근거 참조 검사 상태이며 의미 정확성을 보증하지 않는다.

시간 제외는 `run.started_at`, `run.finished_at`, `run.metrics.elapsed_s`, `run.graph_retrieval.elapsed_s`, `run.graph_retrieval.index_elapsed_s`, `run.units[*].started_at`, `run.units[*].finished_at`의 7종뿐이다. 각 새 query/request ID만 위치/stage별 표식으로 바꿨다. source/target/claim/version ID와 모든 cache 필드, provider response의 과거 시간·parsed payload는 유지했다. 재생 usage/elapsed를 새 모델 비용으로 합산하지 않는다.

## 남은 범위와 근거

이번 범위는 완료했다. 남은 전체 조회 약 22.1초 중 source 복원·문맥·직렬화 약 10.6초와 미분류 약 7.0초가 관측된다. 다음 작업은 조정 담당 채팅이 전체 run 상태 읽기 또는 선택별 문맥 조립 중 범위를 정한 뒤 별도 비교로 판단하는 것이다. 이번에는 그 어느 쪽도 수정하지 않았다. #660 전체는 미완료로 open 유지하며 현재 사용자 결정이 필요한 사항 없음.

원본 DB·paused DB·407개 frozen 코드·이전 결과/기각 실험·원래 작업트리·기존 서버를 보존했다. 실제 새 모델·전체 평가·장기 구축 재개·새 이슈/PR·merge·배포는 실행하지 않았다. raw/DB/원문 snapshot은 Git에 포함하지 않는다.

보존 근거 루트는 `/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_graph_address_join_v1/`다.

- [실제 원 build capture](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_graph_address_join_v1/before_graph_receipt.json), [새 전체 그래프 동등성](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_graph_address_join_v1/after_graph_receipt.json), [합성 22건](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_graph_address_join_v1/synthetic_equivalence.json)
- [시간·호출·RSS 집계](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_graph_address_join_v1/measurement_summary.json), [반복 1 전체 저장 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_graph_address_join_v1/normalized_comparison_repeat1.json), [반복 2 전체 저장 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_graph_address_join_v1/normalized_comparison_repeat2.json)
- [116개 검사](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_graph_address_join_v1/address_join_tests.xml), [reviewed evidence 8개](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_graph_address_join_v1/reviewed_evidence_tests.xml), [원본·frozen·서버 보존](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_graph_address_join_v1/preservation_after.json)
