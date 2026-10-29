# AsterGraph · 기업 지식 워크벤치

기업 자료에서 출처 있는 지식 그래프를 구축하고, 업무 요구별 검수·교정, 사용 버전 확정, 검색·답변과 자료 변경 후 부분 재구축을 연결합니다. 구축 완료·의미 정확성·검토 상태·사용 선택은 서로 다른 상태입니다. 자동 의미 판단과 검색의 미해결 문제를 제품 완료로 표시하지 않습니다.

## 현재 제품 범위 (2026-10-29)

- 화면: `/knowledge` (`/`에서 이동)
- API: `/api/v1/knowledge/*`, `/health`, `/api/v1/health`
- 저장: 별도 SQLite 지식 DB, 원문·버전·검수 및 사용 이력
- 민원 선택·처리·통계·Intelligence, 민원 API/스케줄러/엔진은 독립 저장소로 분리했습니다. 민원 DB와 과거 Git 이력은 삭제하지 않습니다.
- Global 검색과 민원 활용 기능은 현재 제품 범위에 포함하지 않습니다. 검색용 개념 연결을 승인 온톨로지와 동일시하지 않습니다.

## 시작과 기준

[로컬 개발 안내](docs/30_manuals/local_dev_runbook.md) · [화면 안내](frontend/README.md) · [현재 API](docs/10_contracts/api/current_api_contract.md)

`npm run dev`는 화면만 시작합니다. 자료 등록·모델 실행·DB 초기화를 자동으로 수행하지 않습니다. API 실행 전에 실제 `KNOWLEDGE_DB_PATH`와 `KNOWLEDGE_ENABLED`를 확인합니다.

## 설계와 기록

- [제품 요구와 범위](docs/00_overview/company_knowledge_prd.md)
- [지식 아키텍처](docs/05_plans/company_knowledge/architecture.md)
- [민원 분리·공용 경계·검증 기록](docs/05_plans/company_knowledge/complaint_workbench_retirement_20261029.md)
- [문서 지도](docs/README.md)
- [이전 스키마 선행 실행 종료](docs/05_plans/company_knowledge/schema_first_retirement_20261019.md)

회사 지식 연구 기록과 원본 실행 자료는 보존합니다. 과거 설계·실험의 민원/버스 사례는 현재 민원 제품의 유지나 성공을 뜻하지 않습니다.
