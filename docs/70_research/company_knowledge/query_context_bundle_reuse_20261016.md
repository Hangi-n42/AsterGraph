# 요청 안의 공통 원문 묶음 재사용 — 2026-10-16

## 범위와 결과

기존 [#660](https://github.com/Hangi-n42/AsterGraph/issues/660)의 남은 문맥 비용 중 **같은 요청의 순수 `chunks(target_chars=1)` 계산만 3회→1회**로 줄였다. 선택별 `source_context` 조립은 3회 그대로다. 고정 NAV01 저장자료 재생에서 전체 평균은 **37.897→29.128초**, 문맥 구간은 **18.429→10.458초**였다. 새 LLM/embedding 호출·모델 로드는 0회이며 모델 대기를 포함한 실제 QA 성능이나 의미 품질 향상으로 해석하지 않는다.

기준 코드는 `c91dbe68e325ed27aebc28b23cc2e690a90f5099`다. parent `9c938e8f67594740867bf757868e2262`, F3 child `eddddac3dd4f4cca99c84fb33d6d3547`, 같은 질문·3,721블록·3,728passage·7,998관계 입력을 사용했다. 전체 graph 24,697edge와 encoder pool을 혼동하지 않는다. graph 주소 조인과 전체 run 상태 읽기는 수정하지 않았다.

## 최소 변경과 수명

`business_use.query`는 source-reader 요청마다 새 lazy 공급함수를 만든다. 이 함수는 같은 snapshot의 blocks/options로 원문 묶음을 한 번 계산하고 같은 목록을 index 준비·passage 선택·최종 답변 문맥에 제공한다. 각 소비자는 선택 대상별 supports_context_ids·span·locator·조건·제목·표·예외·continuation 연결을 새로 조립한다. 전체 문맥 결과를 공유하거나 필터링하지 않는다.

기존 `source_context`·`passage_search_texts`·`select_passages`·`retrieve`의 호출은 선택적 내부 keyword 없이 그대로 쓸 수 있다. 전역/서비스 캐시·설정·프레임워크는 추가하지 않았다. 첫 실제 사용 때 계산하므로 capacity 예외가 기존 retrieval 경계에서 발생하고 `retrieval_failed` 저장을 유지한다. 실패 결과는 메모화하지 않으며 정상 빈 목록은 한 번 계산한다.

공급함수는 run·service·저장 payload에 넣지 않고, 마지막 source_context 직후 QA 전에 요청 변수 참조를 해제한다. 별도 요청이나 변경된 source-run/version/options에는 새 공급함수가 생긴다. 블록·묶음 객체가 바뀌지 않고 각 선택의 문맥 객체가 독립적인지도 검사했다.

## 기준선과 계측 기록 보정

`query_stage_profile_v1/after_repeat1,after_repeat2`는 이번 시작 HEAD의 제품 파일 hash와 모두 같았다. 동일 시작 DB hash `6dcba12174e892fa54c4666438cde09a126a75a5990e1d926ef6e5ab7738ca07`, 같은 ordered vectors·저장 응답·질문을 사용하므로 기존 두 cold/warm 쌍의 전체·배타 시간을 재사용했다. 불필요한 기준선 재실행이나 반복 cProfile은 하지 않았다.

기존 helper에는 `inclusive_calls=clock.calls`가 다음 query에서 같은 dict를 비우고 재사용하는 기록 결함이 있었다. 이 때문에 과거 최종 파일의 cold/warm 포함시간 내역을 독립된 값으로 해석하지 않는다. `query_total_s`와 별도 복사된 `exclusive_s`에는 영향이 없다. 원 helper·기준선은 보존하고 복사본에서 **query clock 종료 뒤의 기록 한 줄만 `deepcopy(clock.calls)`로 수정**했다.

- 원 helper SHA256: `4616e38ea213f598465506219616ce00c8c7e453796d632ab1beec9ee6ed7d2d`
- 기록 보정본 SHA256: `d10e2440c48c59a67c15ebfbeddaf1934b998b805fa7a2e104c53f7cfbee2b22`

두 helper가 같다고 표시하지 않는다. 비교기는 위 단일 기록 변경만 확인한 뒤 기존 기준선과 대조한다. 이 변경은 query 시간 경계·제품 로직·입력 재생을 바꾸지 않는다. 새 실행의 cold/warm 포함 호출 기록은 각각 복사해 보존했다.

## 실제 시간과 메모리

새 실행은 독립 복사 DB 두 개에서 cold/warm 한 쌍씩, 총 4조회다. cold는 새 서비스의 첫 조회이고 warm은 같은 서비스의 두 번째 조회다. 각 쌍은 같은 DB bytes에서 시작하며 warm에는 직전 새 query 1행이 남는다. OS 파일 캐시까지 cold라고 주장하지 않는다. DB 복사·서비스 생성·사전 hash·사후 artifact 기록은 query 밖이다. 정확 vector/응답 입력 대조·복원은 별도 replay 구간으로 잡았다.

| 상태 | 기존 두 조회(초) | 새 두 조회(초) | 평균 전→후(초) |
| --- | --- | --- | --- |
| cold | 37.972, 37.632 | 29.022, 28.870 | 37.802→28.946 |
| warm | 38.050, 37.936 | 29.479, 29.141 | 37.993→29.310 |

| 배타 구간 평균(초) | 기존 cold | 새 cold | 기존 warm | 새 warm |
| --- | ---: | ---: | ---: | ---: |
| repository.get 읽기·역직렬화 — DB 전체 아님 | 1.680 | 1.609 | 1.780 | 1.661 |
| graph/index/rank | 10.298 | 9.921 | 10.247 | 9.870 |
| source 복원·문맥·직렬화 | 18.432 | 10.363 | 18.426 | 10.553 |
| save로 포착한 저장 | 0.238 | 0.224 | 0.228 | 0.223 |
| 입력 대조·vector/response replay | 0.012 | 0.012 | 0.009 | 0.009 |
| 직접 SQL·decode·commit 등을 포함할 수 있는 미분류 | 7.142 | 6.817 | 7.303 | 6.994 |
| **전체 query** | **37.802** | **28.946** | **37.993** | **29.310** |

표는 반올림했고 각 새 조회의 원시 배타 합계 오차는 0초다. 이번 유효한 호출 기록은 cold/warm 모두 `chunks=1`, `source_context=3`, `build=1`이다. 기준선은 직전 시점의 저장 관측이며 변경하지 않은 구간의 차이는 시점·환경 편차를 포함할 수 있다. graph/상태 읽기 자체를 개선했다고 보고하지 않는다. 포함시간을 위 배타 표에 재합산하지 않았다.

측정 process의 peak RSS는 초기화와 두 query를 포함한다. cold 최대는 5,983,338,496→6,025,150,464 bytes(**+39.9 MiB**), warm 최대는 6,138,085,376→6,176,604,160 bytes(**+36.7 MiB**)였다. 원문 묶음은 첫 사용부터 최종 문맥까지 요청 안에서 보유한다. 공급함수의 QA 전 해제는 약한 참조 검사로 확인했지만 RSS의 세부 증가 원인·OS 반환·실제 모델 대기를 포함한 보유 시간·동시 요청 메모리는 측정하지 않았다. 요청 밖에 남는 캐시는 없으며 다른 자료의 메모리 상한을 보장하지 않는다.

## 결과·저장·검사 보존

기존과 새 cold/warm 네 쌍의 전체 saved run·result·모든 response는 정규화 후 **0 diff**다. retrieval 12개, source_context 33개, passage index 3,728개/848,607 UTF-8 bytes와 messages·schema·순위·PPR·RRF·선택 근거·답변·인용·`succeeded/answered` 저장 상태를 보존했다. 새 query 행 외 모든 기존 DB 행과 다른 table도 그대로다.

제외한 시간 필드는 `run.started_at`, `run.finished_at`, `run.metrics.elapsed_s`, `run.graph_retrieval.elapsed_s`, `run.graph_retrieval.index_elapsed_s`, `run.units[*].started_at`, `run.units[*].finished_at`의 7종뿐이다. 각 새 query/request ID만 위치/stage별 표식으로 바꿨으며 source/target/claim/version ID는 유지했다. **cache 필드 제외는 0개**다. provider response의 과거 시간·parsed payload도 그대로 비교했다. 재생된 usage/elapsed를 새 모델 비용으로 합산하지 않는다.

작은 경계 검사 **62개 통과**다. 계산 3회는 수정 전 두 검사에서 재현했다. 중간 19개 검사 중 1개는 멀티버전 source_documents를 평면 context로 가정한 mock 실패였고 실제 `restore_versions`로 맞췄다. 이 실패·수정 기록도 보존했으며 제품 로직을 추가 변경해 통과시킨 것이 아니다. 원문·묶음 비변형, 선택별 독립성, 빈 결과·실패·첫 사용 한도, 별도 요청/변경 source/version/options, QA 전 해제, 기존 caller·활성/취소 상태·실패 저장을 확인했다.

## 남은 범위와 근거

약 29초가 남으며 graph/index/rank 약 9.9초, 문맥 약 10.5초와 전체 run 활성 상태 확인 등 비용을 구분한다. graph 주소 조인·전체 run 상태 읽기·선택별 문맥 조립·DOM 처리의 다음 개선은 이번에 하지 않았다. 실제 새 모델·전체 평가·장기 구축 재개·새 이슈/PR·merge·배포도 없다. #660 전체는 미완료로 open 유지하며 현재 사용자 결정이 필요한 사항 없음.

보존 근거 루트는 `/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_context_bundle_reuse_v1/`다. 원본 DB·paused 실행·407개 frozen 코드·기존 결과·기각 실험·기존 서버를 보존했다.

- [계측 기록 단일 수정·전후 hash](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_context_bundle_reuse_v1/helper_recording_fix.json), [시간·호출·메모리 집계](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_context_bundle_reuse_v1/measurement_summary.json)
- [반복 1 전체 저장 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_context_bundle_reuse_v1/normalized_comparison_repeat1.json), [반복 2 전체 저장 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_context_bundle_reuse_v1/normalized_comparison_repeat2.json)
- [62개 검사](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_context_bundle_reuse_v1/shared_bundle_tests_v2.xml), [원본·frozen·서버 보존](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/query_context_bundle_reuse_v1/preservation_after.json)

각 새 DB·run·질문/벡터/응답 대조·수정한 helper와 비교기는 위 근거 루트에 보존하고 Git에는 raw/DB를 포함하지 않았다.
