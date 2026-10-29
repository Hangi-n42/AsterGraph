# 현재 API 진입 계약

2026-10-29 민원 워크벤치 분리 이후의 진입점입니다. 실제 요청 모델과 경로는 `app/api/routers/knowledge.py` 및 `/openapi.json`이 기준입니다.

- 상태: `GET /health`, `GET /api/v1/health`
- 자료/원문/구간: `/api/v1/knowledge/sources`, `/sources/{source_id}/versions/{version_id}`, 해당 버전 `/raw`, `/blocks`
- 실행: `/api/v1/knowledge/runs`
- 업무 요구·검수·교정·버전·검색: `/api/v1/knowledge/business/*`
- 워크벤치 저장 조회: `/api/v1/knowledge/workbench/{scopes,review,usage,answers,changes,explore}`

기능 gate `KNOWLEDGE_ENABLED`와 기존 주소·버전·대상 ID·상태 검사를 유지합니다. validation 오류는 공통 error wrapper와 HTTP 422로 반환합니다. 상세 계약은 [지식 통합](knowledge_management_integration.md), [검색 기본값](knowledge_search_defaults.md), [용량·해석 수정](query_capacity_and_interpretation_edits.md)을 참고합니다.

민원 `/api/v1/search`, `/api/v1/qa`, `/api/v1/ui/*`, `/complaint-intelligence/*` 등은 등록하지 않습니다. 지식 검색을 민원 검색 경로로 우회시키지 않습니다. [분리 경계](../../05_plans/company_knowledge/complaint_workbench_retirement_20261029.md).
