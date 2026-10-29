# 민원 워크벤치 분리와 지식 전용 실행 경계 (2026-10-29)

## 목적·기준

AsterGraph의 현재 범위는 기업 지식 워크벤치다. 민원 화면만 숨기면 API 시작 시 스케줄러·민원 엔진·Chroma 의존성이 계속 로드되므로 실행 경계와 전용 부속 자료를 함께 분리했다.

- 기준 main: `f7548838f6e3d58698d986339bbc26ef9a07e2f3` (PR #675)
- 작업 브랜치: `codex/retire-complaint-workbench`
- 독립 민원 저장소: `/Users/hyeongi/projects/Civil-Complaints-Workbench`
- 독립 저장소 커밋: `ac4f56526851491828ef57c74f27194f26480592`
- 독립 저장소 기준 태그: `split-base/astergraph-f7548838`
- 상세 삭제·원본 blob 대응: [파일 목록](complaint_workbench_retired_files_20261029.json)

독립 저장소는 Git 객체를 공유하지 않는 클론이며 원격을 연결하지 않았다. 현재 작업 트리에는 민원 기능을 남기고 회사 지식 화면/API/연구를 제외했다. 이전 Git 이력에는 분리 전 전체 코드가 보존된다. 원본 DB·`.env`·미추적 파일·실행 서버는 복사하거나 변경하지 않았다. 새 원격 저장소 공개, PR 병합·배포는 이번 범위가 아니다.

## 제거와 보존

- 제거: 민원 선택/처리/통계/Intelligence 화면, 전용 API·스케줄러, 수집·구조화·부서/긴급도·민원 검색/생성/평가 엔진, Streamlit UI.
- 전용 부속: 민원 검사·seed/평가 자료·설정·연구 출력·설계/운영 문서를 독립 민원 저장소에 남기고 AsterGraph의 현 트리에서 제거했다. 삭제 파일 879개 모두 독립 저장소의 현재 트리에 존재한다. 민원 `generation/service.py`에서 회사 지식 전용 호환 메서드만 제외했으며 원형은 기준 태그에 있다.
- 유지: `app/knowledge`의 지식 처리, 원문·버전·검수/사용 상태·검색·저장 답변, 회사 지식 연구 329개 파일, `configs/knowledge`, 원본 실행 DB·실패 계보. 과거 자료에서 민원·버스라는 말이 나온다는 이유로 회사 지식 실험을 삭제하지 않았다.
- 화면 `/`는 `/knowledge`로 이동한다. 민원 화면/메뉴와 replay 초기화 스크립트는 제거했다.
- 활성 문서·환경 예제를 지식 제품 기준으로 갱신했다. 과거 회사 지식 설계에 있던 민원 연결은 현재 인도 요구가 아니다. Global 검색은 범위 밖으로 유지한다.

## 공용 코드의 최소 분리

| 공용 연결 | 변경·보존 |
|---|---|
| 모델 주소 검사 | 민원 생성 service에서 `generation/endpoint.py`로 함수 그대로 이동. loopback·HTTP·자격증명/경로 금지 검사 유지 |
| 모델/토큰 계산 | 기존 model client와 입력 계수는 주소 검사 import만 변경. 상한·계수·출력 예약 변경 없음 |
| 한국어 BM25 | 민원 Chroma 로더에서 `retrieval/tokenization.py`로 두 함수·품사 집합 그대로 이동. 지식 `FrozenIndex`의 import만 변경 |
| 그래프 점수 | 기존 RRF·기본 타입·공용 평가 도구 유지. 점수식·순서·한도 변경 없음. 사용자가 없어진 민원 평가셋 어댑터만 제거 |
| 설정 | 지식·공용 설정 유지. `STRUCTURING_MODEL`은 지식 구축에 쓰이는 기존 이름이므로 보존. 민원 scheduler/Chroma/PII/운영 QA 설정 제거 |

삭제된 민원 전용 직접 의존성: Python `altair`, `blinker`, `chroma-hnswlib`, `chromadb`, `ko-pii`, `kss`, `pydeck`, `plotly`, `streamlit`; FE `leaflet`, `react-leaflet`, `@types/leaflet`. 공유 설치 환경을 uninstall하지 않았다. 남은 전이 의존성의 전면 재고정이나 모델 버전 변경은 수행하지 않았다.

## 검증

새 제품 모델·임베딩·선택·QA 호출은 **0회**다.

| 대상 | 확인 결과 |
|---|---|
| 독립 민원 저장소 | API import/라우트 39개·지식 라우트 0개, backend 10개·FE 108개 검사 통과, 화면 build 통과 |
| 공용 분리 | 경계 검사 126개 통과. 이전 함수와 이동 함수의 AST 동일 확인 |
| 지식·공용 회귀 | 367개 통과. 네트워크 연결을 차단한 검사에서 모델·용량·검색·정상 근거·저장/재조회·소스 조건·상태 보존 확인 |
| 최종 설정/평가 경계 | 15개 재확인 통과 (위 검사와 중복이므로 합산 성과로 쓰지 않음) |
| 지식 FE | 8개 파일/65개 검사 통과, Next.js webpack build 통과. 결과 라우트 `/`, `/knowledge`와 not-found |
| 실제 HTTP | 별도 uvicorn·Next 서버 시작. 새 CSV 등록·parse·구간/원문 근거 조회 후 API 재시작. 버전·구간·raw·인용 재조회 값 일치. `/` 307→`/knowledge`, 지식 화면 200, 민원 화면/API 404 |
| 정적 경계 | 잔존 내부 모듈 import 누락 0, Python compileall 통과, diff 공백 오류 없음, 회사 지식 연구/설정 diff 없음 |

HTTP 검사 run ID: `complaint-split-http-20261029-v2`. parse run: `7a1070e10d624c48a8f69dde8fc15e66`. 별도 DB: `/Users/hyeongi/.codex/artifacts/complaint-workbench-split-20261029/runtime-v2/knowledge.db`. 실제 저장 parse metrics의 `llm_calls=0` 확인. 사용한 검사 서버만 종료했다.

첫 HTTP 검사에서는 검사 스크립트가 기존 API의 `run_id`를 `id`로 잘못 읽어 중단됐다. 제품 POST는 200이었으며 검사 스크립트만 수정했다. 첫 DB·로그도 보존했다. 이는 제품 회귀나 모델 실패의 재시도가 아니다.

전체 검사 1,899개 수집으로 import 연결을 확인했으나 전체 의미 평가·전체 모델 실행을 반복하지 않았다. 위 검사는 코드 분리와 저장 계약의 회귀 확인이며 검색/답변 품질 개선이나 M03 의미 문제 해결의 증거가 아니다.

## 복구·후속

삭제 파일은 파일 목록의 기준 SHA/blob와 독립 민원 저장소에서 복원 가능하다. 현 main의 Git 이력·보존 태그를 재작성하지 않았다. 실행 자료·기존 브랜치·서버와 main 세션의 미완료 연구는 유지했다.

검증된 삭제를 main 대상 PR 하나로 검토한다. 병합 전까지 원격 main은 그대로다. 독립 민원 저장소의 신규 원격 공개는 별도 요청 범위다. 현재 사용자 결정이 필요한 사항은 없다.

로컬 상세 증빙: `/Users/hyeongi/.codex/artifacts/complaint-workbench-split-20261029/` (`STEP1.json`, `STEP2.json`, `preservation-check.json`, `STEP5-http-v2.json`, 각 검사 로그).
