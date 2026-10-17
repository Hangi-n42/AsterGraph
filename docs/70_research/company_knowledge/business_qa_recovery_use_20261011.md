# 저장 QA 이의의 최종 판정과 P2 복구·활용 결과

**최신 결과는 하단의 「2026-10-18 후속: 원문 참여 대상 선택과 실패 제안 재개」 절에 있다.** 앞선 티켓 전환 복구에 이어 두 미저장 제안도 Entity 변경을 거쳐 저장·같은 질문의 답변에 사용됐다. 전체 목표는 partial이며, 아래 과거 본문·실패 기록은 당시 결과로 보존한다.

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

## 2026-10-18 다중 의미 QA 관찰의 제한 후속

#667이 병합된 main `c163cf3e23e6d0749ae560aacb48ac7521e1b5d3`에서 별도 `codex/business-qa-remaining-scope`와 DB 사본으로 진행했다. 같은 공개 질문·원문 8블록·저장 의미 38개·시작 후보 8개(기존 정상 7개와 P2 추가 1개)를 고정했다. 재추출·scope/QA 프롬프트 변경·새 검수 계층은 없다. 개발에 노출된 기존 사례이며 일반 정확도 평가가 아니다.

첫 읽기 감사에서 개인 취소 작업은 기존 의미 4개에 정확히 연결됐지만 `bind_gaps`의 단일 의미 제약으로 실제 서비스가 findings 0/deferred 1로 종료됐다. 단체 증빙의 단일 의미 연결은 이미 동작했다. 단체 비예약의 잘못된 부재 서술은 원시 scope/QA부터 존재했고, 최신 QA 소비 재생에서도 같은 모델 요청·답변으로 남았다. 옛 가족 예외의 단체 매핑과 eligibility 0을 최신 own-source 실패로 대체하지 않았다.

채택한 제품 변경은 두 경계뿐이다.

- **과거 검수 해시의 정확 호환:** 주소 복원 원장을 compact view에서 제외하면서 SC03 보존 `after_versions` 하나가 바뀌어 묶인 정상 3후보가 재사용되지 않았다. 같은 저장 필드·원장을 통해 당시 해시 `claim_3d94d93fba973a3eec233974`와 전체 원래 요청을 재계산하고, 메시지·schema·참조·모델·요청/실행 한도가 모두 일치할 때만 소비한다. 버전 필드를 무시하지 않는다. 실제 시작 자료의 유효 검수 재사용은 5/8에서 8/8로 복원됐다.
- **다중 관찰의 최종 판정 연결:** QA 자유 문장을 각 의미의 확정 누락으로 복사하지 않는다. 기존 task·원문·질문·후보·QA와 의미별 버전을 검증한 관찰 한 개를 전달하고, 각 키의 최종 represented/partial/missing/unknown 행이 기존 행동을 결정한다. 일부 미확정은 그 키만 차단하며 독립 정상·확인된 누락은 보존한다. 기존 단일 P2 경로는 유지한다.

관련 **195개 검사가 151.84초에 통과**했다. 의미·조건·주소·원장·모델·프롬프트·schema·한도·원시 결과·임의 해시 변화의 재사용 거절과, represented/missing/unknown 혼합이 실제 `assess`의 maintain/recover/hold로 이어지는 경계를 포함한다. 검사 중 native/임베딩 진입은 0이다. 이후 동결 제품 코드와 실행 중·종료 후 해시는 동일하다. 알려진 기존 16개 baseline 실패를 전체 재실행하지 않았으며 전체 suite 통과로 확대하지 않는다.

### 실제 처리·저장·같은 질문 답변

초기 run `b971d27559c547f8882d83b1cc9fcdf9`의 실제 local/join은 기한을 represented/maintain, 세 나머지를 missing/recover로 판정했고 차단 키·전역 오류는 없었다. 복구 전 R을 다시 생성하지 않고 유효한 저장 assessment를 검증해 새 사본/run `eed4f371138c4388ab1a59f18ef7bb14`에서 기존 repair를 소비했다.

모델 제안 3개 중 **티켓 전환 1개만 실제 저장**됐다. 신규 `ff7e3b646ed04992ad096c3fe5e3fff5`는 “미입장 수량은 해당 회차에 대한 개인 온라인 예약 가능 티켓으로 전환된다.”이며 조건은 “미입장 수량 발생”이다. 자기 출처 검수 `9aa6128135734351a8e3308f16e1e13b`의 supported와 후속 local/join의 represented를 확인했다. 나머지 자동취소·60일 제한의 `Entity=개인 예약자`는 선택 인용뿐 아니라 원문 8블록 전체에서 정확 문자열이 0회라 미저장됐다. 중복 주소나 선택 범위 부족이 아닌 문맥상 바꿔쓰기와 literal 참여자 계약의 불일치다. 기존 Event 편집은 이미 있던 Entity를 보존하는 다른 경계이며 이를 새 참여자 주소의 성공 근거로 사용하지 않는다. 원제안·오류를 보존하고 target 치환·주소 guard 완화·재생성을 하지 않았다.

세 원제안의 Scope에 obligation이 있지만 이는 `recovery_boundaries.unused_model_proposal`에 보존된 미채택 해석이다. 저장된 한 후보에는 interpretation/Scope가 없고 `unparsed_model_edit_requires_review`, `review_status=unreviewed`, `semantic_status=unknown`이다. 기존 문장 복구 경계의 raw 사실·조건과 자기 근거 검수만 사용하며 양태·관계 정확성을 승인하지 않는다. QA의 신규 m9 입력에도 modality/Scope가 없다.

검증용 AI 명시 결정으로 snapshot `4300044a6886487aa55919b2d58366fe`에 기존 8개와 신규 1개를 저장했다. 실제 사람 재검수·전체 요구 승인이 아니다. 그래프는 31노드·NetworkX 41연결·의미 edge record 13개다. 이전 28/38/12와 지표를 구분하며 이 증가를 품질 점수로 계산하지 않는다.

같은 공개 질문 QA `d69fd8d68a1e46c3881f4fb197fdf0fc`/unit `415a1cfb91024d50ad453863d6722bb9`는 개인 취소에 기존 m4와 신규 m9를 direct_fact로 선택했다. 실제 답변 문장·조건·citations에 신규 ID가 들어갔고 티켓 전환의 공백은 제거됐다. 자동취소·60일 제한 두 공백은 명시적으로 남았다. P1의 3후보와 P2 카드 OR는 각각 실제 선택됐고 해당 작업 unconfirmed는 비었다. 기존 8개 run 후보 전체 객체·38의미·원문 8블록·과거 snapshot 원형이 불변이며, 새 snapshot의 기존 8개 객체도 이전 snapshot과 동일하다. snapshot의 명시 결정 상태와 미승인 원본 후보 상태를 혼동하지 않는다.

검색은 BM25/limit 12와 `required_reviewed_meaning` 전달을 유지했다. 기한·티켓 두 후보가 필수 포함됐으므로 자율 그래프 검색 개선 성과가 아니다. 같은 질문의 제한된 저장 후보 활용 성과이며 원문만 보고 새 정답을 만든 성과와 구분한다.

### 비용·잔여·보존

| 단계 | 신규 호출 | 입력/출력 토큰 | 모델 초 |
| --- | ---: | ---: | ---: |
| 최초 local/join | 2 | 24,154 / 2,679 | 311.188945 |
| 복구 제안 | 1 | 5,972 / 2,340 | 163.653273 |
| 신규 1후보 자기 출처 | 1 | 1,301 / 297 | 25.808587 |
| 저장 후 local/join | 2 | 25,848 / 2,690 | 374.245273 |
| 같은 공개 질문 QA | 1 | 10,889 / 662 | 100.109739 |
| 합계 | **7** | **68,164 / 8,668** | **975.005817** |

승인 상한 7회를 소진한 뒤 추가 호출·재시도는 0이다. 실제 사용 모델은 고정 digest의 `qwen3.8:27b-q4_K_M`이며 임베딩은 0이다. driver 합계는 1,004.766383초로 검사·문서화 시간을 포함하지 않는다. 메모리는 측정하지 않았다. 일곱 unit의 전송/응답은 succeeded지만 두 제안 미저장과 의미 잔여가 있으므로 이를 전체 성공으로 바꾸지 않는다.

단체 비예약 답변은 여전히 “명시적 허용·제한 규칙이 제공 문서에 없어”라고 잘못 서술한다. 전원 예약 의미가 최초 source_facts의 선택지에서 빠졌고, raw scope의 잘못된 판단도 남았다. `lookup_stored_meanings`의 후속 상태 기록·전달과 실제 추가 조회 실행은 별개이며 이번 변경은 이를 구현하지 않았다. 단체 증빙 공백, 개인 두 의미의 미저장, 최초 P2 local 오판도 남는다. 부산 R05의 연결/미확정 실패와 버스 Requirement 12의 범위 밖 조사 해소로 인한 partial은 같은 변경에 묶지 않았다. 전체 요구는 partial이며 #616/#620을 닫지 않는다. #617 구성7/조정6/6 종료도 유지한다.

근거는 `/Users/hyeongi/.codex/artifacts/business-qa-remaining-scope-20261018/`의 분리된 두 제품 patch, 코드/입력/모델/한도 동결, 제품 입력과 분리한 평가 기준, 각 run/unit 요청·원시 응답, `semantic_result.json`, `native_costs.json`, 보존 receipt다. 원본 4DB와 옛 실패·코드·서버를 보존했고 모델 해제를 확인했다. 다음 범위는 새 참여자 주소 계약과 실제 추가 읽기 연결을 각각 원인에 맞게 검토하는 것이며 이번 동결판에서 의미 연구를 재개하지 않는다. 현재 사용자 결정이 필요한 사항 없음.


## 2026-10-18 후속: 원문 참여 대상 선택과 실패 제안 재개

### 진행 이유와 제품 경계

직전 결과에서 실패한 두 `Entity=개인 예약자`는 원문에 없는 **미검증 모델 표현**이다. 그 표현이나 행위자 역할을 정답으로 고정하지 않고, 기존 `event_entity`의 일반 `participation` 관계를 원문이 실제 지지하는 참여 대상에 연결했다. 이는 같은 행위자의 주소 복원이 아닌 **Entity·참여 대상의 표현 변경**이다. 고정된 Event·조건·예외·기간·참조·원인용 범위는 바꾸지 않았다. 정답·수동 명사·주소를 주입하거나 원복구 응답을 다시 생성하지 않았다.

제품의 일반 recover와 별도 실패 제안 재개 경로에 같은 선택 함수를 연결했다. 재개는 서버가 원래 repair 요청의 메시지·schema·참조·모델 식별·설정·요청/실행 한도·원응답을 재구성해 일치를 확인하고, 최신 후보 풀에 여전히 recover로 남은 실패 제안만 사용한다. 정상 티켓은 제외한다. `POST /business/runs/{run_id}/participant-resumptions`가 같은 검증을 사용한다. 새 모듈 두 개는 literal 선택·검증과 저장 실패 제안 재개를 각각 맡으며, 기존 그래프 공통 호출부는 정식 blocks를 전달해야 새 위치 계약을 실제 소비·검증할 수 있어 함께 수정했다. 비literal 별칭/역할 ontology는 만들지 않았고 원문 literal이 없거나 중복이면 미해소로 남긴다. 같은 부모 해시/repair의 재요청은 기존 자식 실행을 반환하며 실패를 자동 재시도하지 않는다. 과거 Event 의미 교정이 혼합된 재개는 읽기 검증 중 모델을 호출하지 않고 명시적으로 미지원 처리한다.

새 `source-literal-event-participant-v1` 계약은 원제안·새 Entity 선택·선택 이유·정식 source/version/parse/span을 함께 보존한다. 원인용과 새 literal은 위치가 유일해야 하며 음수/누락/중복 인덱스, 범위 밖 제안·근거, 버전·주소·필드 변조는 거절한다. 새 계약만 그래프와 기존 자기 출처 검수에 연결하고, 그래프 Entity 식별은 source/version/parse/정확 위치/kind에 따른다. 같은 이름만으로 합치지 않는다. Event는 원문에 있는 literal이라고 위장하지 않고 기존 문장 후보로 남긴다. 후속 직접/Event 편집은 옛 선택 계약을 history로 무효화하며 새 문장에 재승인하지 않는다. 원추출에 없는 repair chunk를 기존 부분 재구축의 자동 주소 연결 성공으로 취급하지 않는다.

### 실제 선택·저장·요구 재검수·답변

코드·원문 8블록·의미 38개·기존 9후보·질문·모델·한도를 동결하고 제품 `start → execute`를 실제 호출했다. 첫 선택 뒤 후속 호출 직전에 원출력과 서버 검증 결과를 보고한 뒤 기존 ownS/R/QA를 진행했다.

| 의미 | 원래 미검증 Entity → 새 literal | 정식 원문 주소 | 신규 후보 |
| --- | --- | --- | --- |
| 30분 미입장 자동 취소 | 개인 예약자 → 온라인 예약 내역 | v1/b2, parse `archived_dom_product_block_adaptation_20261011`, 272:281 | `fb77a249b6554ca5aa94b8e9a2eaa275` |
| 미취소 노쇼 60일 제한 | 개인 예약자 → 고객 | 같은 source/parse/b2, 381:383 | `1d2048b19e544a198cbafdeeba8b2743` |

두 후보 모두 자기 출처 검수 `2715bb170e054b1791a1f6bf30870c13`/`dc4e71efadbf4f72bac12b639dd4dbf6`에서 supported를 받았다. 다만 아래 설명 오류가 있으므로 이를 역할·양태·적용 범위 검수의 완전한 성공으로 확대하지 않는다. 미사용 obligation Scope는 원제안 기록에 남고 신규 후보의 interpretation/양태 승인은 없다. 원본 run 후보는 unreviewed/semantic unknown이다.

R local `fe29fbe11ff64dd8bfa3b37fdcf29aef`과 join `7490893aeb50429a83066d9a15fac06f`의 최종 assessment `91bb0f37a58f4a5187186b2a2824baf5`는 개인 기한·자동 취소·티켓 전환·60일 제한 네 의미를 모두 represented/maintain으로 연결했다. blocked/global은 []이며 전체 요구는 partial이다.

검증용 AI 명시 결정 snapshot `5cc0cc070f4f4d3283f2d56c168f62e6`에는 기존 9개와 새 2개가 있다. 그래프는 37노드·NetworkX 47연결·의미 edge record 15개이며 증가 자체는 품질 점수가 아니다. 이전 전체 그래프의 node/edge ID와 기존 의미 edge record도 모두 유지됐다.

같은 공개 질문 QA `420a837db6854d96aed5aba60ec73ee8`/unit `a5c4942610624e3db82e353b30aea793`는 개인 취소에서 m4·m10·m9·m11을 direct_fact로 선택했고 unconfirmed는 []다. 새 두 ID가 실제 답변 문장·조건·기간·citations에 포함돼 직전 두 공백이 제거됐다. **개인은 미취소·30분까지 미입장 시 60일, 단체는 14일 이내 취소 2회 이상 또는 미취소 미방문 1회 이상 시 1년**으로 답변에 구분됐다. P1 m5/m6/m7과 P2 m8의 카드 OR 선택도 유지됐다. answered/item_errors[]는 형식·참조 상태이며 의미 성공의 대체 증거가 아니다.

검색은 기존 BM25/limit 12와 개인 네 의미의 `required_reviewed_meaning` 전달이다. 자율 그래프 검색 개선·사람 승인·전체 요구 승인을 입증하지 않는다. 개발에 노출된 고정 사례의 제품 경로 검증이다.

### 설명 오류와 실제 소비를 분리한 평가

선택 reason은 ‘개인 예약자는 직접 참여자가 아님’이라고 배제하고, 선택/60일 ownS reason은 ‘고객’을 행위자로 부른다. 특히 ownS는 **“개인/단체 구분 없이 적용되는 부도 패널티”**라는 잘못된 범위 설명을 덧붙였다. b2는 개인예약 문맥이고 b5에는 별도 단체 1년 규칙이 있다. 원시 reason을 수정하거나 재시도하지 않고 품질 결함으로 보존했다. 새 그래프의 관계는 일반 participation이며 이 reason을 typed actor/권한 관계나 단체 60일 규칙으로 채택하지 않는다.

잘못된 ownS 범위 설명은 실제 R local 입력 `whole_candidate_judgments[0].check.reason`에 전달됐다. local의 실제 represented_content는 ‘개인 예약의 자동 취소’, ‘개인 예약자의 60일 관람 제한’으로 유지됐다. join과 QA의 실제 입력에는 해당 범위/행위자 설명 문자열이 없고, 최종 답변도 개인 60일/단체 1년을 구분했다. 이는 이번 출력의 소비 추적 결과이며, 다른 사례에서 이유 설명의 잘못된 일반화가 무해하거나 자동 교정된다는 증거가 아니다.

### 검증·비용·보존·잔여

최종 동결본 관련 **311개 검사 통과, 171.90초, native/임베딩 진입 0, 코드 불변**을 확인했다. 작성 중 이전 검사 303개는 통과했지만 동시 보완으로 code_unchanged guard가 실패했고 그 원기록도 보존했다. 이를 최종 검사에 합산하지 않았다. 전체 suite와 알려진 16개 baseline 실패는 재실행하지 않았다.

이번 별도 승인 비교의 신규 호출은 **선택 1 + 기존 ownS 2 + R local/join 2 + 같은 QA 1 = 6회**, 입력 **52,382**, 출력 **4,618토큰**, 모델 **648.445431초**, driver **703.034501초**다. 기존 고정 `qwen3.8:27b-q4_K_M`을 사용했고 임베딩·재시도는 0이다. 앞선 7회 기록/비용을 덮어쓰거나 #617 구성7/조정6/6을 초기화하지 않았다. 종료 후 모델 해제를 확인했다.

기존 9개 run 객체와 9개 이전 snapshot 객체를 각각 같은 종류끼리 비교해 불변을 확인했다. 38의미·8블록·기존 전체 그래프 node/edge ID·원본 4DB·직전 보호 9파일·동결 코드도 보존됐다. 근거는 `/Users/hyeongi/.codex/artifacts/business-participant-grounding-20261018/`의 원계획/정정 계획, freeze, native0 사전점검, 각 원요청·원응답, `selection_result.json`, `semantic_result.json`, `bad_reason_flow.json`, `qa_scope_verification.json`, `full_graph_preservation.json`, `native_costs.json`, `final_receipt.json`이다.

단체 비예약의 “명시적 허용·제한 규칙이 문서에 없다”는 잘못된 부재 설명과 단체 증빙 표현 공백은 남았다. 필요한 저장 의미의 추가 조회·재처리 실제 실행, 원문 부재/표현 공백의 구분, 모델 reason의 역할·범위 품질은 별도 잔여다. 부산 R05·버스 Requirement 12·이전 P2 local 오판은 해결로 처리하지 않는다. 다음 작업은 추가 읽기 실행 연결을 원인에 맞게 다루는 것이며, 이번 종료된 의미 실험을 반복하지 않는다. #616/#620은 열린 상태를 유지한다. 현재 사용자 결정이 필요한 사항 없음.
