# 새 검색의 생략·명시 선택 계약

`POST /api/v1/knowledge/business/search`는 새 검색 실행의 진입부 한 곳에서만 기본값을 해결한다. 검색 알고리즘 기본값은 기존 `hipporag2`를 유지한다. 이는 그래프 중심 개발에 대한 과거 사용자 선택이며 알고리즘 간 품질 우위의 인증이 아니다. 원문 QA 비교와 승인 snapshot 상품 비교는 서로 다른 평가 범위다.

`hybrid_graph` 신규 검색은 API와 직접 서비스 진입에서 DB 쓰기·작업 생성·모델 전송 전에 종료하며 대체 `hipporag2`를 안내한다. 신규 API enum에도 HG를 포함하지 않는다. 기존 `BusinessQuery`의 과거 원문 QA 파싱, 저장 GET·workbench의 당시 모드·답변·인용·검토 상태는 유지한다. 내부 HG 순위 연산은 과거 재현용으로 보존하고 새 실행 경로에서는 사용하지 않는다. standalone Hybrid/BM25/Dense와 공통 후보·선택·PPR·RRF·근거 조립은 변경하지 않는다.

기본값 적용 범위는 `snapshot_id` + `hipporag2` + `full` + `synthesis` + 강제 `requirement_ids` 없음 + graph 경로다. 이 범위에서 생략된 필드만 다음 값으로 해결한다.

| 필드 | 생략 시 |
|---|---|
| `candidate_contract` | `r2_g1_w1` |
| `evidence_union` | `ranked_preserved_claims_v2` |
| `source_citation_contract` | `provided_source_quote_links_v1` |

명시적 `null`은 해당 옵션을 끄고, 명시적 지원 값은 유지한다. 부분 명시도 필드별로 적용한다. 지원하지 않는 조합·값은 기존 요청 검증으로 거부하며 조용히 삭제하지 않는다.

새 화면의 기본 검색은 세 필드를 생략하여 API와 같은 기본값을 사용한다. 화면의 ‘이전 구성’은 기존 동작대로 후보·근거 확장만 끄고 원문 인용 연결을 유지하므로 앞의 두 필드를 `null`, 인용 계약을 `provided_source_quote_links_v1`로 보낸다. 완전한 과거 API 기준선은 세 필드를 모두 `null`로 보낸다. 구형 업무 화면도 같은 서버 진입부를 사용한다.

원문 QA, BM25/Dense/Hybrid, graph 변형, 항목별 답변, 강제 요구, document 기준선에는 기본값을 주입하지 않는다. 해당 경로의 기존 명시 옵션과 검증은 유지한다. 저장 결과 GET·과거 query 파싱·재생·용량 재개에는 기본값을 소급하지 않는다. 저장 데이터는 이동하거나 고쳐 쓰지 않는다.

새 실행의 `query`에 실효값을 저장하고 응답과 저장 실행의 `execution_boundary.query_contracts`, `defaulted_query_fields`에 실제 적용 계약과 생략 때문에 채운 필드를 기록한다. 후보 선택과 주소·literal anchor 연결은 의미 지지 판정이 아니다. 필수 근거가 예산을 넘으면 QA 전에 실패하고, 선택 추가분은 첫 초과에서 직전 입력 상태로 복원한다.

기존 `experimental=true` 진단과 품질 검증 중 안내는 기본 활성화 여부와 별개다. 지원 조합에서 기본 적용되더라도 일반 의미 정확성이나 모든 질문의 품질 향상을 보증하지 않는다.

선별 원본: `01ece0d6`, `b9a109a8`, `c1c231cb`, `428fd6e2`, `32ea9014`, `58952635`, `0fa4eef9`, `a2aaeff2`. 연구 문서·기각 프롬프트·원본 DB·생산 raw는 이 변경에 포함하지 않는다. 부분 재구축·목록 소비·명시 참조 정정은 이 검색 계약에 의존하는 후속 PR에서 다룬다.
