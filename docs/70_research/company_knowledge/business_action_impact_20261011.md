# 자동 의미 판단의 행동 영향 · 저장 응답 대조

2026-10-11. 새 목표 `800fda79-cd8a-49ba-b6e1-7fcb089f6057` §6의 연구 기록이다. 연구 기준은 `791fff1550f7314bb34eea5af7dbfee19d202052`, 제품 기준은 `22ae39dd388a68ecee831ae7cb30330a34751420`다. 새 모델 호출·추출·편집·제품 코드 변경은 0이며 A 누적7을 유지한다. 기존 #657의 종료와 실패를 변경하지 않는다.

## 판단 목적과 근거 범위

같은 U/C 오류라도 실제로 무엇을 바꾸었는지 확인해야 한다. 기존 A/B1의 원문·후보·원응답, SC03/SC04의 연구 출력과 제품 self/repair/preservation/QA를 읽기 전용으로 대조했다. 연구 입력은 이미 개발에 노출됐고 SC03/SC04는 AI가 작성한 평가 변형이다. 자율 추출 오류나 미사용 자료의 성과로 계산하지 않는다.

**원문이 지지하는 표현으로 좁힌 실제 편집은 제한적 제품 성과로 인정한다. 미지지를 현실의 거짓·반대 사실로 바꾸는 설명은 계속 기각한다.** 원문상의 허용/미지지와 현실의 법적 의무 유무를 동일하게 다루지 않는다. 이 문서는 저장 응답의 행동 영향 분석이며 새 분류기나 채택 규칙을 구현한 결과가 아니다.

## 행동 영향표

S=원문 지지, U=원문 미지지, C=명시 반증. 분류와 실제 변경은 별도 열이며 같은 사례의 여러 단계는 독립 성공 건수가 아니다. 위험 열의 미실행 결과는 관찰된 피해로 계산하지 않는다.

| 구분·기록 | 원문·모델 판단의 실제 내용 | 관찰된 행동·정상 보존 | 결정과 남은 위험 |
|---|---|---|---|
| 개선 보존 · A p1, NA02 [R1] | p1은 `수령 가능`에 추가된 `수령해야 한다`를 U로 특정했다. NA02는 `산정해야 한다`와 허용 근거를 찾았으나 C/양립 불가로 과장했다. | A 개발5/10→10/10 개선은 유지한다. NA02의 위치 발견과 분류 실패를 분리한다. 이 연구 출력으로 저장·편집한 기록은 없다. | 후보 대조의 개발 이익은 인정하되 위치가 맞다는 이유로 C와 반대 사실 생성을 승인하지 않는다. 실제 편집 효과는 미측정이다. |
| ① 오류 구절·좁히는 방향은 유용하나 U/C 오류 · SC03/SC04 [R3, R4] | SC03은 모든 관람객으로 넓힌 대상, SC04는 `반드시 예약을 취소해야 합니다`와 관련 원문을 찾았다. 원 singleton과 B1 공동 모두 before를 C로 오판했다. B1은 after2를 S로 유지했다. | B1 추가 확인은 C/S,C/S 그대로여서 분류 개선0이다. source의 현장 답사 대상·취소 허용으로 좁히는 방향은 제공 before/after 대조에서 확인되지만, 연구 호출 자체가 수정문을 생성·저장한 것은 아니다. | C를 U로 고쳐 집계하거나 U/C를 합치지 않는다. SC03의 공손한 종결을 ‘권고’로 낮춘 차이 설명, SC04의 허용→의무 부정 설명은 편집 근거로 부적합하다. |
| ② 라벨은 맞지만 이유에 없는 의미 추가 · B1 condition.Y [R2] | 조건 없는 서류 구비 후보를 U로 판단한 것은 맞다. 그러나 `양수인 미방문시`에서 방문 시 서류가 불필요할 수 있다는 면제까지 추론했다. | 실제 저장·교정0. #657에서 그 면제 문구가 사라진 부분 개선1은 유지하지만, 다른 U→C 회귀2·미완성1 때문에 책임 제거 구성은 미채택이다. | 조건을 복구하는 방향과 방문 시 면제를 새 사실로 만드는 행동을 분리한다. 후자는 원문으로 확인되지 않는다. 라벨 정답만으로 이유 전체를 신뢰할 수 없다. |
| ② 차이 설명과 개별 이유의 오류 위치 구분 · NIE [R2, R4] | 후보는 하다람쉼터에서 먹어야 한다는 의무만 주장했다. B1의 개별 Y 이유는 의무 미지지를 설명했지만 differences는 그 장소에서만 먹어야 한다는 독점성을 덧붙였다. #657에서는 개별 Y 이유에도 없는 ‘하다람쉼터에서만’을 추가했다. | 원문은 지정 장소 제한과 하다람쉼터·에코리움 옥상정원 두 장소를 제공한다. B1의 S/U/C와 이미 맞던 개별 이유를 보존 대조로 구분한다. 실제 편집0. | 존재하지 않는 후보 의미를 지우는 편집, 허용된 다른 장소의 삭제는 허용 근거가 없다. 이는 예상 부작용이며 실제 삭제 발생으로 보고하지 않는다. |
| ③ 정상 후보 공격 · normal_detail 기준선→B1 [R2] | 기준선은 ‘양도증명서를 구비한다’는 정상 부분 진술을 세부 도장 조건 누락 때문에 U로 공격했다. B1은 원본과 상세 후보를 모두 supported로 판단했다. | 정상 공격1의 회복을 인정한다. 전체 B1 개발 읽을 수 있는 라벨7/10→10/10·정상6 유지와 숫자 계약 실패를 함께 보존한다. 실제 후보 수정0. | 정상 부분 진술의 정확성과 업무에 필요한 상세 표현의 충분성은 별개다. 부족한 상세를 보완하는 근거로 정상 후보를 오류화하거나, 부분 진술만으로 전체 요구를 완료할 수 없다. |
| ④ 유용한 발견의 주소 차단 · 제품 SC04 self [P2] | 제품 모델은 원문에 없는 강제성을 `incorrect`로 특정했지만 이유 끝에는 ‘모순’을 썼다. `Event`가 실제 제공 경로 `raw.Event`와 달라 첫 checks=[]였다. | 유일한 실제 raw 키 경로를 서버가 복원해 같은 원응답을 native0으로 재검증했다. 잘못된 ‘모순’ 이유는 수정되지 않았다. | 제품의 incorrect 계약은 연구의 S/U/C 구분과 다르다. 이를 U/C 해결로 세지 않는다. 주소 복원은 소유권 있는 편집 대상을 복구한 기록 처리이며 새 의미 발견·반증 승인이 아니다. |
| ④ 올바른 Event와 잘못된 부가 scope · 제품 SC04 repair [P3] | 모델 Event는 개인 예약자의 회차 시작 전 취소 허용을 제안했다. 추가 scope는 obligation/permission 불일치와 Entity 인용 오류를 포함했다. | 최초 전체 패치는 저장 실패했다. 같은 Event만 기존 단일 필드 경계로 미승인 저장했고 ID·Entity·조건·예외·기간·참조는 서버가 보존했다. 잘못된 scope는 unused_model_scope에 남았다. | 단순 주소 수정으로 scope 전체를 승인한 사례가 아니다. 좁은 미승인 저장 뒤 실제 원문·보존 검토가 필요하며, 잘못된 이유나 부가 해석의 포괄 승인으로 확대하지 않는다. |
| ⑤ 기존 수정본의 정상 보존 · 제품 SC03 P1 [P1] | 실제 before/after 대칭 비교에서 모든 관람객→현장 답사 희망자는 corrected/U, 방문 전·유선 AND 서면·사전 승인 행위는 retained, 새 누리집 참조는 added다. 이유의 ‘모순’ 과장은 남았다. | 기존 저장 수정본의 보존과 후속 소비를 확인한 결과다. P1 새 편집0. 이후 제품 QA에서도 현장 답사 조건을 유지했다. | 새 참조나 정정된 대상을 이전 정상 의미로 세지 않는다. 일반 관람객의 승인 면제나 현실의 권고 규칙으로 확장할 근거는 없다. |
| ⑤ 유용한 수정·저장·보존·답변 · 제품 SC04 [P3, P4] | 모델 제안은 `어린이박물관 개인 예약자는 예약하신 회차 시작 시간 이전까지 예약을 취소할 수 있습니다.`다. 원문 b2의 허용·시점과 일치한다. | 같은 제안 저장1, 현재 supported/errors0, 보존 preserved/comparison_errors0. 실제 전후의 개인·주체·취소·시점과 다른 후보3을 보존했다. snapshot/그래프/BM25/같은 공개 질문의 후보 인용까지 이어졌다. | 유용한 한 건의 제한 제품 성과다. 연구 B1 채택 효과나 전체 요구 완료가 아니다. 직접 retained 행은 Entity2이며 시점은 실제 전후 문장·원문 대조로 확인했다. 답변은 개인 취소 시한만 말하고 남은 단체·세부 규칙은 공백으로 남겼다. |

## 실제 편집 성과의 연결과 한계

SC04의 제품 입력에는 완성된 위 Event가 없고, repair unit `921c7047e18e48289a547d1d7503b52a`의 원응답에서 생성됐다. 이 Event와 저장본·snapshot·QA의 문장을 직접 대조했다. 이전 연구의 after를 공동 판단 입력으로 제시한 것과 새 제품 편집 모델의 출력을 혼동하지 않는다. source b2의 실제 허용 문장이 편집 근거이며, U/C 오판이나 ‘모순’ 단정이 현실의 반대 사실을 입증하지 않는다.

제품 repair `95c2971c80d8494d9bbf075dc9874eb1`은 처음 `applied_awaiting_recheck`였고, 보존 receipt `9973587c00e04294a7ad782058d6371f`를 거쳤다. snapshot `ab745bfd80314d0a84472a3727df5a4e`는 `explicit_query_only`다. 후속 QA run `bf68a1371a5249478a7d8f1efc98226b`는 교정 SC04 ID를 실제 인용했다. 강제 포함된 reviewed 후보와 기존 BM25를 사용했으므로 자율 검색 순위 개선이나 운영 기본 snapshot 활성화 성과는 아니다.

공개4항목·개인/단체8과제 중 직접 후보 사실을 사용한 과제5, 공백만 남긴 과제3이며 직접 답변2에도 추가 공백이 있다. 이를 5/8 정확도나 전체 완료율로 쓰지 않는다. 제품 기준22ae39dd에서 단체 취소·증빙의 후보 복구, 잘못된 전체 represented/개인·단체 결합, 저장 no-show 해석 정정은 미완료다. 새 목표에서 진행하는 단체 취소 복구의 결과는 아직 이 분석에 합산하지 않았다.

## 실제 입력과 용도로 정하는 사용 경계

다음은 이미 있는 검토·수정·저장 경계의 사용 범위다. 정답을 확인한 사례 ID 목록이나 모델 자신감·출력 동의로 라우팅하는 새 규칙이 아니다.

| 실제 용도·입력 조건 | 현재 인정하는 사용 | 자동으로 승인되지 않는 것 |
|---|---|---|
| 같은 출처·버전·현재 후보의 실제 오류 구절과 원문을 기존 검토에 제시 | A/B1의 국소 차이·정상 부분 회복을 연구 및 검토 자료로 유지. 잘못된 분류·이유도 함께 노출 | U/C 통합, 오류 이유 삭제, 위치가 맞다는 이유만으로 자동 편집 |
| 현재 자기 출처 오류가 `event_entity`의 `raw.Event` 하나이고 역할·그 밖의 필드가 유지되는 기존 직접 교정 | 모델이 원문 지지 표현으로 좁힌 Event를 미승인 변경으로 저장하고 기존 원문/보존 검토와 현재 버전 일치 확인을 거침 | 원문에 없다는 이유로 현실의 거짓·금지·면제를 저장하거나 후보의 반대를 새 사실로 생성. SC03처럼 참여자 변경까지 필요한 경우를 Event 전용 경계로 확대 |
| 같은 현재 후보·원문·실제 이의에 바인딩된 유효한 자기 출처/보존 결과 | 해당 후보의 직접 사실과 남은 공백을 같은 공개 질문의 답변에 사용 | 전체 요구·다른 상황·추가 결합·관계 승인. 정상 부분을 전체 충족으로 승격 |
| 주소·ID만 어긋나고 제공 입력에서 유일한 실제 경로가 확인됨 | 서버의 기존 정확 경로 복원과 원응답 보존 | 자연어 조건의 진위·잘못된 scope 의미·애매한 배열 주소까지 자동 확정 |

주소·버전 일치는 기록 안전성을 검증한다. 원문 지지·정상 의미 보존은 별도 실제 대조가 필요하다. 현재 사례는 그 제한 경로의 가치를 보여 주지만 같은 조건의 모든 입력에서 안전한 자동 정정을 입증하지 않는다. 특히 잘못된 이유가 좁히는 편집에도 새 면제·범위 손실을 유도할 수 있으므로 이유를 무시하는 채택 규칙은 만들지 않는다.

## 비용·결정·다음 작업

- 이번 저장 응답 분석: 새 native/추론 입력·출력/모델 처리 시간 모두0, 재추출·새 judge·제품 편집0. 이 분석을 새 A-08/R42나 새 실험 성공으로 세지 않는다. 문서 분석에 사용한 에이전트 토큰·시간을 제품 모델 비용0과 혼동하지 않는다.
- 과거 #657의7호출·26,323/4,596tokens·415.732679초는 원래 실패 비교 비용이다. 이번 비용에 다시 더하지 않는다. A 개발5/10→10/10, B1 개발7/10→10/10의 개선과 #657 회귀·미채택을 모두 유지한다.
- 별도 제품22ae39dd 공개 범위 작업은7호출·57,312/9,075tokens·923.122400초다. 그 안의 self/repair/preservation/QA4호출은13,551/2,556tokens·232.452292초이며 별도4회로 다시 더하지 않는다. 주소 복원과 같은 제안의 Event 저장은 native0이다. 기존 SC03 P1의1호출·3,295/640tokens·58.003330초는 그보다 앞선 별도 보존 확인이다.
- **채택 판단:** 기존 단일 필드 수정·원문/보존 확인·직접 사실 답변 연결의 제한 제품 가치를 유지한다. A/B1은 개발 성과가 있는 연구후보로 유지하되 기본 자동 판단기 채택을 새로 선언하지 않는다. differences 책임 제거와 SC 확인 실패를 반복하지 않는다.
- **다음 작업:** 제품 축은 새 목표의 단체 취소 실제 복구·저장·정상 보존·동일 질문 사용을 진행한다. 결과가 전달되면 해당 원문/자동 finding/실제 저장·답변과 비용만 별도 제품 후속으로 추가한다. 현재 연구 결정에 필요한 추가 비교는 없으며 새 이슈도 필요하지 않다. #616/#617/#620 전체 완료와 #657 연구 종료를 구분한다. 현재 사용자 결정이 필요한 사항 없음.

## 원형 근거

아래 상대 경로의 기준은 각 checkout의 `data/knowledge/evaluations/`다. 읽은 파일의 SHA와 원형 불변 확인은 `/Users/hyeongi/.codex/artifacts/business-action-impact-20261011/evidence_receipt.json`에 남긴다. 원래 frozen/raw와 과거 gate=false를 수정하지 않는다.

| 근거 | 원응답·실제 결과 위치 |
|---|---|
| R1 | 연구 `business_candidate_contrast_20261010/{inputs.json,run/p1_joint_response.json,confirmation/run/NA_pair1_joint_response.json}`; [A 보고서](business_candidate_contrast_20261010.md) |
| R2 | 연구 `business_candidate_text_diff_20261011/{inputs.json,preserved_baselines/normal_detail/response_path.json,run/normal_detail_response.json,run/condition_response.json}`; `business_candidate_diff_confirmation_20261011/{inputs.json,execution/run/permission_place_diff_response.json}`; [B1 보고서](business_candidate_text_diff_20261011.md) |
| R3 | 연구 `business_singleton_confirmation_20261011_execution/{SC03_single_response.json,SC04_single_response.json}` 및 `business_candidate_diff_remaining_20261011/{inputs.json,run/SC03_joint_response.json,run/SC04_joint_response.json}` |
| R4 | 연구 `business_diff_responsibility_20261011/{source_output_audit.json,execution_after_preflight_repair/result.json}`; [#657 최종 결과](business_diff_responsibility_20261011.md) |
| P1 | 제품 `business_preservation_use_20261011/P1_actual/{candidate_review.json,candidate_unit.json}`; [고정 제품 보존 보고서](https://github.com/Hangi-n42/Civil-Complaints-System/blob/22ae39dd388a68ecee831ae7cb30330a34751420/docs/70_research/company_knowledge/business_preservation_use_20261011.md) |
| P2 | 제품 `business_public_scope_20261011/{self_actual/run.json,self_actual/receipt.json,self_address_materialized/receipt.json}` |
| P3 | 제품 `business_public_scope_20261011/{repair_actual/run.json,repair_actual/repair_receipt.json,field_patch_materialized/repair_receipt.json,field_patch_materialized/run.json}` |
| P4 | 제품 `business_public_scope_20261011/{preservation_actual/receipt.json,QA_preparation/snapshot.json,QA_preparation/graph.json,QA_preparation/query.json,QA_actual/output.json,final_comparison.json}`; [고정 제품 활용 보고서](https://github.com/Hangi-n42/Civil-Complaints-System/blob/22ae39dd388a68ecee831ae7cb30330a34751420/docs/70_research/company_knowledge/business_public_scope_20261011.md) |
