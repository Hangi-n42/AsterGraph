# 스키마 선행 지식 실행 경로 지원 종료

기준일: 2026-10-19. 기준 코드는 제품 PR #669를 병합한 `4334e8f8be65fc82afde791125f55eb73b857682`다. 이 문서는 해당 기준에서 수행한 제거 변경을 설명하며, 별도 검색 실험의 채택이나 의미 품질 개선을 뜻하지 않는다.

## 목적과 보존

현재 제품은 AutoSchemaKG 기반 출처 주장·그래프 구축, 개념화, 업무 검토·부분 수정, 출처 지식 버전, 그래프 검색을 사용한다. 이전의 **온톨로지 스키마 설계 → 승인 스키마에 따른 추출 → 이전 개체·주장 저장소 검색** 실행은 별도 경로다. 두 실행이 한 화면과 API에서 섞이지 않도록 이전 경로를 제거한다.

| 기준 | 역할 |
|---|---|
| `main`의 `4334e8f8` | #669의 채택 제품 변경 7커밋을 병합한 제거 직전 기준. 이후 유지보수까지 포함한 옛 경로를 복원할 때 이 커밋을 사용 |
| `codex/legacy-pre-autoschemakg`의 `c433c7b3` | AutoSchemaKG 전환 이전 `94fee116`에 역사 설명 README를 더한 보존 브랜치. 원격 게시 확인. 최신 구형 경로의 모든 유지보수를 포함하는 브랜치는 아님 |
| `codex/retire-schema-first` | 이번 공통 기능 분리·이전 실행 제거·현재 검색 UI 연결 변경. 별도 PR에서 검토 |
| `codex/retail-source-candidates` | 진행 중인 검색 후보 실험. 이 변경에 포함하거나 실행하지 않음 |

원본 DB, 테이블, 추출·승인·실패 기록, 원시 모델 응답, 과거 보고서, untracked 자료를 삭제하거나 변환하지 않는다. 코드 브랜치는 로컬 DB와 untracked 자료의 백업을 대신하지 않는다. 오래된 로컬 main을 강제 동기화하지 않는다.

## 제거와 유지 경계

| 제거한 실행 | 유지한 현재 기능 |
|---|---|
| `discovery_*`의 온톨로지 발견·설계·검토 | `autoschema.py`, `business_*`의 출처 지식 구축·개념화·검토·수정·부분 재구축 |
| `ontology_*`, `extraction.py`, `extraction_contract.py`, `extraction_store.py`의 스키마 선행 실행 | 원문 등록·버전·파싱·원문 위치·사용 제한 |
| 이전 `search.py`, `search_answer.py`, `snapshots.py` 실행 | `business_use.py`, `graph_retrieval.py`, 업무 지식 snapshot과 워크벤치 |
| 위 실행 전용 UI, 테스트, 평가 실행 스크립트 | 현재 업무 지식 테스트와 공통 원문 구간 테스트, 민원 계층, 과거 상담 A 비교 |

전체 파일 삭제 95건에는 이전 실행 전용 검사와 스크립트가 포함된다. 현재도 필요한 구현을 단순히 파일 이름 때문에 삭제하지 않았다. `test_knowledge_discovery_segments.py`의 공통 구간 검사는 `test_knowledge_source_segments.py`로 옮겼다. 구형 기능의 실행 스크립트와 테스트는 제거 직전 커밋에서 찾을 수 있다. 과거 연구 보고서의 파일 링크·명령은 당시 커밋을 기준으로 해석해야 한다.

## 공통 기능 분리

| 이전 구현 | 현재 구현 | 보존한 계약 |
|---|---|---|
| `discovery_profile.FrozenIndex` | `source_index.FrozenIndex` | 숫자 토큰, rank/search 정렬·분산·중복 처리 |
| `discovery_segments` 및 필요한 profile 함수 | `source_segments` | `source-spans-v3`, 원문 위치, 짧은 참조, 안정 ID와 인용 결합 |
| `SourceMeaning`, `affected_keys`, `remap` | `source_meanings` | 필드·기본값, 전제 의존, 원문 리터럴과 주소 구분 |
| snapshots의 현재 사용 제한 | `availability` | 제한 이력, revision 충돌, 근거·원문 차단 전파 |
| 구형 저장 기록을 읽는 최소 함수 | `legacy_records` | 과거 추출 집계 조회와 구형 근거 의존 읽기. 모델 실행·신규 스키마 생성 없음 |
| `ontology_schema.VersionConflict` | `repository.VersionConflict` | 충돌 시 409 응답 |

이동 함수·클래스 27개의 AST를 비교했다. 22개는 그대로이고 나머지 5개는 이동한 함수·예외 클래스의 참조 경로만 바뀌었다. `SourceMeaning.statement_type`은 제거되는 Relation 모델 참조를 같은 Literal 값으로 직접 표현했다. 검색 순위, 추출 프롬프트, 저장 의미 스키마를 새로 설계하지 않았다.

## API 변경: 기존 클라이언트에 대한 호환성 경계

경로는 `/api/v1/knowledge` 아래 기준이다.

- 유지: `/sources`, 원문 버전·raw·blocks, `/evidence/{id}`, 파싱용 `POST /runs`, 실행 조회·취소, `/requirements`, `/business/*`, `/workbench/*`, `/availability`.
- 제거: 이전 discovery 목록 `GET /runs`, `/discovery/*`, `/ontology-cqs`, `/ontologies/*`, `/candidates`, 이전 `/changes/*` 검토·스키마 변경, `/entities`, `/snapshots`, `/export`, `/search`, `/runs/{id}/ontology-changes`. 제거된 URL은 404다.
- `POST /runs`는 `kind=parse`만 받는다. `extract`, `ontology`, `discovery` 및 이전 전용 입력은 422로 거부한다. 현재 업무 지식 실행은 기존 별도 `/business/*`를 사용한다.
- `/evidence/{id}?run_id=...`의 이전 discovery 문맥 조회는 422로 지원 종료를 알린다. `run_id` 없이 정확한 근거를 조회하는 현재 경로는 유지한다.
- 이전 추출 실행의 요약 읽기와 DB 기록은 유지한다. 옛 전체 검색·스키마 편집을 새 API로 위장하지 않는다.

저장소 안의 직접 소비자는 함께 전환했다. 저장소 밖의 알 수 없는 클라이언트가 옛 URL을 사용하지 않는다는 보증은 없다. 이 변경은 이전 API의 명시적 지원 종료다.

## 화면 변경

- 검토 작업에는 선택 항목, 원문 변경·영향, 현재 업무 검토 도구를 남겼다. 이전 온톨로지·개체 사실·사용 버전 관리 도구를 제거했다.
- 새 검색은 `GET /business/snapshots`와 `POST /business/search`를 사용한다. 선택한 출처 지식 버전과 상단 탐색 범위를 동기화한다.
- `source_graph` 버전을 선택하지 않았으면 실행하지 않는다. 옛 active snapshot이나 다른 버전으로 자동 대체하지 않는다.
- 현재 snapshot API가 지원하는 개념·관계 검색, BM25, 임베딩만 노출한다. 별도 원문 QA/실험에 있는 Hybrid 기능을 snapshot에도 지원한다고 표시하지 않는다.
- 응답의 실제 `run_id`로 기존 저장 답변·인용 UI를 재사용한다. 화면을 열거나 버전을 고르는 동작은 모델 호출을 시작하지 않는다.
- 중복 제출을 막고 실패 시 질문을 보존한다. 버전 변경 시 새 검색 탭을 유지하되 이전 버전의 결과는 비운다.

## 검증 결과와 한계

실제 로컬 모델·임베딩은 실행하지 않았다. 별도 작업 위치와 복사 DB, 포트 8041/3041을 사용했다. 기존 서버와 실험 코드는 변경하지 않았다.

- 변경 경계 검사: 공통 구간·현재 API·워크벤치·검색·실행 잠금 등 기존 183개 통과와 신규 지원 종료/기록 보존 검사 3개 통과. 초기 신규 검사 자료의 누락은 고친 뒤 재확인했다.
- 넓은 지식 단위 검사 첫 실행: **1,222 통과, 17 실패, 1 제외, 30 setup 오류**. 신규 테스트 자료 오류 3건은 위 3개 통과로 해소했다. 나머지 **17 실패·27 setup 오류는 변경 전 코드에서도 같은 이름·원인으로 재현**됐다. 전체 검사 통과라고 보고하지 않는다.
- 기존 실패는 오래된 fixture의 요구 필드 누락과 graph stub 인자 불일치였다. 27개 setup 오류는 실제 모델 메타데이터에 접근하려는 fixture를 네트워크 차단 검사 환경이 막은 결과다. 이 작업에서 실제 모델 접근을 허용하거나 기존 의미 기준을 완화해 통과시키지 않았다.
- 프런트엔드 경계 검사 **31개 통과**, Next 빌드·타입 검사 통과. 1,440/1,280px 브라우저에서 복사한 마트 M01/M02 버전 선택·동기화, 현재 API 요청, 저장 답변·인용 표시를 확인했다. 409 검사 응답 뒤 질문 보존·재시도 가능, 미승인 실행 범위의 검색 차단, 가로 넘침 없음, 브라우저 실행 오류 0건도 확인했다. 새로 띄운 검사 서버만 종료했다.
- 브라우저의 새 검색 제출은 현재 API 계약까지 확인하되 모델 부분을 명시적 검사 응답으로 대체했다. 저장 답변과 인용은 복사 DB의 실제 기록이다. 새 답변의 의미 품질, 검색 누락 해결, 자동 오류 교정 성공은 이번 성과가 아니다.

로컬 검증 위치: `/Users/hyeongi/.codex/artifacts/knowledge-legacy-retirement-20261019/`. `baseline-comparison.json`, 각 pytest XML·출력, `shared-contract-ast.json`, 브라우저 요청·검사 영수증·스크린샷을 포함한다. 원본 DB의 검사 전후 SHA-256이 일치한다. 원본 DB와 모델 응답을 이 PR에 추가하지 않는다.

## 다음 작업

1. 이 지원 종료 PR에서 API 변경·공통 계약 보존을 검토한다. 이번 실행에서는 해당 제거 PR을 병합하지 않는다.
2. 제거 변경을 main에 반영한 뒤 활성 실험 브랜치가 필요한 공통 import를 새 위치로 옮긴다. 실험 중인 checkout을 지금 일괄 수정하거나 rebase하지 않는다.
3. 현재 마트 검색 누락·자동 의미 판단의 남은 문제는 별도 실험 결과로 판단한다. 코드 정리가 해당 품질 문제를 해결한 것으로 계산하지 않는다.
4. 사용하지 않는 로컬 worktree·데이터·모델 캐시 삭제는 별도 보존 목록과 승인을 전제로 한다. 이번 제거에 포함하지 않는다.

현재 사용자 결정이 필요한 사항 없음. 제거 PR의 병합은 후속 검토 대상이다.
