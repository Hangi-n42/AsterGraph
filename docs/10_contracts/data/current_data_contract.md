# 현재 저장 계약

회사 지식은 `KNOWLEDGE_DB_PATH`의 SQLite 원장과 원문 저장 경로를 사용합니다. 스키마·상태는 `app/knowledge/repository.py`, `schemas.py`, `business_models.py`가 기준입니다. 출처 버전·근거 주소·주장·검수 상태·사용 버전·이력을 보존합니다.

민원 case/Chroma/관제 SQLite 데이터는 독립 저장소로 분리했습니다. 이번 분리는 기존 지식 DB 마이그레이션·삭제·사용 승인 작업이 아닙니다. [분리 기록](../../05_plans/company_knowledge/complaint_workbench_retirement_20261029.md).
