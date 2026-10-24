# 실행/운영 매뉴얼

- 문서 상태: canonical
- 문서 버전: v2.0
- 문서 분류·링크 정리일: 2026-09-26
- 하위 문서 전체의 구현 일치 여부를 이번에 재검증한 것은 아님
- 기준 코드:
  - `scripts/run_api.py`
  - `frontend/package.json`
  - `scripts/build_complaint_intelligence_demo_seed.py`
  - `scripts/seed_complaint_intelligence_demo.py`
  - `scripts/prepare_complaint_intelligence_real_replay.py`
  - `scripts/seed_duplicate_merge_demo.py`
  - `scripts/evaluate_complaint_intelligence_scenarios.py`
- 관련 문서:
  - `docs/10_contracts/`
  - `docs/20_domains/`
  - `docs/50_issues/complaint_intelligence_demo_seed.md`

## 디렉터리 역할

`docs/30_manuals`는 개발자와 운영/검증 담당자가 실제로 실행할 명령과 순서를 확인하는 곳입니다. 기능 설명보다 실행 절차, seed/replay, 평가, 흔한 문제 해결에 집중합니다.

## 권장 읽는 순서

1. `local_dev_runbook.md`
2. `complaint_intelligence_demo_replay.md`
3. `duplicate_merge_demo_flow.md`
4. `evaluation_runbook.md`
5. `chromadb_lfs_policy.md`

## canonical 문서

- `docs/30_manuals/local_dev_runbook.md`
- `docs/30_manuals/complaint_intelligence_demo_replay.md`
- `docs/30_manuals/duplicate_merge_demo_flow.md`
- `docs/30_manuals/evaluation_runbook.md`

## historical 문서 처리 기준

기존 실험/평가 매뉴얼은 보존합니다. 단, 현재 서버 실행, Intelligence demo/replay, 중복 병합 demo, 평가 실행 절차는 위 canonical 문서를 기준으로 합니다.

## 신규 제품과의 관계

이 디렉터리는 기존 민원 기능의 참고 기준이다. 신규 회사 지식 제품은 [문서 지도](../../docs/README.md)를 통해 PRD·설계·구현·마일스톤을 확인한다. 과거 평가 결과는 [모듈별 실험](../../experiments/README.md)에 보관한다.

## Python smoke와 배포 기록

[Python Syntax Smoke](../../.github/workflows/deploy-production.yml)는 main push/수동 실행에서 Python 문법을 compileall로 검사한다. 서버 전송·배포·GitHub production deployment marker를 생성하지 않는다. 전체 기능·품질 CI도 아니다. 이전 marker 기록은 삭제하지 않았다. [DORA 계산](../../.github/scripts/calc_dora_metrics.mjs)은 GitHub Deployment의 성공/실패 이벤트를 집계하므로, 과거 marker가 포함된 값은 실제 서버 배포 빈도/실패율의 증거가 아니다. 앞으로 이 smoke 실행은 deployment 집계에 추가되지 않는다. 실제 배포가 필요하면 별도 배포 절차와 지표 기준을 정해야 하며 기존 DORA workflow의 활성 상태는 변경하지 않았다.
