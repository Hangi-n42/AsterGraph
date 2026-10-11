# 업무 보존 판정 continuation 연결 — 2026-10-11

#616의 변경은 저장된 유효 보존 판정을 다음 실행에 연결하는 코드 개선이다. 실모델 호출·새 의미 연구·전체 부산/버스 재실행은 모두 0회다. finding0/k1 해소, 의미 품질 개선, QA 성공을 주장하지 않는다. #616/#617/#620은 전체 작업이 미완료이므로 열린 상태로 유지한다.

일반 재개·저장 후보 재검토도 기존 편집용 builder를 통해 부모의 최신 assessment 보존 판정을 수집한다. claim·meaning·공개 requirement·source 지문과 active after 위치를 검증한다. 보존 위치는 제공된 active claim ID를 선택하도록 제한하며, 잘못된 위치는 새 assessment에서 해당 대상만 unknown으로 처리한다. 과거 raw 응답·부모 DB·승인 스냅샷은 정규화하지 않는다. 재사용 이후 새 meaning_challenge가 발생하면 관련 보존을 unknown으로 취소하고 완료를 해제한다.

원문 조사 기록이 참조하는 실제 unit만 `inspection_units`로 승계한다. 모델 응답용 `reusable_units`는 늘리지 않는다. 기존 주소·원문·요청 검증을 그대로 거치며, 원문이 달라지면 조사 범위는 unavailable이다.

최신 부모 `9da0802dc5794b4b9fd6edb196920dd3`에서 실제 start가 저장한 새 실행은 `a76a87aaf3a14c2d98561e74efee3999`다. c47/c116/c117 보존 3개가 유효하며 c47도 repair_context에서 제외됐다. source meaning 17·claim 119·block 171·finding 2·연결 ID/논리내용 5개를 보존했다. 조사 원본 `1f3345c4ec084e2184da588d95b6e97f` 1개를 승계해 범위 available을 유지했다. 제공 5블록·대상 1블록·부모 문맥 4블록이며 inspection_status는 기존 null이다. 이는 조사 완료나 의미 정확성을 새로 입증하지 않는다.

동일 의미 묶음의 요청·schema·reference_map·설정·실행 한도를 비교했다. 기존 국소 11개는 정확히 일치하여 제품의 기존 캐시 경로로 재사용했다. 직접 달라진 local04는 repair_context 제거뿐이며 이번에는 미실행이다. 그 None으로 발생한 plate 확대 요청 1개는 조건부 fallback이다. 실제 실행에서 반드시 필요한 새 호출 수로 세지 않는다. 이후 join은 부분 결과로 만든 진단 입력이며 미실행이다. 바뀐 요청에 과거 응답을 넣지 않았다.

원본 preflight 실패 기록 3개를 보존했다. 첫 비교는 새 validator로 과거 문맥을 재계산했고, 둘째는 fallback 이후 ordinal 비교가 어긋났다. 최종 실행은 연결 기록 전체 dict 일치 검사에서 실패했다. 연결 5개의 ID/논리내용은 같지만 기존 continuation fingerprint 검사로 `review`·`review_error`·`input_fingerprint`가 달라졌다. 원본 result를 고치지 않고, 저장 상태와 해시를 읽은 별도 독립 검증 영수증에 이번 범위의 검증 결과를 기록했다. 연결 판정이나 캐시 계약을 재설계하지 않았다.

검사: 기존 관련 111개 중 최초 110개 통과·fixture 주소 누락 1개 실패. 600c20f 원본에서도 동일 실패를 재현했고, fixture의 provided_block_ids만 실제 제공 주소로 맞춘 뒤 해당 parameter 6개가 통과했다. 최종 보존·조사 검사 31개가 통과했다(신규 continuation 16개·신규 조사 승계 2개 포함). 예전 필드 경로, superseded 위치, 변경된 claim/meaning/requirement/source, 새 모순, 부모 불변, 관련 없는 보존 유지 경계를 확인했다.

상세 검증과 원본 DB SHA-256은 [JSON 보고](business_preservation_continuation_20261011.json)에 기록했다. 실행 자료·DB 복사본·요청·실패·코드 지문·검사 영수증은 `/Users/hyeongi/.codex/artifacts/business-preservation-continuation-20261011/v1`에 별도 보존한다. 독립 영수증의 `bounded_preflight_verified`는 위 코드 연결 범위만 뜻한다.
