# R40 · B1 후보 문자 diff 공동 판단 — 부분 효과, 최초 gate 실패 (#655)

2026-10-11. 서버의 후보↔후보 문자 공통/차이 표시와 고정 해석 주의문을 추가한 신규 4호출에서 **읽을 수 있는 라벨은 기존 7/10→10/10**으로 바뀌었다. c46 정상 원본과 허용/의무 대조의 3판정이 개선되고 다른 7판정은 유지됐다. 그러나 원래 출력 계약은 **2/4**, 조건 확대 이유에는 원문이 밝히지 않은 가능성 설명이 추가됐다. **최초 gate=false·제품 미채택을 유지하며 B1을 부분 효과·추가 확인 필요로 결정한다.** 의미 효과가 전혀 없었다고 기각하지 않고, 라벨 성공을 계약·이유·제품 완료로 확대하지 않는다.

동결 가설의 실제 비교와 결정 한 단위인 **A-06/R40, A 누적6**으로 기록한다. 신규 4호출과 오프라인 검사를 서로 다른 A비교로 세지 않는다. 이전 5비교·실패·준비 당시 상태는 보존한다.

## 변경과 보존 범위

[연구 스크립트](../../../scripts/compare_business_candidate_text_diff.py)는 표준 라이브러리 `difflib.SequenceMatcher(..., autojunk=False)`로 raw 문자열의 모든 후보 쌍을 계산한다. 실제 필드/Entity 요소 경로, 동일 문자열 필드, equal/insert/delete/replace 구간과 Python Unicode code point `[start,end)`·원래 quote를 제공한다. 원문 해석·정답·출처 지지 여부는 계산하지 않는다. 공통 부분은 지지 증거가 아니며 문자 차이는 의미 차이가 아니다.

기존 user 입력에 `candidate_text_diff` 한 객체만 추가했다. 객체에는 상대적 상세함이나 공통 부분으로 다른 후보 판정을 복사하지 말라는 고정 주의문도 포함한다. 그러므로 관찰은 **문자 diff+주의문 입력 묶음의 효과**이며 diff 계산 단독의 기여를 분리한 결과가 아니다. 전체 원문·부모·후보·후보 수/순서·system 지시·판단 책임·assistant prefix·숫자 라벨/차이/근거 출력 계약·모델·설정은 그대로다. 기대 라벨·원하는 정정문·새 후보·gold는 prompt에 없다.

과거 `business_span_binding_20261008/compare.py`는 모델이 source/candidate의 targets/actions/qualifiers 및 의미 bindings를 선택·작성했다. 이번은 source를 읽지 않는 후보↔후보 문자 연산이다. 원형 코드 SHA `c7592b02438e2ce0d988786c7c56026d35e0c1429ff6bb360508cdd46f957acb`와 기존 실제 요청의 source_bindings/candidate_bindings 계약을 대조했다. 모델 내부의 상세함 선호가 원인이라는 확정 증거는 아니다.

## 고정 4요청과 실제 출력

| 요청 | 고정 기대 | 재사용 기준선 | 새 raw의 읽을 수 있는 라벨 | 원래 계약 | 원문·이유 대조 |
|---|---|---|---|---|---|
| normal_detail | S/S | U/S | S/S | 실패: 숫자 대신 supported 문자열 | 일부 주장과 실제 추가 수식을 각각 지지. Y가 원문 모든 세부를 포함한다는 과장 없음 |
| condition | S/U | S/U | S/U | 실패: 삭제된 Y의 difference quote가 빈 문자열 | 조건 삭제/범위 확대 및 Event 오류 위치 발견. 방문 시 서류가 불필요할 수 있다는 부가 추론은 원문 근거 없음 |
| permission | S/U/U | S/C/C | S/U/U | 통과 | 허용은 의무와 의무 부재 모두를 입증하지 않음. U/C 혼동2 회복 |
| explicit_refutation | S/S/C | S/S/C | S/S/C | 통과 | 같은 조건의 명시 의무와 의무 부정을 구분. 정상 동의 표현 보존 |

숫자 라벨 mapping은 새8/10이며 normal_detail 2개는 unknown으로 남는다. 원래 응답 전체 계약을 통과한 요청의 판정은6/10이다. 문자열 라벨을 읽은 보조 관찰10/10과 분리한다. 읽을 수 있는 정상6/6·오류4/4, 이유9/10·Event 오류 구절4/4다. condition.Y의 source 조건을 배타적인 '경우에만'으로 설명하고 참석 시 불필요 가능성을 덧붙인 한계를 숨기지 않는다. U 라벨이 맞아도 그 부가 이유는 통과하지 않는다.

4요청/10판정 출현은 **고유 raw9개·전체 문맥3개·원래 사례 ID4개(c46, NA01, NA02, NLC-C04)·고유 원문 block 문자열11개**다. c46 원본이 두 번 등장하며 독립10사례가 아니다. 모두 개발 노출 자료다. c46 문맥의 DB canonical view10개는 보존됐고 관련 판정4개의 canonical 주소는 오프라인 진단에서 확인했다. NA/명시 반증의6판정은 기존 제공 텍스트의 evidence ID/정확 quote를 확인한 범위이며 원래 canonical_views=null을 DB 버전/parse 주소 검증으로 바꾸지 않는다.

## 같은 raw 오프라인 재처리의 안전한 경계

원래 실행기·parser·요청·criteria·raw·최초 실패는 수정하지 않았다. `offline_audit.json`은 별도 복사본에서만 진단하며 모델 호출0이다.

- normal_detail: 고정 사전 `supported→1`, `unsupported→2`, `contradicted→3` 중 실제 supported 두 곳만 치환한 복사본이 기존 엄격 parser를 통과했다. 라벨 의미·이유·근거·위치를 변경하지 않는다. 원래 출력 계약 실패를 소급 성공으로 바꾸지 않는다.
- condition: 입력의 유일 delete opcode는 X Event `[0,10)`과 Y Event `[0,0)`다. 모델의 X 인용과 정확히 대응하므로 서버 입력 유래의 삭제 위치를 확인할 수 있다. 빈 quote를 모든 위치에 허용하거나 비어 있지 않은 오류 절로 바꾸어 모델이 고른 구절로 표시하지 않는다. 기존 quote schema에서는 전체 응답이 여전히 실패한다.
- condition의 differences만 제외한 복사본으로 기존 judgment/error_span/evidence/canonical 주소를 따로 검사했다. 이는 **판정·근거 부분 진단**이며 전체 응답 계약 복구가 아니다. 이후 typed deletion span 계약을 만들더라도 필드·상대 인용·유일 opcode·정확 offset·입력 provenance를 검증하고 모호하면 거절해야 한다. 이번에는 제품 parser/출력 계약을 구현하지 않았다.

기술 수리로 원문 이유를 고치거나 조건 삭제를 반증/면제로 바꿀 수 없다. semantic prompt 재시도·정답 재작성·같은 입력 추가 모델 호출0이다.

## 미사용 확인 조사와 다음 설계

기존 노출 inventory와 현재 NA6호출·SC5호출 영수증을 대조했다. 부산 c/H/A/K/E/NLC/SL/AR/KR/BI/NA/SC 및 설계 gold가 노출된 pilot 목록에서는 **확정 가능한 미사용 기존 사례0**이다. 이는 열거한 보존 경로 범위의 결론이며 모든 과거 대화·삭제 자료·사전학습 비노출의 증명이 아니다. SC는 같은 기관의 별도 페이지였지만 지금은 이미 실행·노출됐다. 실패했던 기존 후보를 새 확인으로 이름만 바꾸지 않는다.

제안만 남긴다: 새로운 source 한 문맥의 고정 공동2요청, 정상 일부/상세 S/S와 허용/의무/무의무 S/U/U. 실제 source가 이 대조를 허용하는지 먼저 확인하고 전체 부모/예외를 보존하며 작성과 blind 독립 검토 뒤 기준을 동결한다. 다른 source에서도 정상 보존·U/C·추가 면제/금지 이유 없음·위치/근거/계약을 함께 확인해야 한다. 미사용 source 확보·새 후보/gold 작성·별도 확인 실행은 이번0이며 조율의 다음 결정과 자원 배정 전에는 시작하지 않는다. 작은 확인의 통과도 실제 저장 교정/일반 성능의 증거가 아니다.

## 비용·환경·자원·보존

| 신규 요청 | 입력 token | 출력 token | 모델 시간(초) | 요청/저장 elapsed(초) |
|---|---:|---:|---:|---:|
| normal_detail | 2168 | 496 | 37.991047 | 38.305745 |
| condition | 2087 | 533 | 40.181332 | 40.183520 |
| permission | 5339 | 817 | 73.620558 | 73.623810 |
| explicit_refutation | 2168 | 706 | 50.255593 | 50.257744 |
| 합계 | 11762 | 2552 | 202.048530 | 202.370819 |

신규4·기준선4재사용·재시도0. completion driver202.374842초, 적재/실행/종료 driver217.881268초, 엔진/GGUF 전체 해시 확인6.318413초다. 모델 시간은 prompt_ms+predicted_ms 합으로 준비·검토·대기 시간을 포함하지 않는다. 기존 응답의 과거 비용을 신규 비용에 합산하지 않는다. 4/4 EOS·비잘림·timings.cache_n=0이며 원시 tokens_cached의 별도 비영 값은 보존했다.

설치 `qwen3.8:27b-q4_K_M` 태그 digest `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`, native 엔진 전체 SHA `c8bbfac5e73a6f04f0dd2d91dde8f9934c0f1526b862f6129703be8d158a25db`, GGUF SHA `f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d`를 새로 확인했다. T0·seed42·ctx8192·n_predict2048·단일 슬롯·cache_prompt=false·cache-ram0·수동 ChatML 유지다. 현재 tokenizer의 기준선 token ID/전체 parameter 및 props(동적 media_marker 제외)가 정확히 같음을 확인한 뒤 재사용했다.

소유 PID63113의 정확 명령을 확인해 SIGTERM·exit0으로 종료했다. **2026-10-11 13:35:01 KST 당시** 11435 포트 닫힘·Ollama models=[]를 확인했다. 이후 제품 세션의 모델 사용은 건드리지 않는다. 종료 영수증은 `server_stop.json`이다.

Unicode/emoji/개행/반복/동일·삽입·삭제 문자 span과 재구성, 입력·원문·system 보존, 3후보 모든 쌍 selfcheck를 확인했다. 원본 동결/기준선/raw SHA 불변 및 감사 산술을 대조했다. 전체 테스트·재추출·Windows 실기·모델별 안정성/일반화·사람 시험·효용은 미실행/미측정이다.

원시4·그대로 재사용한 기준선4의 요청/응답/props/runtime·전체 입력/criteria·동결 코드·실제 driver·사후 감사·실패·자원 반환을 로컬 `data/knowledge/evaluations/business_candidate_text_diff_20261011/`와 `/Users/hyeongi/.codex/artifacts/business-candidate-text-diff-20261011/final`에 파일별 SHA로 보존한다. [구조화 결과](business_candidate_text_diff_20261011.json)는 공개 보고의 원문/raw 복사를 피하고 해시·경로·결과를 연결한다.

승인된 정확 초안으로 #655를 생성했고 승인된 완료 기록으로 #654 CLOSED를 확인했다. #655는 이 고정 비교와 기록 완료 범위이며 이후 확인/제품 채택을 의미하지 않는다. #616/#617/#620 제품 목표는 미완료다. 제품 코드/DB·README2·이전 연구0변경, 실제 자동 발견→편집/저장→같은 요구→그래프/검색/답변의 B1 연결0, c47 전후 재실행/B2/병합/배포0이다. 다음 기술 계약/새 확인 및 제품 연결은 조율이 별도로 판단한다. 현재 이 완료 기록에 사용자 결정이 필요한 사항 없음.

## 2026-10-11 새 평가 원칙에 따른 해석 보충 — #657

읽을 수 있는7/10→10/10·정상6보존은 분류 개선이며 최초 gate=false·숫자8/10·원계약2/4·condition.Y의 면제/배타성 추가 이유는 그대로 둔다. B1은 이미 A에 서버diff+주의문을 더한 구성이다. A+B1을 새 방법으로 세지 않는다. #657은 같은 입력에서 별도 differences 재작성 책임만 없애는 새 한 변경이며 분류100%를 단일 채택 문턱으로 쓰지 않는다. 당시 기준·원시 응답·실패를 소급 수정하지 않았다. [다음 비교 준비](business_diff_responsibility_plan_20261011.md).
