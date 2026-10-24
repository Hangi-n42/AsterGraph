# 제한 RAG 후속의 재현 자료

제품 변경은 reader의 parser 위치 두 필드를 복원한 것뿐이다. 실험 P1은 기각돼 기본 검색에 들어가지 않았다. 새 제품 실행·입력·출력의 식별자와 비용은 상위 `document_graph_rag_followup_20261012.json`을 기준으로 읽는다.

- `P1_selection_policy.py`, `P1_offline.py`: 실제 고정 lexical 분리·교대 선택 코드. 모델 없는 원문 문맥 비교만 수행했다. P2의 위치 복원을 제외하는 hook을 명시했다.
- `P2_driver.py`: 기존 product `business_use.query` 호출, 저장 검색/선택 재생, 송신 요청의 exact 동결 검사를 사용한 실제 평가 driver. 준비 오류를 수리한 최종 버전이며 SHA는 송신 계약과 같다.
- `preservation_manifest.json`: 최종 송신 계약 SHA·6개 요청 SHA·원본16파일 SHA·제품 코드 SHA와 로컬 raw/DB/코드의 보존 SHA.

실제 full inputs/outputs와 사본 DB는 기록된 `data/knowledge/evaluations/document_graph_rag_followup_20261012/`에 있다. 원래 발표의 source DB·source pool·질문·설정·saved QA·cache도 필요하다. clone만으로 전체 실험이 실행되는 배포 묶음은 아니다. 고정 코드의 절대 경로는 실제 실행 위치이며, 다른 환경에서는 명시된 원본과 해시를 맞춰 경로를 준비해야 한다. frozen contract와 raw를 덮어쓰는 재시도는 하지 않는다.

P1은 원본 DB의 source run을 읽기 전용으로 `/private/tmp/rag-followup-20261012/source_snapshot_readonly.json`에 내보낸 입력을 읽었다. 이 사본은 source run digest와 대조했고 원본 DB는 불변이다. P2 준비6건의 capture와 종료 API 오류는 모델 호출·실제 모델 실패가 아니며, 별도 `preflight_close_failure/P2_driver.py`와 사본 DB에 보존됐다. final driver는 실제 `executor.shutdown`을 사용한다.

평가 원문 정답은 비교 설계/판정 전용이다. 두 driver는 evaluation-reference/scoring 파일을 제품 입력으로 읽지 않는다. POSIX `fcntl`은 로컬 driver의 실행 조건이며 제품의 Windows 지원 판단과는 별개다. 실제 모델 실행 없이 재검토할 때는 full request SHA/원문 보존/코드 SHA/원형 응답을 우선 대조한다.

재현 코드 경계: 원본 `P1_offline.py`의 `discovery_profile` import와 절대 경로는 당시 실행 코드다. 현재 main에서 실행하도록 원본을 수정하지 않는다. 해당 모듈은 [제거 직전 보존 커밋](https://github.com/Hangi-n42/AsterGraph/blob/4334e8f8be65fc82afde791125f55eb73b857682/app/knowledge/discovery_profile.py)에 있고 현재 공통 구현은 `app/knowledge/source_index.py`다. 기존 `preservation_manifest.json`의 코드·입력·원응답 해시 및 당시 환경이 재현 기준이며, 새 requirements가 과거 환경을 대신하지 않는다. 정리 전 설치 목록은 [e96febe6 requirements](https://github.com/Hangi-n42/AsterGraph/blob/e96febe6765123f663b19c1c554d93773c703d55/requirements.txt)에서 조회한다.
