# 발표 비교 기록 보존 안내

[발표 보고서](../document_graph_rag_presentation_20261012.md)는 2026-10-12에 완료된 부분 구축 그래프와 노출된 탐색 6문항의 B/C 비교를 기록한다. 결과 수치와 판정은 총괄의 최종 파일에서 복사했고, Markdown의 링크와 보존 안내만 추가했다. CSV는 Git 정책에 따라 LF 개행으로 보존했으며 데이터 행은 동일하다.

## 실행 코드와 문서 이력

- 실제 모델 실행 코드 SHA: `da9f53abf3cb141b904f0133d8557e5b7dfcb4be`.
- 보존 브랜치: `feature/document-graph-rag-comparison`.
- 문서 커밋은 위 실행 코드 이후의 별도 커밋이다. 이 디렉터리 최초 추가 커밋은 `git log --diff-filter=A --format=%H -- docs/70_research/company_knowledge/document_graph_rag_presentation_20261012.md`로 확인할 수 있다. 실행 코드 SHA를 문서 커밋으로 대체하지 않는다.
- [보존 manifest](preservation_manifest.json)는 원본 위치·원본 해시·보존 파일 해시와 링크 수정 범위를 기록한다. 커밋·push 이후의 실제 문서 SHA와 원격 검증은 완료 보고 및 로컬 `documentation_preservation_receipt.json`에 별도로 기록한다.

## 보존 자료

- 결과: [채점 기록](scoring_ledger.json), [요약](result_summary.json), [질문별 CSV](question_results.csv).
- 비용과 실행: [감사 보고서](execution_cost_audit.md), [정확한 집계와 파일 검사](execution_cost_audit.json), [기존 추출 비용 영수증](historical_extraction_costs.json), [QA 실행 상태](qa_execution_ledger.json).
- 범위와 참조: [범위 고정](priority_scope_freeze.json), [질문](questions_only.json), [평가 참조 기준](evaluation_reference_only.json), [방법과 해석 기준](presentation_methods_and_limits.md), [원문 범위 연결 영수증](source_closure_receipt.json). 평가 참조 기준은 결과 해석용이며 제품 입력으로 사용하지 않는다.
- 재현 조건: [설정](qa_settings_manifest.json), [구축 manifest](source_build_manifest.json), [QA continuation manifest](qa_continuation_manifest.json), [QA 실행 manifest](qa_execution_manifest.json).
- 부분 구축: [스냅샷 요약](build_receipt_summary.json), [스냅샷 연결 영수증](snapshot_connection.json).

영수증의 시각·원래 절대 경로·해시·실행 상태는 기록 당시 값이다. `priority_scope_freeze.json`의 개념화 전 상태, `historical_extraction_costs.json`의 당시 pending 값, 감사 보고서의 미커밋 상태 및 당시 HEAD는 수정하지 않았다. 최종 실행·비용은 `execution_cost_audit.json`, 최종 채점은 `scoring_ledger.json`과 `result_summary.json`을 사용한다.

[audit_execution_costs.py](audit_execution_costs.py)는 원래 로컬 위치에서 실행한 일회성 집계 코드의 원본 보존본이다. 현재 문서 디렉터리에서 실행하는 재현 명령이 아니다. 원래 위치·당시 HEAD·미생성 출력 조건을 전제로 하며, 보존 작업에서는 실행하지 않았다.

## 로컬에 유지한 큰 원본

원시 QA 응답·DB·임베딩 cache·전체 구축 기록은 다음 경로에 유지했다. JSON 내부 원본 경로와 해시도 그대로 보존했다. 다른 컴퓨터의 Git checkout만으로 큰 원본이 제공되지는 않는다.

`/Users/hyeongi/.codex/worktrees/document-graph-rag-comparison/Civil-Complaints-System/data/knowledge/evaluations/document_graph_rag_20261012/presentation_20261012/`

기존 전체 실행은 인접 `build_v2/` 및 발표 범위 `safe_stop/`에 유지했다. 새 모델 호출·재채점·제품 변경 없이 문서만 보존했다. #660, 원래 최종 26문항, A 비교, 전체 그래프 완성은 발표 이후로 유보하며 완료 처리하거나 자동 재개하지 않는다.
