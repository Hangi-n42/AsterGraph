# R05 결론 구절과 추가 관계 판단의 제한 비교

2026-10-11. 제품 `feature/business-requirement-answer-flow`, 시작 `b1c4e8990b3e2781a3c988a39c0857bda65a0cc3`. #616/#617/#620의 후속 개발 비교다. **의미 gate 실패, 제품 기본 미채택, 새 R05 QA 0**으로 결정했다. 같은 prompt 재시도·새 judge·threshold 조정은 0이다.

## 비교 결과

기존 requirement_join 한 번 안에서 원 결론 구절 → 모델이 작성한 추가 관계 → 원문 지지를 명시하도록 바꿨다. k1 모델은 원 결론 전체를 relation에 다시 쓰며 명지·금련산으로 처리 기관이 한정된다고 supported로 판단했다. 담당 업무와 번호판 교부 기간 사실을 복합 처리 가능성으로 연결하고, 번호 변경·재발급·재봉인 제외를 번호판 변경 수반 업무 전체의 제외로 넓히는 기존 오판이 남았다.

모델의 `satisfied`, source complete, 오류 없음, eligible 21은 저장된 자기 판단이다. 자동 의미 품질이나 합의된 `r05-guidance-scope-v1` 완료가 아니다. 정상 k3/k4/k5는 supported를 유지했고 형식·주소·보존 계약은 통과했다. 정상 대조 유지와 핵심 관계 오판을 분리했다. 해당 기관의 실제 모든 권한이 거짓이라고 판정한 결과도 아니다.

## 동결과 변경 요소

기준선은 run `439a9c618e164141a8390a41db28e8fa`, join unit `0a8ef483d30344789c0b754674715264`다. 부모 DB의 171원문 블록·119후보·17원문 의미와 기존 실패/이력을 보존했다. 실제 join 선택 입력은 54블록·21후보·12의미·12국소 판정·기존 결합 5개다. 전체 DB를 모델 입력으로 직렬화하지 않았다.

기준선과 requirement·선택 원문·후보·source 의미·공개 항목·국소 판정·findings·source_inspections·selection·preservation targets가 전부 동일함을 비교했다. 원 결합의 ID/text/origin도 같다. user payload에서 달라진 것은 새 계약의 conjunction fingerprint뿐이며 기대 전제·정답 관계를 제공하지 않았다. 공개 질문·revision 1·원 criterion·모델·digest·generation·한도를 그대로 유지했다. 최대 context 49,152, 출력 8,192, think=false, temperature=0이다. 입력 예산 추정은 48,567이며 정확 토큰 수가 아니다.

새 `relation_checks`를 기존 ConjunctionReview 안에 추가했다. 모델은 원 결론의 실제 substring, 자신이 생성한 관계, 실제 의미키/근거, 지지 상태와 이유를 같은 호출에서 작성한다. 새 판정 호출은 없다. 기존 evidence-ID schema/주소 복원을 nested 관계 행에 연결하고, 기존 resolver/history/public 항목/의미·후보 위치를 재사용했다. prompt와 출력 schema 및 검증 계약이 함께 바뀌었으므로 단일 문장 지시만의 효과로 주장하지 않는다.

서버는 exact quote·의미키·근거 주소와 동일 원 결론 전체의 지원/미확인 출력 모순만 검사했다. 서로 다른 구절의 담당 사실 지원과 별도 복합 처리 미확인은 자동 모순으로 처리하지 않았다. 서버가 모델 label을 기대 진실로 바꾸지 않았으며 관계 내용의 완전성·진실을 계약 검사로 대신하지 않았다. 필드 생성과 주소 복원만으로 의미 판단이 개선되지는 않았다.

준비 첫 실패는 baseline 실행 스냅샷과 현재 Requirement 테이블의 history/current_assessment 메타데이터 차이였다. 공개 id/revision/question/criterion/target/situation/period/source_ids는 같았다. 원 사본·driver·failure를 `preflight_failed_01`에 보존하고, 새 실험 run 입력의 내부 bookkeeping metadata만 baseline 스냅샷으로 동결했다. 현재 테이블과 baseline 스냅샷 양쪽을 기록했고 원 DB·공개 요구·과거 판정을 수정하지 않았다.

준비에서는 모든 신규 generate를 금지하여 국소 12개가 exact 요청/응답 재사용임을 확인했다. SC03의 별도 문자 주소 복원 코드가 실행 전에 추가돼 v1/v2를 보존하고 최종 v3 manifest/code/driver를 동결했다. C의 원 input/prompt/schema는 이 주소 복원 때문에 바뀌지 않았다. 실행 중 코드를 수정하지 않았다.

## 실제 1회

run `12831a8102d34e99b9c09489cfa49f2d`, assessment `0f9c5f53deff4d8abbbc1322625407ce`, unit/request `9fc77f1743e348c3b9c64c493964f3b6`이다. 국소 요청 12개를 정확 재사용하고 새 join 1회를 수행했다. 입력 16,603·출력 3,645토큰, 모델 316.783973초, driver 344.041728초다. driver에는 복사 DB/start/재사용 처리도 포함되며 준비·대기·검토 전체 시간은 아니다. stop, 형식/주소 오류 0을 확인했다. 2026-10-11 05:01:31 UTC 소유 모델을 unload했고 models=[]를 확인했다.

k1은 원 statement를 유지하며 original/current supported다. relation은 `번호판 변경 수반 이전등록의 처리 가능 기관은 명지 본소와 금련산센터로 한정되며, 각각의 번호판 교부 기간이 다르다.`다. 근거 2개는 두 기관의 담당/교부 문장이다. 이유는 다른 세 센터의 특정 제외를 번호판 변경 수반 업무의 제외로 넓히고, 최종 이유에서는 이 두 기관에서만 가능하다고 단정한다. 분리해야 할 용어 대응·복합 처리·제외 적용 관계를 실제로 나누지 않았다. 원 결론을 단일 관계로 다시 표현한 것으로, 새 필드가 판단 책임을 제대로 수행했다는 증거가 아니다.

k2도 다섯 기관 처리 가능을 supported로 유지하면서 특정 번호 변경/재발급 제외는 번호판 변경 수반 업무에만 적용된다고 설명했다. k3의 세 센터 번호 변경/재발급/재봉인 제외, k4 동부산 말소/저당 제외, k5 금련산 신규/임시운행 제외는 정상 대조로 유지됐다.

finding0도 번호판 변경을 **수반하지 않는** 경우의 서류 공백을 여전히 `plate_change_documents`/b32/c47의 **변경 시** 구비항목으로 해소했다. 독립 common_documents 근거를 직접 연결하는 정정은 없었다. 대상이 달라진 해소를 resolved로 저장한 실패도 별도 기록했다.

12개 국소 상태는 represented이고 의미/원문 challenge는 0이다. 원문 의미·findings·전체 후보는 그대로다. 이 정상 계약 보존과 잘못된 전역 완료를 혼합해 정답률로 계산하지 않는다. 새로운 R05 snapshot·검색·QA와 전체 추출은 0이다.

## 보존과 기본 경로 경계

로컬 `data/knowledge/evaluations/business_conjunction_relations_20261011/`에 준비 실패, v1/v2/v3 동결 code/manifest/driver, 기준선과 입력 비교, 요청 13개, 실제 원 응답·run/DB·해제·원문 평가를 보존했다. `actual/experiment_only.patch`는 C에 해당하는 schema/prompt/resolver/nested evidence/fingerprint/전용 테스트만 포함하고 A dispatch·SC03 주소 복원을 포함하지 않는다. 역적용 가능성을 검사했다. 원 모델의 잘못된 supported 상태를 기대 label로 덮어쓰지 않았다.

코디네이터는 실패 구성을 제품 기본에 채택하지 않기로 결정했다. 독립 SC03 source4가 종료한 뒤 C 전용 patch의 역적용 검사를 통과하고 실제 역적용을 완료했다. `actual/code_withdrawal_receipt.json`에 patch와 코드 전후 SHA256 및 안전 경계를 기록했다. A dispatch와 SC03 주소 복원은 보존됐고, C schema/prompt/resolver/nested evidence/fingerprint/전용 테스트는 현재 기본 변경분에서 제거됐다. 실험 원형/patch/코드/보고와 다른 작업자의 변경은 보존했다. 현재 R05 목표는 미완료다. 이 실패 구성의 새 prompt·필드·검수·threshold 변형은 새 근거 없이 반복하지 않는다.

주소·Event·결합 관련 작은 검사 53건 및 이전 C 관련 5모듈 141건이 각각 통과했다. 두 실행의 중복 테스트를 합산하지 않았다. 검사 통과는 해당 계약에 관한 결과이며 의미 gate의 실패를 없애지 않는다. 공식·사람 검수·일반화 품질 결과는 아니다. 현재 사용자 결정이 필요한 사항 없음.

실제 비교의 독립 보존본은 `/Users/hyeongi/.codex/artifacts/business-conjunction-relations-20261011/first-join-trial-v1`이다. 66파일 1,161,134,313bytes를 모두 SHA256 대조했다.

회수 receipt·원 patch·원문 평가의 독립 보존본은 `/Users/hyeongi/.codex/artifacts/business-conjunction-relations-20261011/withdrawal-v1`이다. 3파일 41,841bytes의 SHA256을 모두 대조했고 이전 실험 보존본을 덮어쓰지 않았다. 실제 회수 뒤 A 변경을 포함한 관련 6모듈 76개 검사가 24.38초에 통과했다. 원 R05 의미 gate는 계속 실패이며 이 회귀 검사를 의미 개선으로 계산하지 않는다.
