# P3/P4 제한 비교의 재현 자료

두 후보는 제품에 채택하지 않았다. 결과와 판정은 상위 [보고서](../document_graph_rag_continuation_20261013.md)와 [구조화 기록](../document_graph_rag_continuation_20261013.json)을 따른다. 기본 제품과 시험5파일은 `ade0185c`와 byte 단위로 같다. 이전 P2 위치 복원은 보존했다.

- `prototype_vs_ade.patch`: 실제 모델 실행에 사용한 P3/P4 제품·시험 코드의 동결 차이. 별도 임시 디렉터리에서 기준5파일에 적용해 저장된 prototype5파일을 정확히 재구성했다. 제품 경로에 적용한 상태로 남기지 않았다.
- `P3_P4_driver.py`: P3 선택/QA와 P4 핵심6건에 사용한 공통 driver의 동일 원형. `current_baseline_driver.py`는 현재 위치 정보와 원선택을 보존한 기준선, `P4_gap_B_driver.py`는 ACT501108 B의 독립 P4 대조다.
- `audit_saved_results.py`: 기존 raw에서 실제 새 호출의 token·시간·제공자 cache 필드를 합산한다. 정확 재사용된 선택기2건은 새 비용에서 제외한다. 모델을 호출하지 않는다. 의미 판정은 계산기로 자동 생성한 점수가 아니다.
- `post_P3_capture_driver.py`: P3 제거 직후 P4가 남아 있던 중간 코드에서 동결 요청8개를 정확히 재생한 capture 검사다. 현재 최종 제품의 P4 사용 증거가 아니다. 실제 모델0이며 초기 capture 종료 처리 오류는 따로 보존했다.
- `preservation_manifest.json`: 원본16파일, 실제 계약·raw·사본 DB·동결 코드, 중간 capture 및 오류 자료, 최종 제품 복원과 연구 patch의 SHA-256이다.

실제 full inputs/outputs·실패·DB 사본·동결 코드7파일은 `data/knowledge/evaluations/document_graph_rag_continuation_v1/`에 있다. 이 ignored 로컬 자료와 원래 발표의 source DB·source pool·saved QA·질문·설정·cache가 필요하다. DB·캐시·원본 전체는 커밋하지 않았다. clone만으로 모델 실험을 재실행하는 배포 묶음은 아니다.

실제 실행 driver는 절대 경로·code SHA·source DB SHA·frozen request·model digest를 검사한다. 동일 입력 계약/원응답을 덮어쓰는 재시도를 금지한다. 현재 제품에는 비교 옵션이 없으므로 source patch를 별도 기준 checkout에서 복원하지 않은 채 driver를 실행하지 않는다. POSIX `fcntl`은 로컬 실험 실행 조건이며 제품 Windows 호환성 판정과 구분한다.

P3 준비 V1의 input budget 기록 오류, ACT501108 C의 원문 용량 실패, 중간 무모델 capture 종료 오류를 각각 구분했다. P3 정상 대조6건은 준비만 했고 모델은 실행하지 않았다. 평가 reference는 비교 설계/판정 전용이며 실행 driver의 제품 입력으로 읽지 않았다.
