# 변경되지 않은 관계 입력의 임베딩 재사용 — 2026-10-16

## 범위와 판정

같은 서비스에서 관계 그래프 일부가 바뀌었을 때 **정확히 같은 문자열의 수치 벡터만 재사용**한다. NAV01 고정 자료에서 관계 입력 7,998행 중 새 문자열 3개만 실제 계산하고 7,995행을 재사용했다. 상위 관계·최종 검색·필수 문맥·실제 필터/QA 요청은 저장 기준선과 같았다. 이 관찰은 이번 제품 변경의 채택 근거이며 일반 검색 품질 향상이나 새로운 의미 판정의 근거가 아니다.

기반은 `8d851cfd65767dc44ad9a5ec4004e4ad4da4d451`, 별도 브랜치는 `codex/knowledge-edge-vector-reuse`다. 최신 main `35f97608ec9dcb9e65ef701d60ebebe2c2f4464e`와 비교해 중복 구현할 입력별 캐시가 없음을 확인했다. 기존 통합·F3 frozen 실행·원본 DB·기각 실험은 수정하지 않았다.

## 제품 변경과 재사용 계약

기존 `retrieve`는 원문 index key와 전체 edge 목록을 함께 키로 하여 관계 행렬 하나를 저장했다. 개념 관계 일부만 달라져도 전체 7,998입력을 다시 계산했다. 이제 관계 호출에만 `embed(..., service=service)`를 전달한다. 정확 문자열의 첫 출현 순서로 새 입력을 계산하고, 입력 순서·중복 행·float64 shape를 복원한다. 관계 ID·출처·조건·버전·상태·PPR/순위·모델 메시지·지식 항목은 병합하거나 변경하지 않는다.

재사용은 같은 서비스와 같은 로드된 model/tokenizer 객체, device·parameter dtype·최대 길이·출력 차원·truncate 설정·기본 prompt 설정에 한정한다. `normalize_embeddings=True`, 기본 float32 encode, task/prompt 없음과 float64 반환은 유지한다. 제품의 `encoder()`는 process 단위 무인자 `lru_cache(maxsize=1)`이며 서비스 생애 중 모델을 교체하는 API는 없다. 모델 재로드·프로세스 재시작·비교 설정 변경에는 기존 캐시를 재사용하지 않는다. 장기 디스크 재사용 계약이나 이전 서버의 캐시 객체 마이그레이션은 추가하지 않았다.

캐시 hit도 기존 입력 길이 검사를 거친다. 누락·비유한·차원/반환 dtype/정규화 불일치 벡터는 재사용하지 않으며, 실패하거나 불완전한 새 batch를 부분 저장하지 않는다. 현재 관계 풀의 벡터만 남기고 배열 보유 예산은 64 MiB다. 이는 문자열·모델·임시 행렬을 포함한 **총메모리 상한이 아니다**. 원문 구간과 query의 제품 임베딩 동작은 변경하지 않았다.

실제 실행의 로컬 모델은 BGE-M3 revision `5617a9f61b028005a4858fdac845db406aefb181`, CPU float32, 최대 8,192 token, 출력 1,024차원이다. 로컬 모델·tokenizer 파일 hash를 기존 저장 계약과 실행 전에 한 번 대조했다. 이번 runtime은 torch 2.5.1 / sentence-transformers 3.4.1 / transformers 4.46.3 / tokenizers 0.20.3 / numpy 1.26.4다. 과거 기준선의 package version은 별도 기록이 없어 동일하다고 단정하지 않는다. 제품 캐시는 같은 로드 객체 안에서만 유지하며 매 조회마다 모델 파일 hash를 다시 계산하지 않는다.

## 고정 자료와 실제 비용

parent `9c938e8f67594740867bf757868e2262`, 기존 child `1939ac0efc174b00a4b076ab52c57557`, F3 child `eddddac3dd4f4cca99c84fb33d6d3547`의 같은 NAV01 질문을 사용했다. 전체 graph edge는 **24,697개**, encoder relation pool은 **7,998행**, 원문 passage는 **3,728개**다. 양 arm의 모든 관계 입력 hash와 순서는 저장 v3 기준선과 정확히 같았다. 각 arm의 고유 문자열은 7,337개, 공통 7,334개이며 F3에 새로 생긴 문자열은 다음 3개다.

- `Digital 선박 has_concept 품목명`
- `Digital 선박 has_concept 기술분야`
- `Digital 선박 has_concept 혁신성장분야`

전체 기준선을 불필요하게 다시 계산하지 않았다. 사전에 고정한 규칙은 **기존 순서 행렬에서 같은 문자열의 첫 저장 벡터 선택**이다. 모든 기준선 vector 파일의 hash·shape·float64·유한 값·정규화를 먼저 확인했고 첫 벡터가 유효하지 않으면 중단하도록 했다. old-cold는 이 행렬을 제품 cache miss 경로에 복원한 것이며 native cold 실행이 아니다. 원문 passage와 query도 정확 입력 hash에 해당하는 저장 벡터를 복원했다.

| 제품 관계 경로 | 관계 행 수 | 제품 cache miss 고유 입력 | 실제 새 encoder 입력 | 재사용 행 | 제품 embed 전체 시간 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 기존 child, cold artifact 복원 | 7,998 | 7,337 | 0 — 저장 벡터 복원 | 0 | 3.156185초 |
| F3로 변경한 warm | 7,998 | 3 | **3** | **7,995** | **0.472333초** |
| 같은 F3 graph의 warm | 7,998 | 0 | **0** | **7,998** | **0.345717초** |

제품 embed 시간은 입력 길이 검사·벡터 유효성 검사·순서 복원을 포함하고 외부 vector 파일 저장/hash I/O를 제외한 경계다. cold artifact 복원에는 새 process의 모델 로드 2.780386초가 포함됐다. 실제 changed-warm encoder는 **1회·3입력·0.132804초**였다. 기존 v3 F3 arm에서는 같은 7,998입력을 실제 처리한 embedding 함수 시간이 127.171421초였으나 다른 시점의 저장 관측과 이번 결과를 일반적인 속도 개선율로 환산하지 않는다.

같은 graph의 기존 전체 행렬 hit는 입력별 길이·벡터 검사를 반복하지 않았다. 이번 same-warm은 실제 새 계산 0이어도 0.345717초의 CPU 부가비용이 있다. 같은 graph 반복 조회의 속도 향상을 주장하지 않는다. 보유 배열은 이 자료에서 60,104,704 bytes였다. 전체 native cold 7,337입력의 시간·품질은 재실행하지 않았다.

첫 계측 시도 v1은 실제 cold probe **1회·2입력·0.159420초**가 반환된 직후 logger의 `kind` 인자 충돌로 중단됐다. cache 반환까지 성공한 실행으로 세지 않았다. 모델 로드 3.545663초·실패 코드·비용·원본 hash를 보존했고 같은 probe를 다시 계산하지 않았다. v2는 logger 경계와 시간 계측만 수정했으며 제품·모델·입력·질문은 같았다. 두 시도를 합한 신규 실제 encoder 비용은 **2회·5입력·0.292224초**이고 두 process의 모델 로드 비용은 별도다. 새 의미 조정이나 기존 최대 6회 계보의 초기화는 없다.

새 LLM 호출은 **0회**다. old-cold / changed-warm / same-warm의 실제 생성 요청에서 request ID를 제외한 모든 필드, 특히 messages와 schema가 저장 기준선과 정확히 같은 경우에만 필터·QA 응답을 각각 재생했다. 총 6개 응답 재생이며 신규 생성·품질 검증이 아니다. 재생한 response를 통과한 run의 `metrics.llm_calls`·`model_total_s`에는 과거 호출 수와 시간이 남아 있으므로 이번 물리적 비용으로 더하지 않는다.

## 수치 차이와 의미·선택 보존

| 비교 | bit 차이와 최대 절대오차 | 실제 선택 영향 |
| --- | --- | --- |
| 기존 child 중복 입력의 첫 벡터 공유 | 352/7,998행, `2.384185791015625e-07` | 상위 30 관계·선택 간선·seed/PPR·전체 순위·최종 검색 모두 동일 |
| changed-warm 대 저장 F3 전체 행렬 | 1,463/7,998행, `2.7194619178771973e-07` | seed 점수 최대 `3.5443206436447383e-07`, PPR 점수 최대 `1.1680658458697313e-10` 차이. seed 노드·상위 30·dense/PPR 순서·최종 선택은 동일 |
| 새 3문자열의 native batch 대 과거 행렬 | 3/3행, `1.4901161193847656e-07` | 위 실제 전체 순위 대조에 포함 |
| cache 재사용 7,995행 / same-warm 전체 행렬 | 이전 제품 cache 벡터와 **bit 동일** / 직전 changed-warm 행렬과 **bit 동일** | 추가 선택 변화 없음 |

세 제품 경로 모두 실제 그래프의 원래 항목·출처·조건·역할·미승인 상태와 passage hash를 보존했다. 두 child의 개념 차이는 원래대로 유지했고, old/F3 사이에 있던 차이를 지우지 않았다. 최종 retrieval 12개와 source_context 33개, 필터/QA 입력·schema·인용이 각자의 저장 기준선과 같았다. 이전 ranking을 강제로 넣지 않고 새 벡터로 유사도·상위 관계·PPR·fusion·선택을 다시 계산했다.

이 결과는 원문 노출 NAV01 한 과제의 회귀 없음이다. F3의 구체 선박 태그 소실, 다른 질문·자료의 적용, 개념화·답변의 새 의미 품질은 추가로 판정하지 않는다. `answered`는 기존 응답 형식·제공 근거 참조 상태이며 승인·정확도 점수가 아니다.

## 남은 시간과 미측정 범위

| 관측 경계 | changed-warm | same-warm |
| --- | ---: | ---: |
| 제품 관계 embed 전체 | 0.472333초 | 0.345717초 |
| retrieve 시작→index 준비 완료 (`index_elapsed_s`, 위 시간 포함) | 25.396600초 | 25.481269초 |
| retrieve 시작→검색 완료 (`elapsed_s`, index 포함) | 27.760934초 | 27.505667초 |
| 전체 `business_use.query` 계측 경계 | 80.917033초 | 81.506503초 |

changed-warm에서는 index 이후 검색까지 2.364335초, retrieve 경계 밖의 query 작업에 53.156098초가 관측됐다. 같은 warm의 경계 밖 값은 54.000835초다. 관계 encoding을 줄여도 이 관측창의 다른 비용은 남는다. index 경계 안의 graph/passage 준비, 경계 밖 전후 처리, DB 읽기·쓰기, 문맥/DOM 준비, 외부 계측의 hash·artifact I/O 기여는 각각 측정하지 않았다. 어느 하나가 81초의 원인이라고 지목하지 않으며 순수 제품 운영 시간이나 새 LLM 시간으로 해석하지 않는다. 추가 전체 실행·계측 프레임워크·성능 리팩터링은 수행하지 않았다.

## 검사와 보존 근거

새 캐시 검사 16건과 제품 호출자 검사 11건을 합한 27건이 통과했다. 캐시의 순서·중복·서비스 범위·모델/설정 무효화·누락/손상/차원 불일치·실패 원자성·배열 예산·길이 검사·서로 다른 출처 항목의 비병합을 확인했다. 기존 stub은 새 keyword `service`만 받도록 좁게 맞췄고 기존 불변성 assert를 삭제하거나 완화하지 않았다. 이 stub 수정 후 해당 호출자 11건을 다시 통과했다. 전체 테스트·26문항·재추출·장기 구축은 실행하지 않았다.

- [기준선 입력·벡터·실행 기록](/Users/hyeongi/.codex/artifacts/source-scoped-knowledge-reuse-20261016/f3_v1/consumer_v1/query_execution_v3/execution_manifest.json)
- [v1 실패와 이미 지불한 비용](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/edge_vector_reuse_v1/finished.json)
- [v2 사전 고정 규칙·입력/hash 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/edge_vector_reuse_v2/prepared.json), [동결 비교 helper](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/edge_vector_reuse_v2/evaluate.py)
- [현재 모델 계약](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/edge_vector_reuse_v2/model_contract.json), [실제 encoder 비용](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/edge_vector_reuse_v2/encoder_calls.json), [제품 embed 전체 시간](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/edge_vector_reuse_v2/product_embedding_calls.json)
- [세 경로의 순위·근거·요청 대조](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/edge_vector_reuse_v2/comparisons.json), [벡터 bit 보존](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/edge_vector_reuse_v2/vector_preservation.json), [실제 요청 동등성·응답 재생](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/edge_vector_reuse_v2/replay_requests.json)
- [원본/paused/frozen DB·raw·기준선 벡터 hash 보존과 종료](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/edge_vector_reuse_v2/finished.json), [좁은 호출자 11건](/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/edge_vector_reuse_v2/strict_stub_callers.xml)

비교는 별도 DB 사본에만 새 조회 기록을 저장했다. 원래 parent·두 child payload와 원본·paused·F3 DB/기존 frozen helper·raw·기준선 벡터 hash는 그대로다. 기존 F2·F4-a 미채택과 장기 실행 중단을 유지하며 PR 병합·배포·새 이슈를 수행하지 않았다. 후속으로는 이 결과와 별도 F3 감사를 검토한 범위만 통합하며, 현재 사용자 결정이 필요한 사항 없음.
