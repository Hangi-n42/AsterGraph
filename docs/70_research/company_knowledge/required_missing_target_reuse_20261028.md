# 고정 필수 범위의 전체 미발견 요약 보존

현재 scope에서 유효하게 결속된 두 missing이 설명 문구만 달라 요약에서 unbound/unknown이 되고, 상품 2개 recover 후보가 사라졌다. 전체 missing은 대상 자체가 이미 정해져 있으므로 해당 target의 내용·근거를 재사용하도록 좁게 수정했다.

`business_review.summarize_local`의 질문용 사본에만 적용한다. 현재 원문 버전을 포함한 scope ID 일치, 유효 binding, missing, 빈 정상 기여/ID/표현 인용·결속, 미확정/모순/주소 오류 없음, 원래 잔여와 근거 존재가 모두 필요하다. 원형 모델 응답과 batch 이력은 바꾸지 않는다. partial/unknown/다른 scope나 버전/오류 행은 이 규칙으로 병합하지 않는다. 원문 전체 판정과 action/repair 규칙도 바꾸지 않는다.

현재 target.evidence에 이미 있는 중복 인용도 그 고정 값 그대로 재사용한다. 새 원문이나 더 넓은 요구 범위를 추가하는 작업이 아니다. 원래 모델 인용·문구는 해당 batch/unit에서 확인할 수 있다.

무모델 검증 결과:

- 관련 4개 테스트 파일의 고유 172개 검사가 통과했다. 처음 171개 통과/1개 실패는 기존 전체 missing의 자유 문구를 기대한 검사였고, 고정 target 값 및 원형 batch 보존을 확인하도록 수정해 그 1개를 재검증했다. 신규 좁은 경계는 17개다.
- 실제 저장 5개 경로 재생/실제 assess→action→repair 경계/저장·GET 일치. CURRENT 결합의 상품 2건은 unknown에서 유효 missing으로 회복돼 recover 후보 0→2, hold 8→6이다. 정상 대조의 2개와 일치한다. 단독 B1/B2 및 직전 정상 대조의 후보 수는 3/2/3으로 동일하다.
- 실제 관측은 7/64 또는 14/64다. 전체 후보 대조 경계는 유지돼 실제 교정 송신 0이다. 기존 합성 양성 3건은 송신 직전 요청 조립에 도달하고 정상 기여를 reuse_candidates로 보존했다. 합성 중복 1건은 기존 matcher가 차단했다.
- 국소 R의 두 전체 요청(메시지·스키마·참조·예약)은 기준 33d22073 요청과 bytes까지 동일하다. 요약의 고정 missing 값이 복구되므로 후속 G/교정 입력은 의도적으로 달라질 수 있다. 현재 제품의 G local_judgments 전달식에 missing 내용·근거가 남는 것을 확인했다. 실제 G 생성은 실행하지 않았다.
- 원형 batch, whole 결과, 후보 자기 원문 action은 5개 경로 모두 동일하다. 주장 199개·교정 2변경·기존 unit 151개·상속 llm_calls=12·기존 실패를 보존했다. 새 모델 호출 0, 실제 교정 송신 0이다.
- 원본 35개 실행 payload 및 원본 DB는 동일하다. 복사본의 requirements 진단 history만 실제 assess가 갱신했고 나머지 16개 테이블은 동일하다. 보호 파일 1,889개 변경 0, 기존 서버 29개 및 다른 checkout 6개/빈 모델 점유 상태 동일이다.

근거 루트: `/Users/hyeongi/.codex/artifacts/retail-knowledge-pilot-20261018/retail_required_missing_target_reuse_20261028_v1`의 `BEFORE_AFTER.json`, `LOCAL_R_REQUEST_COMPARISON.json`, `JOIN_PROJECTION_AUDIT.json`, 테스트 로그, 각 재생 결과와 보호 영수증.

이 변경은 요약의 정보 소실을 고치는 A다. B1 whole 조미 기여 회귀나 B2 whole 수량 과장을 의미적으로 해결한 결과가 아니다. 판단 계약 B는 별도 연구 브랜치·후속 비교로 격리한다. 현재 사용자 결정이 필요한 사항 없음.
