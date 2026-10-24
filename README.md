# 회사 지식 워크벤치

> **2026-10-19 실행 경로 정리:** 현재 지식 구축은 AutoSchemaKG 기반 출처 그래프와 업무 검토 경로를 사용합니다. 이전 스키마 선행 실행의 제거·호환성 경계와 역사 보존 브랜치는 [지원 종료 기록](docs/05_plans/company_knowledge/schema_first_retirement_20261019.md)을 참고합니다.

- 문서 버전: v3.0
- 기준일: 2026-10-19

회사 문서에서 출처 있는 지식 그래프를 구축하고, 검토·수정한 지식을 저장·갱신하며 검색·답변에 활용하는 제품을 개발합니다. 검색용 개념 연결과 승인된 온톨로지는 구분합니다. 기존 민원 검색·답변·관제 기능은 별도 활용 경로로 유지합니다.

## 주 기준 문서

- [제품 요구사항(PRD)](docs/00_overview/company_knowledge_prd.md)
- [목표 아키텍처·설계](docs/05_plans/company_knowledge/architecture.md)
- [구현 계획·오픈소스 재사용](docs/05_plans/company_knowledge/implementation.md)
- [1~2일 단위 마일스톤](docs/05_plans/company_knowledge/milestones.md)

## 현재 상태

`app/knowledge`와 지식 API·워크벤치는 원문 등록·파싱, AutoSchemaKG 추출·개념화, 업무 검토·부분 수정, 출처 지식 버전, 그래프 탐색·검색을 연결합니다. 구축 완료, 의미 정확성, 승인, 업무 요구 충족은 서로 다른 상태입니다. 현재 검색 누락과 자동 의미 판단의 미해결 문제를 전체 제품 완료로 표시하지 않습니다.

이전 온톨로지 발견·설계·검토와 승인 스키마 기반 추출·검색 실행은 보존 브랜치로 분리했습니다. 현재도 쓰는 원문 구간·의미 기록·검색 색인·사용 제한은 공통 모듈로 유지하며, 과거 DB와 실험 기록은 삭제하지 않습니다. 상세 API 지원 종료 범위는 위 기록에 명시합니다.

민원 계층은 [기존 민원 기능 PRD](docs/00_overview/complaint_system_prd.md)와 [구현 아키텍처](docs/00_overview/complaint_system_architecture.md)를 참고합니다. 아래 초기 PRD·계획·K1/K2 보고서는 작성 당시의 목표와 기록이며 현재 실행 경로 전체를 설명하지 않습니다.

## 개발 시작

[로컬 개발 안내](docs/30_manuals/local_dev_runbook.md)에 Python 3.11.9, Mac/Windows 환경, 로컬 `.env`, 데이터·Ollama·포트 설정을 정리했습니다. [프런트엔드 안내](frontend/README.md)도 함께 확인합니다. 일반 `npm run dev`는 화면만 시작합니다. 민원 replay DB 초기화는 명시적 `npm run replay:prepare`로 분리했으며, 실행 전 대상·백업 안내를 확인합니다. 현재 런타임 설정은 `.env` 환경변수와 `app/core/config.py`를 따릅니다. 이전 `configs/base.yaml`, `local.yaml`, `models.yaml`은 런타임 로더가 없어 제거했으며 [정리 전 기준](https://github.com/Hangi-n42/AsterGraph/tree/e96febe6765123f663b19c1c554d93773c703d55/configs)에 보존돼 있습니다.

## 문서와 산출물

- [문서 전체 지도](docs/README.md): 요구사항·설계·현재 계약·운영 안내
- [파일럿 고정 기록](docs/70_research/company_knowledge/company_knowledge_pilot_freeze_2026-09-26.md): 현재 준비 범위와 한계
- [모듈별 과거 실험](experiments/README.md): 과거 보고서 보관
- [실행 산출물](reports/README.md): 스크립트가 사용하는 JSON·캐시와 평가 절차
- [문서 정리 감사표](docs/DOCS_AUDIT.md): 이동 경로와 검토 범위
