# R38 Entity 교체 보완 준비 (#654, A 누적4 유지)

2026-10-11. 기준 연구 HEAD `02923fb9ab184d70e1a30e6becc66c692610e0e7`. [#654](https://github.com/Hangi-n42/Civil-Complaints-System/issues/654)는 R38의 기계적 구성 결함 보완과 정상 보존 확인이다. **준비·정적 검사 완료, 신규 모델 호출0·자원 배정0·실제 tokenizer/runtime preflight 미실행**이다. 새 A-05·새 오류 검출·자동 교정·제품 완료로 계산하지 않는다.

## 실제로 배운 실패와 좁은 수정

[R38](business_source_limit_contrast_20261011.md)의 자동 선택은 c46에서 원문의 수식된 서류명을 골랐지만, 기존 서버는 이를 기존 서류명 앞에 삽입하여 명사를 중복시켰다. 모델 이유가 설명한 치환문과 저장된 삽입문도 달랐다. 원문 구절의 정확 주소와 삽입 밖 문자 보존은 문법·의미 구성 성공의 증거가 아니었다. 과거 입력·출력·판정·실패 gate·제품 후속 기록은 그대로 보존한다.

별도 연구 버전 [구성 함수](../../../scripts/compare_business_source_entity_replacement.py)는 기존 R38의 source/anchor/canonical 검사를 재사용한다. Event에서 자동 source quote의 시작 Entity에 괄호 수식이 이어지고, 그 Entity가 저장 목록·anchor·Event에 유일하게 연결된 경우 해당 Entity 문자열만 source quote로 교체한다. 조사·행위·다른 Event 문자열·Entity 배열·원문/부모/버전은 유지한다. 새 parser·업무 단어 하드코딩·새 LLM 선택/대조문 생성은 없다. 이 문자 연결은 의미 귀속을 보증하지 않는다.

저장된 3개 자동 선택의 새 구성 결과는 c46 `constructed_unverified`1, c13/c47 `unsupported`2이며 분모3을 유지한다. c46 대상 `[53:58]` 밖 문자열과 source 정확 주소가 보존됐다. 같은 저장 선택을 119후보에 대조했을 때 주소 조건을 충족한 대상은 c46 하나였으며 일반 적용률이 아니다. c13의 이미 있는 조건 재선택과 c47의 범위+양태 복합차이는 해결하지 않았다. source 수식은 날인 대상2곳을 포함하므로 한 문자 편집을 한 의미 차이로 승인하지 않는다.

## 검사와 원본 단독 재사용의 경계

- assert selfcheck: 유일 Entity 교체, 변경 밖 문자열/다른 raw/원문 부모 불변, 반복 Entity·반복 대상·기존 수식 재삽입 거부, 잘못된 source/anchor 거부를 확인했다. fixture는 주소 검사이며 의미 성과가 아니다.
- 실제 3건: 저장 선택만 재사용해 구성1/미지원2, c46의 정상 서류 목록·미방문 조건·기존 법인 조건은 교체 밖 문자열로 보존했다. 전체 입력/코드/기준 SHA를 동결하고 정적 preflight를 통과했다.
- 원본 c46 singleton의 prompt는 R37 저장 요청 및 실제 응답 prompt와 정확히 같다. 현재 준비 설정과 저장 요청 parameter, 저장 token1694개·응답 token count, 과거 R37/R38 props(동적 media marker 제외)·모델/엔진 SHA·실행 인자가 일치한다. 과거 응답의 기존 계약 파싱도 확인했다. **현재 tokenization은0이며 재사용 승인=false**다. 실제 자원 배정 후 적재 runtime/props와 tokenizer token ID를 대조한 경우만 원본 응답을 재사용한다.
- 준비 모듈 SHA-256: `7568d2d8dbdba2ec4016786c27b1e1ee0a6bd8b6fb590a5ad8cc9bcfa7b8e7c7`. 로컬 `data/knowledge/evaluations/business_source_entity_replacement_20261011/`의 `prepared.json`, `inputs.json`, `judgment_inputs.json`, `criteria.json`, `baseline_reuse.json` 및 `frozen_code/`에 실제 원형·교체본·출처·지문을 보존한다. 로컬 raw/원문은 이 문서에 복사하지 않는다.

## 필요한 경우의 최소 의미 비교 설계

조율의 자원·실행 결정 뒤 교체본 단독1+원본/교체본 공동1까지만 제안한다. 호출 할당량이 아니며 현재 실행 허가=false·token request=null이다. c1–c76 정상쌍, c13/c47 새 판단, 역순·새 선택·다른 prompt 탐색은 보류한다. 기존 연구 judge/원문/부모/모델/settings를 유지하며 생성 이유·평가 라벨·제품 교정문/gold를 판단 입력에 넣지 않는다.

판단 전에 원본S·교체본S의 원문 지지 정상 대조로 고정했다. 원본을 오류로 바꾸거나 수식 명시를 오류 발견으로 계산하지 않는다. 라벨 외 실제 추가 의미·문법·두 날인 대상·정확 오류 위치/원문/이유·정상 보존·단독 대비 공동 기여를 분리한다. 의미 차이가 없거나 복합이면 그대로 보고하며 한 범위 차이 성공으로 바꾸지 않는다. 현재 그 모델 의미 결과는 미실행이다.

열린 #617은 제품 후보 교정·보존, #620은 제품 종단 연결 범위이며 연구 전용 대조 구성의 별도 실행 단위는 명시하지 않았다. #653은 종료된 R38 비교다. 조율이 새로 만든 #654에 이번 준비를 연결했으며 이 세션은 이슈 생성/수정/종료0이다. A 누적4, 제품 기본 미채택, #616/#617/#620 미완료를 유지한다. 현재 사용자 결정이 필요한 사항 없음; 다음은 제품 join과 자원 조율 후 최소 진단 실행 여부를 정하는 것이다.
