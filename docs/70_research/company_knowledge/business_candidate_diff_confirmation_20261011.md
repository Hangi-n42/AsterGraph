# B1 국립생태원 새 원문 확인 결과 · 2026-10-11

**결론: 비교 완료·현재 기본 경로 제품 미채택.** 동일 공통 기술 parser로 평가한 baseline/diff 모두 라벨8/8·정상4/4·오류4/4이며 추가 라벨 개선0·회귀0·동일8이다. legacy와 공통 기술 계약은 모두2/3, whole 계약 수용 판정도5/8씩이다. 개별 이유 개선1건은 보존하지만 차이 설명의 범위 오독과 장비 출력 계약 실패로 양쪽 전체 gate=false다. A누적6 유지, 새 기제/A07은 아니다.

## 같은 입력·설정의 실제 비교

[준비 계획](business_candidate_diff_confirmation_plan_20261011.md) 커밋 `1d3f7e1`과 원문5,033자·40블록/8부모·후보v2 8개·골드·system·순서·기술 parser를 유지했다. 정상C01/C08의 부분/상세 사실, 허용/의무/비지정 장소, 유모차/휠체어 범위 3묶음이다. 작성/블라인드 합의8/8·미확정0은 사전 기준이며 제품 출력의 외부 채점은0이다. source는 공식 [국립생태원 이용안내](https://www.nie.re.kr/nie/main/contents.do?menuNo=200212)다.

baseline3 후 diff3의6신규, 재사용0. 각 조건 고유8판정, 총16출현은 독립16사례가 아니다. user 입력에는 context/candidate raw와 diff 조건의 문자 diff+기존 고정 주의문만 있다. gold/기대라벨/작성해설은 모델에 전달하지 않았다. 원문 밖 면제/허용/금지를 추가하지 않는 사전 기준과 실패 분모를 유지했다.

전체 token preflight에서 최대입력9,191+출력2,048=11,239로 ctx8192에 맞지 않았다. **첫 판단 호출 전에 baseline/diff 모두 ctx11264**를 고정·기록했다. 원문 삭제0·후보/지시/출력변경0, 재기동 뒤 모든 token ID 동일을 확인했다. 실제 native Qwen `qwen3.8:27b-q4_K_M`, temperature0·seed42·output2048·cache_prompt=false·no-context-shift·단일슬롯이다. 과거자료와 ctx가 달라진 새 확인이며 과거 응답 재사용은 없다.

| 묶음 | 기대 X/Y/Z | baseline | diff | legacy/기술 계약 |
|---|---|---|---|---|
| normal_detail · C01/C08 | S/S | S/S | S/S | 양쪽 통과 |
| permission_place · C02/C03/C04 | S/U/C | S/U/C | S/U/C | 양쪽 통과, 차이 이유 한계 유지 |
| equipment_scope · C05/C06/C07 | S/C/U | S/C/U | S/C/U | 양쪽 실패, 원시 라벨은 유지 |

## 실패와 부분 개선

- **허용→의무 C03:** baseline 개별 이유는 raw에 없는 “하다람쉼터에서만”을 추가하고 다른 지정 장소 허용을 그 강화된 주장의 미지지 근거로 사용했다. diff의 개별 이유는 “먹어야 한다”는 식사 의무가 원문에 없음을 설명해 개선됐다. 그러나 양쪽 differences X/Y는 “해당 장소에서만 먹어야 한다”를 남겼다. 실제 Y의 식사 의무와 장소 배타성은 같은 주장이 아니다. 개별 이유7/8→8/8을 전체 gate 회복으로 확대하지 않는다.
- **장비 baseline:** Z만 있는 difference row가 최소2후보 pair 계약에 실패했다. Z의 U 이유와 원문 근거는 옳지만 전체 응답 계약은 실패다.
- **장비 diff:** difference의 X/Event quote “유모차”는 해당 Event에서2회라 위치가 유일하지 않다. Y/Z error_spans는 Entity 배열을 문자열 필드로 인용했다. quote는 실제 배열 원소지만 field/path/index 주소를 갖춘 문자열 인용이 아니며 사후 path 생성/계약 완화를 하지 않았다. Y의 C와 Z의 U 및 이유는 옳다. 실제 Event 오류구절 유효성과 Entity 추가 실패를 분리한다.
- **정상 보존:** 부분 사실 C01과 상세 C08 모두 양쪽S다. 생략 자체를 오류로 처리하지 않았고 안내견 예외·등 표현을 보존했다. 정상4/4·U2/C2 보존은 유용하지만 baseline도 같아 새 오류검출 추가 효과는0이다.

16판정의 관련 원문 근거·보존 원문 주소(23개 참조)를 확인했다. 실제 Event 오류구절8/8은 정확하나 전체 오류 인용 계약은 baseline4/4·diff2/4다. 일부 인용은 Event 전체를 가리켜 가장 작은 오류 구절 특정의 증거로 쓰지 않는다. 차이/Entity 실패를 제외한 진단은 전체 계약을 복구하지 않는다. 문구 alias·typed 빈좌표의 사후 수용은 이6응답에서0이며 양쪽 같은 parser로 최초 계약 실패를 그대로 보존했다.

## 호출량·실측 비용

| 항목 | baseline3 | diff3 |
|---|---:|---:|
| 입력 token | 20,573 | 24,980 |
| 출력 token | 2,254 | 2,526 |
| 모델 prompt+generation 초 | 231.955870 | 281.896161 |
| 요청 elapsed 합 초 | 232.221701 | 281.905011 |

전체6신규 입력45,553/출력4,780·모델513.852031초·요청elapsed합514.126713초·completion driver514.133066초다. 적재·ctx 재기동·실행 전 설정 확인 대기·실제 종료를 포함한 driver는537.634930초, 해시검증5.998319초는 이 안의 별도 구간이다. 연구 준비·사후 검토·커밋의 전체 경과 시간은 아니다. 이 묶음에서 diff 입력+4,407(21.42%)·모델+49.940291초(21.53%)를 관찰했다. 일반 속도 효과나 금전 비용을 확정하지 않는다.

EOS6/6·잘림0·실행오류0·실제전체입력token 일치6/6·timings cache_n0/6이다. 원시의 별도 tokens_cached 값을 재사용 cache hit로 해석하지 않는다. 준비 때 두 Astra 세션의 누적 API usage는 [준비 기록](business_candidate_diff_confirmation_plan_20261011.md)에 있으며 이 native 비용과 합치지 않는다.

## 환경·자원 종료·검사 기록

engine SHA `c8bbfac5e73a6f04f0dd2d91dde8f9934c0f1526b862f6129703be8d158a25db`, GGUF SHA `f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d`와 설치 tag manifest를 확인했다. 최초 ctx8192 PID69538은 tokenize preflight만 수행했고 최종 ctx11264 PID69540에서6판단을 실행했다. 두 소유 command를 확인해 SIGTERM/exit0, **14:29:49 KST 포트11435닫힘·Ollama models=[]**를 확인하고 제품 세션에 자원을 반환했다. 이후 제품 자원 상태를 재조회하지 않았다.

원문/후보/골드/기준/준비/실행freeze·의존코드·raw SHA를 확인했다. 원래 B1/B2 final archive도 불변이다. execution AST와 git diff check, README2 SHA 보존을 확인하며 제품 코드/DB·merge/deploy는 변경하지 않았다. 관련 오프라인 검사만 실행했고 제품 전체 테스트는 실행하지 않았다.

최초 사후 감사는 “모든 개별 판단 계약이 유효”하다고 가정해 Entity 인용에서 실패했다. 원래 코드/실패를 보존하고 같은6응답의 source 주소와 Event 인용을 분리 검사했다. 새 모델/원시 수정/실행 parser 수리/계약 회복0이다. runtime metadata도 그대로 보존한다. 첫 server_starts의 args는 공유 list 재사용으로 나중 ctx11264가 표기됐으나 당시 log는8192를 확인한다. 과거 reference에서 복사된 same_runtime_as_baseline flag는 이전 ctx8192와의 동일성 증거로 사용하지 않았다. 실제6회는 requests/props/log의11264로 고정됐다. 이 기록상의 한계는 `runtime_metadata_errata.json`에 남기며 실행 실패나 결과 변경으로 세지 않는다.

## 종합 결정과 보존

최초B1의 개발7/10→10/10 부분 효과·원래 gate=false/condition 이유 실패를 보존한다. 새 확인은8/8→8/8·추가 라벨 효과0·전체gate=false다. B2의 실제 수정본 대조에서도 joint 추가 효과0·U/C 반증 오류가 남았다. 조율의 원문/최종6 raw 독립 대조와 함께 현재 기본 경로를 미채택했다. A06의 같은 가설 확인이므로 최종 A누적6, 설정·예제·prompt·parser 완화·seed반복 등 추가모델0이다. A계열 전체 불가능을 확정한 결과는 아니다.

#655는 이 연구 비교 종료·제품 미채택 범위로 완료댓글/닫기를 커밋 후 처리한다. #616/#617/#620 및 실제 제품 자동 발견→교정→같은 요구/그래프·검색·답변의 전체 완료를 주장하거나 종료하지 않는다.

- 원문/v1·v2/gold/blind/준비 동결: `/Users/hyeongi/.codex/worktrees/business-semantic-research/Civil-Complaints-System/data/knowledge/evaluations/business_candidate_diff_confirmation_20261011`.
- 실제6 요청/설정·raw·원래 실패·주소/의미 감사·자원 receipt: `/Users/hyeongi/.codex/worktrees/business-semantic-research/Civil-Complaints-System/data/knowledge/evaluations/business_candidate_diff_confirmation_20261011/execution`.
- 별도 최종 보존 묶음: `/Users/hyeongi/.codex/artifacts/business-candidate-diff-confirmation-20261011/final`. prepared 보존 묶음과 최초 freeze를 덮어쓰지 않는다.

## 제품 최종 연결 기록의 별도 동기화

제품 checkout의 HEAD/원격 SHA `7d85edff21170550c69c1a1794e573a3b0837d6b` 일치와 clean 상태를 읽기 전용으로 확인하고 [SC03 실제 편집/저장·후속 검수 보고](https://github.com/Hangi-n42/Civil-Complaints-System/blob/7d85edff21170550c69c1a1794e573a3b0837d6b/docs/70_research/company_knowledge/business_auto_finding_extension_20261011.md) 및 [C 결합 관계 비교/회수 보고](https://github.com/Hangi-n42/Civil-Complaints-System/blob/7d85edff21170550c69c1a1794e573a3b0837d6b/docs/70_research/company_knowledge/business_conjunction_relations_20261011.md)의 Markdown/JSON 전체를 대조했다. 제품 raw/DB·76검사를 이 연구에서 다시 실행한 것은 아니다.

제품 기본에 남긴 코드 경계는 교정 task 전달 분기와 동일 문장의 모든 문자 주소 복원이다. SC03은 실제 편집 응답의 Event/Entity/Scope를 바꾸지 않고 저장했다. 현재 raw/Scope의 현장 답사 희망자·방문 전·유선 AND 서면·사전 승인이 원문과 일치한다는 제품 AI 원문 대조 성과와 direct1의 SC01/SC02/SC03 supported를 보존한다. 공식·사람·일반화 품질 결과는 아니다.

자동 before_normal 보존 receipt는 정정된 주체/범위와 신규 누리집 참조를 기존 정상 내용과 혼동해 실패했다. 실제 기존 행위·시점·유선/서면 내용 유지의 원문 대조와 이 잘못된 자동 preserved 판정은 별도다. 한 receipt를 세 독립 의미 오답으로 합산하지 않는다. eligible=[]·SC03 normal_meaning_preservation_unconfirmed, SC04 unresolved/Scope obligation-permission 모순과 최초 SC03/SC04 U→C 오판을 유지한다.

source4의 원문 의미38/필수32는 질문 밖 필수 전파와 날짜 적용성의 한계가 남아 전체 요구 정확성으로 채택되지 않았다. whole R/QA0, 운영 graph/search/QA·#616/#617/#620 미완료다. C1의 k1 복합 처리 추론과 잘못된 gap 해소는 실패로 보존하고 전용 실험 코드는 실제 회수했다. 제품신규8(edit2/source4/direct1/C1)·C 국소12 exact 재사용·회수 후 관련76 pass는 제품 보고의 해당 실행 수치이며 연구6신규나 A누적6에 더하지 않는다. 이 단계는 제품 파일 수정·새 모델 호출0이고 연구 diff/joint judge 미채택 결론을 바꾸지 않는다.

## 2026-10-11 새 평가 원칙에 따른 해석 보충 — #657

NIE baseline/diff8/8 동률은 그 자료의 추가분류 이득0이고 핵심 실패 개선 가능성의 기각 근거가 아니다. B1의 C03 개별 이유7/8→8/8 개선과 differences의 후보에 없는 장소 배타성 과장을 분리한다. #657에서 NIE는 이미 올바른 개별 이유 보존·중복 오류 출력 제거/비용 대조이고 새 개별 이유 개선 대상으로 세지 않는다. 최초 계약/전체 gatefalse·기본 제품미채택은 보존한다. 당시 기준·원시 응답·실패를 소급 수정하지 않았다. [다음 비교 준비](business_diff_responsibility_plan_20261011.md).
