# F4-b: 2단 머리글 부채비율표의 정형 행·필드 근거 보존

2026-10-16 KST. 제품 기준 `68c796299a679e3b531a6d28db4733f841ab426f`의 별도 관리 작업트리 `knowledge-debt-table-mapping`, 브랜치 `codex/knowledge-debt-table-mapping`에서 구현·검증했다. 조율 검토에서 해당 2단 부채표의 정형 전사·주소 연결로 제한 채택했다. 본인 브랜치에만 인계하며 F2 브랜치 통합·PR 병합·배포는 하지 않는다.

## 진행 이유와 구현 범위

D01 별표2의 C25/C26 수치는 기존 Event 주장에 이미 있었다. 필요한 별도 변경은 2단 머리글과 빈 셀, 명시 단위, 행별 값·필드 근거, 공통 주석의 원문 주소와 적용 미확정을 정형 기록으로 보존하는 것이다. 기존의 5열 산업분류 전용 프로필은 이 표를 지원하지 않았다. 숫자의 새 생성이나 두 행 전체의 의미 교정이 아니다.

- `business_html_debt_rows.py`에 해당 머리글·병합·본문 셀·제목·주석 구조만 받는 좁은 프로필을 추가했다. 제품 코드에는 C25/C26의 정답 숫자를 넣지 않는다. 값은 원문 셀의 문자열 그대로 저장하고 재계산하지 않는다.
- 기존 `POST /api/v1/knowledge/business/html-rows`와 `HtmlLiteralRowsRequest(parent_run_id, block_ids)`를 그대로 사용한다. 이 프로필에서는 선택할 행의 업종 셀 주소를 전달한다. 기존 산업분류 프로필의 코드 셀 선택은 유지한다.
- 기존 `structured_row/raw.fields`와 `direct_tabular_row` 형식을 재사용한다. 각 새 행의 `table_mapping`에 원문 hash·parse·표 경로·머리글/병합·빈 머리글·명시 단위·공통 주석과 구조적 귀속/적용 미확정·의존 fingerprint를 저장한다. 별도 DB나 범용 매핑 체계를 만들지 않았다.
- 평균/제한 머리글의 `%`만 명시 단위로 저장한다. 사업전환 열의 단위는 `unresolved`, symbol은 null이다. 최소200/최대500 등 세 공통 주석은 실제 원문과 같은 목록 구조를 보존하되 적용은 모두 `unresolved`로 남긴다. 빈 머리글에는 block ID나 내용을 만들지 않는다.
- 새 자유 개체나 개념화 대상을 만들지 않고 기존 행/필드 노드를 사용한다. 저장과 실제 조회 시 필드별 근거를 연결하고 같은 행의 다른 수치 셀이 근거로 섞이지 않게 했다. 이를 위해 `graph_retrieval.py`의 그래프 읽기 연결만 좁게 보완했다.
- 재사용은 값뿐 아니라 원문·parse·위치·필드 근거·table_mapping이 같은지 확인한다. 머리글/단위/주석/병합이 프로필 밖이면 미지원 이유를 반환하고 기존 주장과 추출 경로를 보존한다. 자동 모델 fallback은 실행하지 않는다.

`autoschema.py`, `business_concepts.py`, `business_run.py`, `app/generation/model_client.py`, `business_models.py`는 기준 commit과 해시가 같으며 편집하지 않았다. F1/F2 작업이나 모델 슬롯을 조작하지 않았다.

## 실제 원문·행과 제품 API 결과

원문 버전 `86a31d6b511a46f195963ef5ee52cd96`, parse `aa11c25ea5ba4c7c8e48ed186d4db851`, 등록 파일 `D01_canonical.html`을 사용했다. 원본 등록 HTML SHA-256은 `2c37e607822db85bf98c5d2d3c0fd118fcab5bc8cd5bab6283df7e3b65bfe017`이다. 원래 HWP 전체를 재감사한 결과는 아니다.

표 경로는 `#source > section:nth-of-type(72) > ul:nth-of-type(1) > li:nth-of-type(1) > table:nth-of-type(1)`이다. 머리글 row0/c0–c3은 rowspan2, row0/c4는 빈 셀, row1/c4는 `사업전환\n융자`다.

| DOM 행 / 원문 번호 | 업종 | 평균부채비율(%) | 제한부채비율(%) | 사업전환 융자 원문값 |
|---|---|---:|---:|---:|
| 20 / 19 | C25(금속가공제품(기계 및 가구 제외)) | 154.0 | 462.1 | 924.1 |
| 21 / 20 | C26(전자부품, 컴퓨터, 영상, 음향 및 통신장비) | 115.2 | 345.7 | 691.4 |

업종 선택 주소는 `a5105262da624079b0c830b4630f9772`, `e40a2a77f742418f856342e57c3e9e3d`다. 원문 값·주소와 단위 적용을 구분하며 사업전환 값에 `%`를 추가하지 않는다.

원본 `knowledge-html-rows/.../w7_final_pool_20261015_v1/knowledge.db`를 바이트 동일하게 새 artifact DB에 복사했다. 기존 run들은 모두 종료 상태였으며, 중단된 전역 개념화 DB를 제품 서비스에 연결하지 않았다. 생성과 임베딩 경로는 호출 시 실패하도록 막은 상태에서 실제 제품 router를 TestClient로 호출했다. 별도 서버나 평가 전용 정형 변환기를 만들지 않았다.

| 단계 | 실제 결과 |
|---|---|
| 원래 parent | `4c08e21f1fea4e09b42d1236eae6d051` |
| 두 행 저장 | HTTP200, run `9443284b54e546b2a12282c3a03cbb6c`, changeset `94db3ee648d54d10b10ae931fd43bc07` |
| 새 행 | `claim_1186e2805f0b8f9402979c37`, `claim_5ffaa9a510fe920c02d3495f` |
| 공통 table_mapping | `table_mapping_a99269ecf35c5b0a1acfce40` |
| 재조회 | 제품 runs GET에서 두 행·10필드 원문 문자열, 각 값/머리글/주석/원문 위치 확인. raw GET은 등록 SHA와 일치 |
| 필드 근거 | 실제 저장 run의 그래프를 읽어 10필드 모두 각자의 값·머리글·공통 참고 원문으로 연결. 다른 수치 필드의 값 셀은 섞이지 않음 |
| 반복 요청 | HTTP200, run `d233d9e236764e339a50dfd2456394d8`, 새 행0·기존2행 재사용 |
| 승인 경계 | 새 두 claim은 unreviewed/unknown이며 후보 자격 목록에 포함되지 않음. `exact_direct_row`의 의미 검토 우회에도 해당하지 않음 |
| 모델·임베딩 | 신규0회, 기존 숫자·주장·원시 출력 삭제/교정0 |

## 검사·보존·회차

- 새 프로필과 기존 HTML 분류표, 그래프 조회, 기존 API의 관련 **72개 검사 통과(27.92초)**. 전체 저장소 검사 결과는 아니다.
- 머리글, `%` 단위, 주석의 최대값, rowspan, 빈 머리글의 내용이 달라질 때 기존 행을 잘못 재사용하지 않는 경계를 검사했다. 필드별 원문 연결은 전체 원문 풀 사용/미사용 양쪽으로 확인했다.
- 초기 기능 부재 회귀검사는 실패했다. 구현 중 주석의 실제 끝 줄바꿈 대응과 검사 fixture의 파생 counts 비교를 보완한 뒤 위 범위를 통과했다. 이 과정은 모델 의미 조정 회차로 계산하지 않는다.
- 복사 DB의 모든 기존 행 hash가 같고 runs/changesets만 각2개 추가됐다. sources/versions/blocks/요구/결정/snapshot/활성 상태의 추가·변경은 없다. 원래 1,891주장과 기존 graph/개념 기록은 보존했다.
- 원본 final-pool DB/raw, 중단 run `ee09f60fe2344d9c955769eed38a85a8`의 DB·별도 pause DB·final_run JSON의 전후 hash가 모두 같다. 보호 파일5개도 기준과 같다.
- 원래 용량 실패 `ea82e9d3f5644bd4aca8e0e57d2e17f2`와 v7 `c02e648adfa84679b13934fcee2775d6` 계보의 **capacity2/6은 별도로 승계**한다. 과거 주소/의미 실패 조정 횟수는 unknown이다. 이번은 그 실패와 연결된 새 정형 매핑/주소 계약 변경1개이며 이전 회차를0으로 초기화하지 않았다. 같은 실패의 새 모델 재시도는0이다.

## 증거·한계와 다음 작업

로컬 증거 루트는 `/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261016/f4b_debt_rows_v1`이다. `before.json`, `first-response.json`, `new-claims.json`, `field-links.json`, `repeat-response.json`, `actual-result.json`, 실행에 사용한 `verify_actual_rows.py`를 보존한다. runtime DB/raw는 Git에 넣지 않는다.

완료 범위는 해당 명시 구조의 C25/C26 원문 값·주소·미확정 상태를 제품 API에서 저장하고 재조회한 것이다. 기존 두 Event Scope의 오류나 주석 해석이 자동 교정됐다는 결과가 아니다. 사업전환 단위, 주석의 실제 적용 대상, 하위코드 우선에 따른 업종 판단은 미확정이다. 다른 표/업무·전체882행·새 검색/QA·자동 의미 판단·브라우저 UI·범용 표 처리를 검증하지 않았다.

원격 [#660](https://github.com/Hangi-n42/AsterGraph/issues/660)은 원문/그래프 검색·답변 비교, [#614](https://github.com/Hangi-n42/AsterGraph/issues/614)는 별도 개념화 이웃 평가의 보류 범위로 확인했다. 둘 다 열린 상태이며 중복 이슈를 만들거나 기존 이슈를 변경·종료하지 않았다. 이 두 이슈나 전체 F4/W7 완료로 보고하지 않는다.

실제 수행한 것은 제품 API의 저장·재조회·원본 조회와 저장 그래프의 필드별 근거 연결이다. 자율 검색·답변·QA는 실행하지 않았다. 다음 통합 여부는 주 작업 담당이 별도 검토하며 본 작업에서 F2 브랜치에 반영하지 않는다. 현재 사용자 결정이 필요한 사항 없음.
