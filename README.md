# AutoSchemaKG 이전 구현 — 온톨로지 스키마 우선 경로

이 브랜치는 **AutoSchemaKG 활용으로 전환하기 전의 구현을 보존하는 역사 참조 브랜치**입니다. 현재 주력 제품이나 최신 실행 환경을 나타내지 않습니다.

| 항목 | 보존 기준 |
| --- | --- |
| 브랜치 | `codex/legacy-pre-autoschemakg` |
| 기준 커밋 | `94fee1161e34f3d462e9d5da2ea9dd4ff7403fc7` |
| 기준 커밋 일자 | 2026-10-06 KST |
| 전환 커밋 | `2ae34f92d70a877cfffff5c7bfd067140e5e4c1e` — 이 브랜치에 포함하지 않음 |
| 보존 범위 | 기준 커밋의 전체 Git 추적 파일과 이 README 안내. 실행 코드는 기준 커밋과 동일 |

## 이전 구축 방식

문서·업무 질문 분석 → 온톨로지 개념·속성·관계 설계 → 검토·승인 → 승인 스키마에 맞춘 사실 추출 → 개체·주장 저장 → 검색·답변 순서의 구현입니다.

| 보존할 경로 | 주요 파일 |
| --- | --- |
| 온톨로지 발견·설계·검토 | `app/knowledge/discovery_*.py`, `ontology_run.py`, `ontology_schema.py` |
| 승인 스키마 기반 추출 | `app/knowledge/extraction.py`, `extraction_contract.py`, `extraction_store.py` |
| 해당 저장소의 검색·사용 버전 | `app/knowledge/search.py`, `search_answer.py`, `snapshots.py` |

이 구현의 보존은 자동 온톨로지 품질이나 전체 업무 흐름의 성공을 선언하는 것이 아닙니다. 당시 실패·미완료 범위는 해당 시점의 연구·검증 기록을 함께 확인해야 합니다.

## 현재 구현과의 경계

- 전환 이후 주력은 AutoSchemaKG 기반 개체·사건·관계 추출과 추출 후 개념화입니다. 그 신규 실행 코드와 이후 개선은 이 브랜치에 포함하지 않습니다.
- 이 브랜치는 위 세 경로만 떼어낸 독립 패키지가 아니라, 해당 경로가 사용하던 공통 코드·API·UI·검사와 기존 민원 기능을 포함한 전환 직전 저장소의 스냅샷입니다.
- 현재 제품은 이전 모듈의 원문 분할·의미 기록·참조 대응·검색 등 일부 공통 기능을 재사용합니다. 이 보존 브랜치를 만들었다고 현재 제품의 동일 이름 모듈을 일괄 삭제할 수는 없습니다.
- 현재 제품의 레거시 API·UI 제거 또는 공통 기능 분리는 별도 변경입니다. 이 브랜치에서는 수행하지 않았습니다.
- Git에 추적되지 않는 원본 DB·원시 응답·평가 산출물·로컬 설정은 새로 포함하거나 이동하지 않았습니다. 이 브랜치만으로 당시 전체 실행 환경이 재현된다고 보장하지 않습니다.
- 재현이 필요하면 별도 작업 위치·DB·포트를 사용하고 당시 모델·설정·데이터를 확인해야 합니다. 현재 실행 중인 환경에 그대로 적용하지 않습니다.

## 아래 원본 README의 해석

아래 내용은 기준 커밋에 있던 README를 그대로 보존한 것입니다. 그 안의 ‘현재’·‘구현 전’ 설명은 과거 작성 시점의 기록이며, 이 브랜치의 전체 구현 상태나 최신 제품 상태를 설명하는 기준으로 사용하지 마세요.

---

# 회사 지식 워크벤치

> **2026-09-27 병합 상태 보충:** K1 측정 절차·최소 계약과 K2 자료 등록·추출·근거 위치 API/UI가 #498에 포함됐다. 아래 구현 전 설명은 #497 정리 당시 상태다. 현재 범위와 기존 Mac 확인 기록은 [K2 안내](docs/30_manuals/knowledge_k2_runbook.md)를 따른다. K3 이후와 전체 효용 비교는 미완료다.

- 문서 버전: v2.0
- 기준일: 2026-09-26

회사 문서에서 근거가 있는 지식·온톨로지를 구축하고, 사람이 검토한 지식을 갱신하며 Local/Global 검색에 활용하는 제품을 개발합니다. 기존 민원 검색·답변·관제 시스템은 재사용 기반이자 향후 활용 예시입니다.

## 주 기준 문서

- [제품 요구사항(PRD)](docs/00_overview/company_knowledge_prd.md)
- [목표 아키텍처·설계](docs/05_plans/company_knowledge/architecture.md)
- [구현 계획·오픈소스 재사용](docs/05_plans/company_knowledge/implementation.md)
- [1~2일 단위 마일스톤](docs/05_plans/company_knowledge/milestones.md)

## 현재 상태

신규 제품은 P0 구현 전입니다. K1의 파일럿 자료와 12개 평가 과제는 고정했지만 비교 실행 절차와 최소 데이터/API 계약은 남아 있습니다. `app/knowledge`와 지식 전용 API·UI는 아직 없습니다. 파일럿 과제는 독립적인 사람의 맹검 평가 자료가 아니며 제품 효용을 입증한 결과도 아닙니다.

현재 실행할 수 있는 기능은 기존 민원 검색·답변 생성·평가·관제입니다. [기존 민원 기능 PRD](docs/00_overview/complaint_system_prd.md)와 [현재 구현 아키텍처](docs/00_overview/complaint_system_architecture.md)를 참고합니다.

## 개발 시작

[로컬 개발 안내](docs/30_manuals/local_dev_runbook.md)에 Python 3.11.9, Mac/Windows 환경, 로컬 `.env`, 데이터·Ollama·포트 설정을 정리했습니다. [프런트엔드 안내](frontend/README.md)도 함께 확인합니다. `npm run dev`의 사전 처리에는 replay DB 초기화가 포함되므로 실행 안내의 데이터 보존 경로를 먼저 확인합니다.

## 문서와 산출물

- [문서 전체 지도](docs/README.md): 요구사항·설계·현재 계약·운영 안내
- [파일럿 고정 기록](docs/70_research/company_knowledge/company_knowledge_pilot_freeze_2026-09-26.md): 현재 준비 범위와 한계
- [모듈별 과거 실험](experiments/README.md): 과거 보고서 보관
- [실행 산출물](reports/README.md): 스크립트가 사용하는 JSON·캐시와 평가 절차
- [문서 정리 감사표](docs/DOCS_AUDIT.md): 이동 경로와 검토 범위
