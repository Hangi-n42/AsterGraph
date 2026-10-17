# NAV01 조회 준비의 반복 계산 제거 — 2026-10-16

## 확인 범위와 결과

기존 [#660](https://github.com/Hangi-n42/AsterGraph/issues/660)의 남은 조회 시간을 실제로 나눠 보고, 확인된 두 반복만 수정했다. 같은 저장 자료·벡터·응답을 사용한 경량 계측에서 cold 평균 **78.838→37.802초**, warm 평균 **81.904→37.993초**였다. 모델 대기를 제외한 고정 재생 조건의 결과이며 실제 새 QA 속도나 품질 향상으로 일반화하지 않는다.

기준 코드는 `0f72f88b271f9c6766a83d9eab2691e217cc1b74`, 브랜치는 `codex/knowledge-edge-vector-reuse`다. parent `9c938e8f67594740867bf757868e2262`와 F3 child `eddddac3dd4f4cca99c84fb33d6d3547`의 같은 NAV01 질문을 사용했다. 원문 3,721블록·3,728passage, 전체 graph 24,697edge·encoder pool 7,998행을 구분한다.

## 측정 경계

표준 cProfile 1회는 원인 진단에만 사용했다. 그 실행의 173.332초는 profiler 부하를 포함하며 아래 경량 성능표와 섞지 않는다. 이후 수정 전후 각각 독립 process 2개에서 같은 DB 복사본으로 cold/warm 한 쌍을 실행했다. 경량 조회는 총 8회이며 질문 전수평가가 아니다.

- cold는 새 서비스와 빈 서비스 캐시의 첫 조회다. OS 파일 캐시·모듈 내부의 모든 상태까지 cold라고 주장하지 않는다.
- warm은 같은 서비스의 두 번째 조회다. 직전 조회가 저장한 새 run 1행이 남는다. 이 경계는 수정 전후 동일하고 각 쌍의 시작 DB는 byte/hash가 같다.
- DB 복사·서비스 생성·벡터/응답 파일 검증·최종 결과/hash 기록은 query 구간 밖이다. query 안의 정확 입력 대조·벡터 복원·응답 재생은 별도 replay 구간으로 분리했다.
- 주요 함수 wrapper의 중첩 경계로 배타시간을 분할했다. 함수의 포함시간은 자식 비용과 겹치므로 다시 합산하지 않는다. 각 경량 실행의 배타시간 합계와 전체 경과의 차이는 원시 수치에서 0초다.
- DB API·SQLite·JSON 모듈을 대체하지 않았다. 읽기 항목은 `repository.get`으로 잡은 부분이며, 직접 SQL·일부 직접 역직렬화·commit은 미분류에 남을 수 있다. 표의 DB 읽기 값을 DB 전체 비용으로 해석하지 않는다.

전후 helper SHA256은 `4616e38ea213f598465506219616ce00c8c7e453796d632ab1beec9ee6ed7d2d`, 시작 DB SHA256은 `6dcba12174e892fa54c4666438cde09a126a75a5990e1d926ef6e5ab7738ca07`로 모두 같다. `edge_vector_reuse_v2`의 저장 벡터와 응답은 실제 전체 입력 순서/hash 및 messages·schema·한도 일치를 확인한 경우에만 복원했다. 순위·PPR·RRF·원문 복원·문맥 조립·취소 확인·DB 저장은 제품 경로를 실행했다. 불일치를 정상으로 바꾸는 fallback은 없다.

## 확인된 원인과 최소 수정

cProfile에서 `autoschema.chunks`는 3회 포함 106.439초였다. 그 안의 `list_parents`는 11,163회 포함 77.610초, 같은 원문 경로의 `list_text_parent`는 42,809,763회 호출됐다. 같은 group의 조상 후보 자격은 실제 target에 따라 바뀌지 않는데도 매 target마다 전체 pool을 다시 판정했다. 이 포함시간들은 서로 겹친다.

`graph_retrieval.build`는 같은 요청에서 2회, 포함 36.862초였다. 첫 결과로 후보를 만든 뒤 `retrieve`가 같은 snapshot을 다시 구성했다. 이 두 반복을 각각 다음처럼 줄였다.

같은 진단의 DOM `for_service`는 포함 9.982초(`serialize` 9.532초 포함)였다. 이번에는 이 하위 구현을 변경하지 않았다.

1. `chunks`는 group마다 기존 `list_parents` 규칙으로 어차피 제외될 항목만 한 번 선별한다. 실제 자료는 3,721개 중 후보 114개다. 기존 helper에 같은 순서의 작은 후보 풀을 주며, 실제 조상·source/version·ID·조건·span 판정은 그대로다. 전역 캐시나 목록 규칙 재설계는 추가하지 않았다.
2. source-run query의 첫 `build` 결과를 같은 요청의 `retrieve`에 전달한다. 검색 뒤 graph/edges tuple 참조를 해제하고 BM25에서도 불필요하게 보유하지 않는다. snapshot 조회와 기존 4인자 호출은 기존 경로를 유지한다.

`source_context`와 `chunks` 호출은 여전히 각 3회다. 선택대상별 supports_context_ids·locator·표 행·주석을 조립하는 전체 문맥 결과를 공유하거나 임의로 필터하지 않았다. DB 캐시·저장 생략·새 설정·모델 변경도 없다. `build`와 순위 계산이 원래 그래프·parallel 관계·passage 순서를 변경하지 않는지도 검사했다.

`retrieve` 내부의 두 번째 build를 없앴으므로 기존 `graph_retrieval.index_elapsed_s/elapsed_s`의 포함 경계는 달라진다. 속도 비교는 이 trace 단독 값이 아니라 같은 외부 query·stage 경계로 했다.

## 실제 경량 측정

| 상태 | 수정 전 두 실행(초) | 수정 후 두 실행(초) | 평균 전→후(초) |
| --- | --- | --- | --- |
| cold | 79.253, 78.424 | 37.972, 37.632 | 78.838→37.802 |
| warm | 82.361, 81.446 | 38.050, 37.936 | 81.904→37.993 |

| 배타 구간 평균(초) | 기존 cold | 수정 cold | 기존 warm | 수정 warm |
| --- | ---: | ---: | ---: | ---: |
| get 읽기·역직렬화 — DB 전체 아님 | 1.474 | 1.680 | 1.760 | 1.780 |
| graph·index·vector 연결·순위 | 17.890 | 10.298 | 17.968 | 10.247 |
| source 복원·문맥 선택·직렬화 | 52.174 | 18.432 | 54.491 | 18.426 |
| save로 포착한 저장 | 0.232 | 0.238 | 0.238 | 0.228 |
| 정확 입력 대조·vector/response replay | 0.012 | 0.012 | 0.010 | 0.009 |
| 직접 SQL·역직렬화·commit 등을 포함할 수 있는 미분류 | 7.057 | 7.142 | 7.437 | 7.303 |
| **전체 query 경계** | **78.838** | **37.802** | **81.904** | **37.993** |

표시값은 반올림했다. 함수 계층의 포함 호출 수는 build 2→1, chunks 3→3, source_context 3→3이며 get 13, save 11은 전후 같다. save 수에는 상위 `business_run.save`와 내부 `repository.save`가 함께 들어 있어 물리적 SQL 쓰기 11회라는 뜻은 아니다. DB 저장을 줄여 얻은 효과가 아니다.

원래 전체 3,728bundle의 30,974,330 UTF-8 bytes는 수정 전후 byte 동일이며 SHA256은 `96a856860adb12a55797787740b9b9878ab4e548deaf3a0d30027cc3843bcb60`이다. 각 최종 입력은 retrieval 12개·source_context 33개, passage index 3,728개/848,607 UTF-8 bytes다. 새 run의 실제 저장 JSON은 약 11.22 MB이며 시간 문자열·새 ID에 따른 몇 byte 차이만 있다. 이는 논리 payload 크기이며 물리적 디스크 I/O 총량이나 반복 UPDATE의 누적 쓰기량이 아니다.

측정 process의 관측 peak RSS는 초기화와 두 query를 포함한다. warm 최대는 기준선 6,122,487,808→수정 후 6,138,085,376 bytes로 약 14.9 MiB 높았다. 이 증가의 세부 원인은 분해하지 않았으며 메모리 절감으로 보고하지 않는다. 새 지속 캐시는 없고 공유 graph의 요청 변수 참조는 검색 직후 해제하며 조상 후보 목록은 `chunks` 지역 변수로만 둔다. 이 관측으로 다른 입력의 메모리 상한을 보장하지 않는다.

## 저장 결과·계약 보존

두 반복의 cold/warm 네 쌍에서 전체 저장 run·반환 result·모든 response는 정규화 후 차이가 0개다. 비교에서 제외한 필드는 다음 7종뿐이다.

- `run.started_at`, `run.finished_at`, `run.metrics.elapsed_s`
- `run.graph_retrieval.elapsed_s`, `run.graph_retrieval.index_elapsed_s`
- `run.units[*].started_at`, `run.units[*].finished_at`

각 새 query ID와 그 query에서 생성한 unit request ID만 위치/stage별 고정 표식으로 바꿨다. 원래 source·target·claim·version ID는 유지했다. **cache 통계 제외는 0개**이며 provider response의 기존 elapsed·parsed payload도 비교했다. 순위·선택 간선·근거·메시지·schema·답변·인용과 `succeeded/answered` 저장 상태가 같다. 새 query 행 외 모든 기존 row와 다른 table도 원본 복사 기준과 byte 동일하다. `answered`를 의미 정확도나 업무 승인으로 해석하지 않는다.

공용 경계 검사 58개와 기존 snapshot/answer 호출자 43개, 합계 101개가 통과했다. 목록의 빈 경로·중첩 list·동명·다른 source/version·표/주석·continuation·용량 실패·독립 요청·graph 비변형을 확인했다. 수정 전 5개 작은 검사 중 예상한 3개 실패와 수정 직후 11개 통과 기록도 보존하되 101에 중복 합산하지 않았다. 새 추출·QA·embedding 실행과 LLM/embedding 모델 로드는 모두 0회이며 profile 1회와 경량 8회의 저장 응답 재생은 새 모델 품질 실험이 아니다.

## 남은 비용과 범위

수정 후에도 이 조건의 조회는 약 38초다. graph/index/rank 약 10초, source 복원·문맥 약 18.4초와 기타 비용이 남는다. DOM 처리 등 하위 기능의 수정 후 개별 기여는 이 경량 경계만으로 전부 분해하지 않았다.

별도 진단에서 활성 실행 확인용 `SELECT payload FROM runs` 뒤의 Python genexpr는 39 primitive call/포함 6.912903초이며, 그 안의 `json.loads` 직접 38회가 포함 6.012225초였다. 이는 전체 run payload를 decode하는 확인된 잔여 경로다. 경량 미분류 약 7초와 겹칠 수 있으나 profile 수치를 경량 표에 다시 더하지 않는다. 이 확인을 DB 상태 캐시나 활성 실행/취소 guard 축소로 확대하지 않았다.

다른 질문·자료·실제 모델 대기를 포함한 전체 서비스 성능과 의미 품질 일반화는 미검증이다. 원본 DB·407개 frozen 코드·기존 벡터/응답·중단된 장기 구축과 기존 서버를 보존했다. 전체 #660은 미완료로 open 유지하며 추가 전체 실행·새 이슈/PR·merge·배포는 수행하지 않았다. 현재 사용자 결정이 필요한 사항 없음.

## 보존 근거

로컬 근거 루트는 `/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_stage_profile_v1/`다.

- [표준 profile·포함 함수](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_stage_profile_v1/diagnostic_v1/profile_top.json), [측정 집계·helper/DB hash](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_stage_profile_v1/measurement_summary.json)
- [반복 1 전체 저장·응답·ledger 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_stage_profile_v1/normalized_comparison_repeat1.json), [반복 2 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_stage_profile_v1/normalized_comparison_repeat2.json)
- [직전 전체 bundle 계약](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_stage_profile_v1/before_bundles_receipt.json), [수정 후 byte 동일](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_stage_profile_v1/after_bundles_receipt.json)
- [공용 경계 58개](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_stage_profile_v1/related_boundary_tests.xml), [기존 호출자 43개](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_stage_profile_v1/snapshot_compatibility_tests.xml), [원본·frozen·서버 보존](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_stage_profile_v1/preservation_after.json)

동결 helper·cProfile 원본·각 독립 복사 DB·query run·입력/응답 대조는 같은 근거 루트에 남겼으며 raw/DB를 Git에 새로 포함하지 않았다.
