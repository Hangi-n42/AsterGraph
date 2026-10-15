# B2 · 실제 모델 제안 before/after 공동 판단 — U/C 미해결

2026-10-11. 제품이 실제 제안했지만 동결 당시 저장하지 못한 SC03·SC04 수정본을 기존 A 공동 판단으로 비교했다. **after 단독은 S/S, 공동은 두 사례 모두 C/S**다. before 단독의 기존 C/C와 같아 공동의 추가 라벨 효과0이며 두 U/C 오류가 남았다. 사전 기대 U/S를 C/S로 바꾸지 않는다. **최초 gate=false·현재 B2 구성 제품 미채택**이다. B1의 문자 diff/주의문·alias/삭제 위치 계약과 결합하지 않았다.

## 실제 입력과 동결 비교

제품 `actual/SC03_proposal_for_B2.json`, `SC04_proposal_for_B2.json`의 before/after 전체 Event+Entity를 사용했다. 별도의 unchanged stored-before-after 파일은 비교 대상으로 쓰지 않았다. SC03 제안은 대상 한정을 Event와 Entity 모두에 되살렸고 SC04 제안은 의무를 허용으로 바꿨다. 이는 실제 native 편집 모델의 제안이며 동결 provenance의 edit_applied=false를 저장 성공으로 해석하지 않는다. 이후 제품의 별도 주소 수리/저장 성과는 이 연구와 구분한다.

전체 source8블록/부모6·제목/버전·예외/안내를 기존 singleton 문맥 그대로 보존했다. handoff는 start/end/DOM 표기, 기존 요청은 locator 표기로 달라 최초 준비 assert가 실패했다. id/text/evidence_ref/source version와 DOM order/selector·canonical span이 같은 것을 확인한 뒤 원래 문맥 형식을 유지했다. 다음 준비의 root import 실패도 명시 PYTHONPATH로 해결했다. 두 준비 실패는 모델0회 상태에서 보존했으며 동결 뒤 입력/코드 변경·모델 재시도0이다.

후보 지지/오류를 source에서 직접 대조해 before U·after S를 고정했다. SC03의 좁은 답사 대상 안내는 다른 관람객의 승인 의무 부정을 명시하지 않는다. SC04의 취소 가능 시한도 취소 의무의 명시 반대가 아니다. after를 실제 제안이라는 이유로 정답 취급하지 않고 해당 원문 주장을 독립 대조했다. 평가 label/gold·편집기 이유·provenance/적용 성공 여부는 판단 입력에서 제외했다. 기존 system/prefill/숫자·차이·근거 출력 계약·모델/설정은 그대로다.

after 단독 기준선이 없었으므로 공동 효과와 after 자체 지지를 분리하기 위해 **after singleton2+joint2**를 결과 전에 고정했다. before singleton2는 전체 prompt/현재 tokenizer token ID/parameter·engine/GGUF/props 일치 확인 뒤 저장 응답을 정확 재사용했다. 노출된 SC 두 사례의 실제 제안 적용 진단이며 새 A 판단 메커니즘이 아니므로 A 신규0·누적6 유지다.

| 비교 | 고정 기대 | 실제 | 출력 계약 | 의미 이유/위치 |
|---|---|---|---|---|
| SC03 after 단독 | S | S | 통과 | e4/e7의 답사 대상·행위와 Entity 일치 |
| SC04 after 단독 | S | S | 통과 | 개인예약 e2의 회차 전 취소 가능·부모 보존 |
| SC03 before/after 공동 | U/S | C/S | 실패 | 대상 확대를 명시 모순으로 오판. Entity 배열을 문자열 quote 주소로 반환 |
| SC04 before/after 공동 | U/S | C/S | 통과 | 의무/허용 차이는 찾았으나 허용과 의무가 양립 불가라고 과장 |

신규 라벨4/6·이유4/6, after 정상 출현4/4(고유2), before U/C 오류2다. 고유 raw4/같은 source문맥1의6판정 출현은 독립6사례가 아니다. SC03의 Entity quote는 실제 배열 원소와 대응한다는 관찰을 남기되, 기존 출력 계약에 배열 경로/index가 없어 정확한 후보 문자열 주소 성공으로 계산하지 않는다. 이 실패를 Event quote로 자동 옮기거나 이유/라벨을 사후 고치지 않았다.

source evidence 선택의 canonical 주소9참조/6판정은 별도 오프라인 source 주소 검사에서 확인했다. SC03 전체 계약 실패·두 의미 실패와 구분한다. 정확 source 주소가 U/C 판정을 입증하지 않는다. frozen parser가 통과한 요청은3/4이며 출력 계약 수리를 새 의미 개선으로 계산하지 않는다.

## 비용·자원·보존과 다음 작업

신규4·before2재사용·재시도0, 입력12848/출력1150 token, provider prompt+predicted 모델131.521847초·요청 elapsed합131.764233초·completion driver131.768207초·적재/종료 driver139.621370초·전체 hash 확인6.077409초다. 재사용의 과거 비용을 신규 비용에 합산하지 않는다. 실제4/4 EOS·비잘림·timings.cache_n=0, 원시 tokens_cached도 그대로 보존한다.

Qwen3.8 27B Q4_K_M 설치 태그/엔진/GGUF 전체 digest를 새로 확인했다. T0·seed42·ctx8192·출력2048·cache_prompt=false·cache-ram0·단일 슬롯·수동 ChatML 유지다. 소유 PID65651을 정확 command 확인 후 SIGTERM·exit0으로 종료했고 **2026-10-11 13:52:21 KST 당시**11435닫힘/Ollama models=[]를 저장했다. 이후 제품C 자원에 재적재하거나 개입하지 않는다.

입력/gold 제외·원문/부모/Entity 보존·AST·동결/raw/hash 불변과 감사 산술을 확인했다. 관련 구현을 바꾸지 않아 전체 테스트/재추출·c47 전후 재실행·Windows·반복 안정성·새 기관/사람 시험은 추가하지 않았다. 실제 저장/같은 요구/그래프/검색/답변의 B2 개선 증거0이며 전체 R05/#616/#617/#620 제품 목표는 별도 미완료다. 모델 검출로 손상된 before를 U로 회복하지 못했으므로 현재 공동 구성을 제품 기본에 연결하지 않는다.

원시4·before 재사용2의 원본/요청/props/runtime·실제 제안 handoff·준비 실패·전체 입력/criteria·동결 코드/driver·감사/자원 종료를 `data/knowledge/evaluations/business_actual_proposal_pair_20261011`와 `/Users/hyeongi/.codex/artifacts/business-actual-proposal-pair-20261011/final`의 파일별 SHA로 보존한다. [구조화 결과](business_actual_proposal_pair_20261011.json)는 원문/raw를 공개 보고에 복사하지 않는다.

다음은 제품의 주소 복원·저장 성과와 이 의미 검수 실패를 분리해 조율에 인계하고, B1의 새로운 자료 작성/블라인드 검토를 모델0회로 마치는 것이다. B1 확인이 남은 #655는 닫지 않는다. README2·기존 연구·제품 코드/DB 보존, 병합/배포0이다. 현재 사용자 결정이 필요한 사항 없음.
