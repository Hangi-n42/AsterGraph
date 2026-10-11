# 저장 QA 이의의 최종 판정과 P2 복구·활용 결과

2026-10-11. 출발 커밋 `49f04cd4d67b23e27cdf3796e19ea80c4c1eca2a`, 제품 브랜치 `feature/business-requirement-answer-flow`.

**P2의 카드 선택지를 신규 후보 1개로 저장하고, 실제 자기원문 검수·표현 재검수·같은 공개 질문 QA까지 연결했다.** 기존 정상 후보 7개와 원문 의미 38개는 유지했다. 전체 질문은 미완료이며, 최초 local의 표현 완료 오판도 남아 있다. 이 결과는 선정된 개발 사례의 복구 증거다.

## 진행 이유와 범위

기존 후보는 가족관계증명서가 증빙서류에 “포함된다”고만 표현했다. 원문 b4에는 “가족관계증명서 또는 자녀 수가 명시된 다둥이카드”가 있지만, 기존 표현 검수는 이를 전체 표현으로 잘못 판정했다. 실제 저장 QA `45f21a71e7cb45b0b73902e5d12edf83`가 지적한 카드 공백을 기존 의미 `batch2:multi_child_proof_documents`에 연결했다. 정상 7후보·P1·원문 38의미·질문은 고정했다. [첫 비교 실패 기록](business_qa_gap_recovery_20261011.md)은 별도로 보존한다.

공개 질문은 **“어린이박물관의 사전 승인·예약 취소·비예약자 동반 입장과 증빙서류 안내는 무엇인가?”** 그대로다. 다른 질문으로 축소하지 않았다. 전체 재추출·새 모델·버스 신규 추론·외부 공개·병합·배포는 수행하지 않았다.

| 지정 범위 | 완료 대조 | 이번 확인의 경계 |
| --- | --- | --- |
| P1 단체 예약 취소 누락 | 기존 3후보 저장·자기원문 검수 결과 유지, 같은 QA에서 3개 모두 활용 | 기존 완료 결과의 보존 확인이며 재실험 아님 |
| P2 개인 증빙서류 카드 선택지 | 새 후보 저장·자기원문 지지·R 표현 판정·같은 QA 활용 확인 | 선정된 공백의 복구 완료 |
| 정상 주장과 전체 질문 보존 | 기존 7후보·38의미·공개 질문/항목 동일 | 전체 질문의 잔여 3항목은 미완료 |

## 제품 변경과 판단 권한

- `POST /knowledge/business/runs/{run_id}/answer-rechecks`는 저장 QA ID, 기존 task ID 목록, `repair` 실행 정책을 받는다. `repair` 기본값은 기존 실행 요청과 같은 `true`다. 판정·정답 문장·의미키를 입력받지 않는다.
- QA 원래 unit/응답/snapshot/run, 현재 원문·후보 전체 객체·공개 요구·작업·기존 의미·정확 근거 주소를 검증한다. 하나의 기존 의미로 연결되는 관찰만 `unverified_expression_gap`으로 전달한다. 원래 QA 문장 자체는 사실이나 후보 오류가 아니다. 의미 주소가 여러 개인 단체 입장 관찰은 `deferred`이며, 이것은 의미 오류 탐지 증거가 아니다.
- 해당 QA 이의의 최종 기여 행은 변경 여부와 관계없이 필수다. 명시적인 `represented`, `partial`, `missing`, `unknown`을 허용하고 같은 상태·후보 집합의 재확인도 허용한다. 행 누락·중복·범위 밖 주소는 미완료다. `partial`은 표현된 내용·잔여 내용·정확 잔여 근거를 모두 요구한다. 같은 행이 QA 관찰 처리와 후속 행동의 공통 근거다. 설명 문자열에서 상태나 답을 추출하지 않는다.
- 원문 조사 `local_not_found/reference_missing_here`의 기존 `not_required` 결과는 원문·요구·의미·assessment 입력 fingerprint·성공 unit·원래 finding·raw 판정 행·정확 근거가 일치할 때만 재사용한다. 새로운 구체 원문 이의가 있으면 재사용하지 않는다. 과거 후보의 전체 표현 완료 판정은 이 재사용 대상이 아니다.
- 재사용 행의 과거 후보 주소가 현재 join의 제공 후보 밖에 있더라도, 위 검증을 거친 원래 행과 전체 내용이 정확히 같을 때만 유지한다. 주소·이유를 바꾼 행에는 이 예외가 없다. 유효한 판정의 주소를 삭제하거나 global block을 강제로 지우지 않는다.
- 재검수는 기존 `assess(focus)`→필요한 원문 이의 재검수→`repair`→새 후보 자기원문 검수→표현 재검수→그래프·변경안 저장 경로를 사용한다. 미검증 QA 공백만으로 원문 재판정이나 자동 수정이 발생하지 않는다. 전체 요구는 `partial`로 남긴다.

## 중간 실패와 실제 후속 결과

각 변경은 확인된 계약 결함에 대응했다. 같은 요청의 모델 재시도로 성공 결과를 고르지 않았으며, 앞선 실패 raw·DB·동결 코드·비용을 모두 보존했다.

| 단계 | 실제 결과 | 신규 모델 호출 |
| --- | --- | ---: |
| QA 연결·과거 binding 표시 | local은 카드 부재를 설명하면서 `represented`, join은 부분성 설명과 `checks=[]`. `maintain`, 복구 0. 기존 원문 조사 3건 재작성 과정에서 근거가 사라져 global block 발생 | 2 |
| 필수 최종 행·원문 조사 재사용 | join이 `partial`을 명시하고 global block 제거. 그러나 상속한 선택 필드인 표현·잔여 내용을 생략해 `hold`, 복구 0 | 1 |
| 잔여 필드 필수 선언 | join이 표현·잔여·근거를 작성, `recoverable_remainder=true`, 행동 `recover`. 진단 parent의 `repair=false` 때문에 저장은 실행하지 않음 | 1 |
| 기존 복구 경로 실행 | 실행 정책만 `repair=true`로 별도 실행. 신규 후보 저장, 자기원문 `supported`, local/join 모두 새 후보로 `represented`. 서버의 재사용 주소 검증 결함으로 postjoin global block 발생 | 4 |
| 재사용 주소 검증 수정 | 직전 실제 local/join 요청·응답을 정확 재생. 새 의미 판단 없이 정규화 통과, global/meaning block 없음 | 0 |
| 같은 질문 QA | 새 후보를 선택해 증빙서류 OR 전체를 답변. P2 해당 항목 `unconfirmed=[]` | 1 |

두 번째·세 번째 단계는 첫 실제 local의 messages/schema/reference map/설정/요청·실행 한도가 동일한 경우만 저장 응답을 재사용했다. 필수 필드 변경에서 실제 송신 schema에 새로 필수가 된 것은 `represented_content`, `missing_content` 두 문자열이다. `missing_evidence`는 기존 근거 선택 wrapper가 이미 필수로 만들고 있었다.

`repair=false`로 종료된 세 번째 실행은 보존했다. 후속 실행은 유효한 assessment fingerprint를 확인하고 기존 제품 복구 함수를 호출했으며, 복구 전 local/join을 다시 호출하지 않았다. 최종 주소 수정 후 재생은 messages/schema/reference map/설정/한도/응답 전체 일치를 확인했고 새 생성 호출을 금지했다. 따라서 최종 R은 **실제 모델 응답 + 수정된 서버 경계의 native0 재생**으로 검증됐다. 주소 수정 후 새 R 모델을 실행한 것으로 세지 않는다.

| 증거 | 실행·식별자 |
| --- | --- |
| QA 연결 | `7d9dc000ff104510b825411ab62e1552` |
| 필수 최종 행 | `580298f7852f443f94337d32124f40dd` |
| 필수 잔여 내용 | `587e58f57afe4137a27eb03ba126c439` / assessment `351fdb139bfa4cbbbd8457d2d51b9712` |
| 실제 저장·자기원문·R | `ef09d8dc446d424393917f323f119a5e` / repair `697fd1ba3d8046b9a565147030f5a476` |
| 수정 후 정확 R 재생 | `0710c42c6d88461285423a9d01118240` / assessment `58a685dec18a4ebc94fb23e0fe0ffcae` |
| 최종 QA | `0db01b17227f47fbbc286b67c201550f` / snapshot `423a2d50a2384196a020048cd6beeea2` |

## 실제 저장·활용과 정상 보존

신규 후보 `8640f72195134958be4642fa62e74f5e`의 모델 생성 문장:

> 다자녀 가족의 비예약자 동반 입장에 필요한 증빙서류는 가족관계증명서 또는 자녀 수가 명시된 다둥이카드이다.

`event_entity`, Entity는 `다자녀 가족`, 조건은 `다자녀 가족의 비예약자 동반 입장`, 근거는 원문 b4다. 이 후보는 증빙서류 범위이며 무조건 입장 허가가 아니다. 기존 SC01의 자녀 4명 이상·사전 예약 가족 5명과 동반·현장 증빙 확인 조건은 그대로다. 기존 SC02의 증명서 포함 진술도 삭제·변경하지 않았다.

실제 자기원문 unit `43e9c9a0be1d4510adf16a375e2eefb1`은 새 후보를 `supported`로 판단했다. 후속 local `a2f7cd9f18b04dbab0c37a9eabd98578`, join `5d3b2f2c03fe4f55b34b892d72e3f048`은 새 후보 c8로 `represented`를 반환했다. 최종 QA의 `museum-4/context1`은 m8→새 후보를 `direct_fact`로 선택했고 공백 목록이 비었다. 렌더 답변과 citation에도 새 후보가 있다.

- 기존 정상 7후보 전체 객체와 원문 38의미가 동일하다. 기존 7개 자기원문 receipt도 현재 요청·설정에 유효하며 그대로다. 새 후보 검수와 과거 결과 재사용을 구분한다.
- P1 단체 취소의 기존 3후보는 `museum-2/context2`에서 모두 선택됐고 `unconfirmed=[]`다. P1 재복구·새 의미 검수는 하지 않았다.
- 최종 그래프는 노드 28개, NetworkX 연결 38개, 저장된 의미 edge record 12개다. 새 후보에 연결된 event/entity 노드 2개와 participation 의미 edge 1개가 있다. 서로 다른 edge 수를 같은 지표로 비교하지 않는다.
- snapshot은 AI 로컬 검토 결과를 활용한 진단용 승인 경로다. 후보 원본의 `review_status=unreviewed`, `semantic_status=unknown`을 수동으로 성공으로 바꾸지 않았다. 별도 자기원문 receipt와 활용 자격을 통해 검증했다. 인간 승인이나 전체 요구 승인 증거가 아니다.

## 비용과 경계 검사

| 단계 | 신규 호출 | 입력 토큰 | 출력 토큰 | 모델 초 | driver 초 |
| --- | ---: | ---: | ---: | ---: | ---: |
| QA 연결 | 2 | 19,256 | 1,564 | 197.861705 | 205.636636 |
| 필수 최종 행 | 1 | 10,990 | 819 | 113.569409 | 120.957597 |
| 필수 잔여 내용 | 1 | 10,990 | 865 | 112.869971 | 120.099735 |
| 저장·자기원문·R | 4 | 29,440 | 2,864 | 344.373267 | 352.887847 |
| 같은 질문 QA | 1 | 10,156 | 681 | 100.632269 | 103.066545 |
| 합계 | **9** | **80,832** | **6,793** | **869.306621** | **902.648360** |

위 합계는 신규 추론만 포함한다. local 실제 응답 재사용 2회, 수정 후 R 응답 재생 2회, 원문 조사 receipt 재사용, 사전 점검은 신규 추론이 아니다. driver 합계는 표의 실제 실행 시간 합계이며 테스트·문서화·전체 작업 시간을 뜻하지 않는다. 반복 성능 벤치마크가 아니다.

기존 로컬 Ollama 설정의 draft `gemma4:31b-it-q4_K_M`, review `qwen3.8:27b-q4_K_M`를 사용했다. 단계별 실제 모델·요청 한도·토큰은 각 `request_ledger.json`과 raw 요청에 보존했다.

최종 관련 경계 테스트는 **122 passed in 143.75s**다. 범위는 feedback, qa_action_contract, missing_recovery, separated_review, public_scope 5개 테스트 파일이다. 저장 QA 연결·실행 정책·필수 판정·잔여 필드·정확 주소/근거·원문 재사용 무효화·복구 후 경계를 확인했다. 테스트 통과 자체를 모델 의미 개선으로 계산하지 않는다.

제품 worktree에서 실행한 명령은 다음과 같으며, 결과 파일은 `data/knowledge/evaluations/business_qa_recovery_use_20261011/tests_final_boundary.log`다.

```sh
/Users/hyeongi/projects/Civil-Complaints-System/.venv/bin/python -m pytest -q \
  app/tests/unit/test_knowledge_business_feedback.py \
  app/tests/unit/test_knowledge_business_qa_action_contract.py \
  app/tests/unit/test_knowledge_business_missing_recovery.py \
  app/tests/unit/test_knowledge_business_separated_review.py \
  app/tests/unit/test_knowledge_business_public_scope.py
```

기존 버스 QA `7c02742a2dca48ab8bcf60afdf4e7184`, `e5f927e463d0411fbdec45b315d8c88f`는 messages/schema/reference map/렌더 답변이 정확히 같다. 해당 BUS-CONTROL-12/BUS-NEW-13 assessment에는 public_scope·QA finding·answer_gap_recheck가 없고 원문 재사용 수가 0이다. 따라서 새 필수 최종행·재사용 주소 예외가 적용되지 않는다. 원본 DB SHA-256 `b85204999c9069cd629eab8a322454d3886adaf2830cea2fe7baa112c9d1165f`도 그대로다. 이는 native0 경계 보존 검사이며 버스 전체 R 재평가 증거는 아니다.

각 실행의 동결 코드와 실제 요청·raw를 보존했다. 최종 QA 기준 제품 코드 12파일 무결성 검사가 통과했고 종료 후 Ollama 모델 목록은 비어 있다.

## 남은 한계와 다음 작업

초기 local의 OR 전체 표현 오판은 해결되지 않았다. 이번에는 저장 QA 이의를 받아 최종 join에서 올바른 잔여를 판정하고 실제 복구로 연결했다. 반복 개발에 노출된 단일 사례이므로 일반 정확도·미노출 사례 성능·100% 완료를 주장하지 않는다. 상태만 좋아진 단계, 저장 효과, 실제 QA 활용을 별도로 기록했다.

같은 공개 질문에는 다음 문제가 남아 있다.

- 개인 예약: 30분 내 미입장 자동 취소·개인 온라인 티켓 전환·60일 관람 제한의 검토 의미가 제공되지 않았다.
- 단체 증빙: 기관 정보·고유번호증 등의 검토 의미가 제공되지 않았다.
- 단체 비예약 입장: QA는 b5의 “연령에 관계없이 모든 인원이 예약”을 인용하면서도 첫 문장에 “명시적 허용·제한 규칙이 제공 문서에 없다”고 서술한다. 원문 부재와 검토된 표현의 공백을 혼동한 부정확한 서술이다. 이 항목은 이번 복구 대상이 아니다.

coordinator는 이 결과를 기존 #616/#617/#620 및 연구 원장에 연결하고, 위 잔여 공백과 잘못된 부재 서술을 후속 범위로 관리한다. 이 문서는 이슈 종료나 전체 목표 완료 근거가 아니다. 현재 사용자 결정이 필요한 사항 없음.

## 증거 보존 위치

제품 worktree의 `data/knowledge/evaluations/` 아래 네 디렉터리를 보존한다.

- `business_qa_gap_recovery_20261011`: 최초 연결 실패, 사전 기준·원본 연결·동결·실제 2회 응답.
- `business_qa_action_contract_20261011`: 필수 행 비교, 원문 재사용과 후보 추가 probe, 실제 join 실패.
- `business_qa_action_contract_required_20261011`: 필수 필드 schema·실제 잔여·recover 판정 및 repair=false 실행.
- `business_qa_recovery_use_20261011`: 실제 저장·ownS·R, 주소 오류 raw, 정확 재생, 같은 질문 QA, `semantic_result.json`, `native_costs.json`, 최종 테스트·버스 경계 기록.

독립 보존본은 `/Users/hyeongi/.codex/artifacts/business-qa-gap-recovery-20261011`이다. 네 디렉터리, 최종 제품 코드·테스트·보고서·diff·커밋/원격 receipt를 포함하고 파일별 SHA-256 manifest로 검증한다. 최종 커밋과 manifest digest는 보존본 및 전달 메시지에 기록한다. 기존 `business-missing-recovery-20261011` 보존본은 변경하지 않는다.
