# 업무 지식 의미 판단 연구 기록의 main 분리

2026-10-11. 제품 변경과 독립적으로 연구 원장·보고서·실행 코드·helper 검사를 보존한다. 이 분리는 새로운 품질 실험이나 제품 채택이 아니다.

## 출처와 선택 범위

- 기준 main: `c049efedb103c460fd295a1792d068532d0baaa8`.
- 원본 연구 브랜치: `feature/business-semantic-modality-research`, 커밋 `16fd09f48736404be84a4d279c8cbc2d479c49d3`.
- 분리 브랜치: `feature/business-semantic-research-records`.
- 비교 범위: `docs/70_research/company_knowledge`, `experiments/company_knowledge`, `scripts`, `app/tests/unit/test_business_*`.
- 위 범위에서 main에 없는 신규 파일 145개만 원본 커밋의 바이트와 파일 모드 그대로 복사했다. 원본의 제품 변경을 포함한 커밋 이력을 cherry-pick하지 않았다.
- `00ecdc34791ec3192b2e6b66886809cb5e1a4bd0..16fd09f48736404be84a4d279c8cbc2d479c49d3`의 후속 32개 커밋에서 달라진 선택 파일은 101개다. 그 이전에 이미 존재하던 미반입 연구 기록·helper·검사 44개도 포함했다. 32개 커밋 이후 파일만 고르면 이전 보고서와 helper 의존성이 빠지기 때문이다.

| 원본 반입 종류 | 파일 수 |
|---|---:|
| 연구 문서·구조화 결과 | 80 |
| 실험 원장 | 1 |
| 실행 코드·helper·패치 | 57 |
| 연구 helper 단위 검사 | 7 |
| 합계 | 145 |

원본 반입 파일의 총 크기는 28,622,772bytes다. 이 안내문과 [파일별 출처·SHA-256·검사 영수증](business_research_records_manifest_20261011.json) 2개를 더해 이 분리 변경은 신규 147개다. 기존 파일 수정·삭제는 없다. 원본 연구 checkout의 미커밋 `docs/README.md`, `experiments/README.md`는 반입하지 않고 그대로 보존했다.

## 제외한 차이와 제품 경계

아래 수정 4건은 원본 브랜치의 고정 커밋 URL을 상대 링크로 바꾼 차이뿐이다. 기존 고정 링크를 유지하면 원본을 계속 찾을 수 있고, 제품 PR의 문서 정정과 불필요하게 충돌하지 않는다. 특히 `business_scope_boundary_20261009.md`의 첫 문단은 제품 PR의 R05 평가 정정 안내와 겹친다.

- `business_evidence_parent_boundary_20261007.md`
- `business_fact_candidate_responsibilities_20261007.md`
- `business_operating_scope_20261008.md`
- `business_scope_boundary_20261009.md`

삭제로 나타난 `business_product_split_20261009.md`는 main에만 추가된 제품 분리 문서이므로 main 원형을 유지했다. 제품 `app/knowledge`, API, frontend, 기존 제품 검사, PR #635에서 삭제한 ARES wrapper·SVG를 이 분리에서 수정·복원하지 않았다. 제품 작업은 별도 [PR #658](https://github.com/Hangi-n42/Civil-Complaints-System/pull/658)에서 다룬다.

## 결과를 읽는 기준

- A의 개발 라벨 5/10→10/10, B1의 읽을 수 있는 개발 라벨 7/10→10/10과 정상 부분 회복은 해당 노출 개발 자료에서의 부분 성과로 보존한다. 이를 미사용 자료 일반화, 실제 저장·교정, 기본 경로 채택 성과로 바꾸지 않는다. [행동 영향 대조](business_action_impact_20261011.md)
- 이미 공동 판단이 8/8이던 NIE 자료에서 단독도 8/8인 비교는 공동 판단의 필요성·효율·형식·회귀를 확인한 것이다. 미해결 조건·범위·U/C 오류의 개선 가능성을 부정하지 않는다. 작은 고정 표본의 100%를 모든 입력에 적용할 보편 채택 기준으로 삼지 않는다. [#657 해석 보충](business_singleton_scope_contribution_20261011.md)
- #657의 차이 재작성 책임 제거는 조건 이유의 면제 추론 제거라는 부분 성과가 있었지만, U/C 회귀·이유 과장·주소 계약 실패·미완성과 비용 때문에 현재 변형을 기본으로 채택하지 않았다. 원래 B1의 개발 개선과 SC 확인의 잔존 실패를 함께 유지한다. [고정 5+2 결과](business_diff_responsibility_20261011.md)
- 과거 원응답, 실패 JSON, 당시 gate와 비용은 소급 수정하지 않았다. U/C를 합치거나 unknown·미완성을 성공으로 계산하지 않는다. helper 검사 통과도 의미 품질이나 제품 end-to-end 개선의 증거가 아니다.
- 실제 제품 편집·저장·보존·같은 질문의 답변 연결은 [원장](../../../experiments/company_knowledge/automatic_semantic_judgment_ledger.md)의 별도 제품 후속으로 읽는다. 제한 사례의 복구와 공개 질문 전체의 남은 공백을 구분한다.

## 의존성과 재현 한계

선택한 Python 63개를 AST로 읽고 정적 로컬 모듈 참조를 대조했을 때 누락은 없었다. helper가 가져오는 `compare_business_nli`, `compare_business_natlogic`, `compare_business_label_selection` 등은 함께 보존됐다. 원본 연구 문서의 inline·reference 형식 상대 링크 155개도 반입 파일과 기준 main에서 모두 해소됐다.

연구 실행기는 당시 `data/knowledge/evaluations`의 입력·source packet·동결 기준·원응답, 로컬 모델·서버·패키지를 참조한다. 일부는 main의 `ModelClient`/`ModelRequest`, `exact_evidence`, `discovery_segments`, `graph_retrieval`, `FrozenIndex`를 사용한다. 해당 모듈·이름의 정적 존재와 이번 helper 검사만 확인했으며 모든 실행기의 현재 제품 API 호환성·모델 실행·전체 재현은 검증하지 않았다. 당시 동결 코드/해시는 원래 실행의 출처이지 현재 main의 제품 코드를 과거 버전으로 되돌리라는 지시가 아니다.

원장의 절대 경로 링크 13개는 검사 시 이 컴퓨터에 존재했다. 별도 제품 worktree와 `.codex/artifacts`에 있는 자료여서 clone만으로 접근할 수 없다. DB, 모델, 런타임 산출물과 환경 설정을 이 PR에 새로 싣지 않았다. JSON·과거 보고서의 원래 경로도 그대로 보존했다. 이 변경은 연구 기록의 보존이며 독립 실행 가능한 전체 실험 배포 묶음은 아니다.

## 이번 분리의 검사와 다음 작업

- 원본 145개: 파일별 SHA-256·Git blob·모드 일치. 원본 checkout의 HEAD와 미커밋 README 2개 해시 유지.
- 기존 main 파일: 수정·삭제 0. 제외 M4/D1과 제품 경로 원형 유지.
- JSON 36개 파싱 및 Python 63개 AST 파싱 성공.
- 연구 helper 검사 7개 파일: `37 passed in 0.09s`. 모델 없이 라벨/주소/집계/Boolean 계약만 확인했다.
- `git diff --cached --check` 통과. 새 로컬·외부 모델 호출 0, 품질 재실험 0.

검사 명령은 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python -m pytest -q -p no:cacheprovider` 뒤에 영수증의 `validation.pytest.files` 7개를 지정한다. 검사 환경은 기존 프로젝트 `.venv`를 사용했다.

다음은 이 분리 변경을 별도 연구 PR로 검토하는 일이다. 제품 PR과 연구 PR의 검토를 분리하고, 이 작업에서는 PR 생성·병합을 실행하지 않는다. 현재 사용자 결정이 필요한 사항 없음.
