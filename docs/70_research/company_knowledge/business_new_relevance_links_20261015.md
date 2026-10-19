# 변경 영향의 새 관련 요구 기록 보완

기존 [#617](https://github.com/Hangi-n42/AsterGraph/issues/617)의 상태 기록 보완이다. 영향의 의미 판정이나 실제 모델 품질 개선으로 계산하지 않는다. 원래 W6 응답·DB·실패 기록은 보존했다.

## 원인과 기존 연결의 정의

`KnowledgeBusiness`는 `new_relevance`가 참일 때 `새 관련 요구`를 표시한다. W6의 실제 검수는 공휴일 요구를 `affected`로 판정했지만 provider 응답의 `new_relevance`는 `false`였다.

기존 직접 연결은 **변경 대상 원문 버전에 연결된 `current_assessment` 포인터**다. `source_ids`는 자료 선택 범위이며 평가·근거 연결의 증거가 아니다. 직접 연결 자체도 영향 확정이나 같은 block 내부의 의미 의존을 입증하지 않는다.

| 호출 경로 | 기존 동작 | 보완 |
|---|---|---|
| `business_changes.analyze` | 이전 판본 ID를 포함한 현재 평가 포인터로 직접 연결을 계산 | 같은 정의를 공통 함수로 유지 |
| `business_edit.recheck` | 다른 저장 요구의 평가 포인터와 무관하게 항상 `direct=[]` 전달 | 실제 편집 후보 전후 및 원문 해석 정정 근거의 판본 ID로 같은 연결 계산 |

편집 대상 판본 ID가 없거나 실행의 실제 출처 목록에서 확인되지 않으면 신규 연결을 확정하지 않는다. 내부 `direct=None`은 그 미확인을 나타내며 기존 원장의 `direct_dependency_ids` 목록 형식은 유지한다. 포인터 불일치·불가용은 기존 검수 보호에 따라 `unknown`이며 신규 표시도 거짓이다.

## 최소 변경과 경계

- `status`, `reason`, `change_ids`는 기존 원문 검수 결과와 기존 불가용·동시 수정 보호를 사용한다. 연결 없음으로 `unaffected`를 만들지 않는다.
- `new_relevance`만 변경 판본 범위를 확인했고, 검수가 `affected`이며, 해당 판본의 기존 평가 연결이 없는 경우 참으로 계산한다.
- `unaffected`·`unknown`·불완전 검수에서는 신규 표시를 남기지 않는다. `apply_impacts`가 동시 수정으로 `unknown`을 기록할 때도 신규 표시를 지운다.
- 모델 지시·스키마를 바꾸지 않았다. 원래 provider의 `new_relevance`는 실행 단위의 원응답에 남고, 연결 상태에서 계산한 값은 파생 영향 목록과 변경 이력에 저장된다.
- 승인·스냅샷·정상 평가 포인터·기존 원문을 변경하는 기능을 추가하지 않았다.

## 검사와 실제 저장 응답 재생

관련 세 검사 파일의 **40개 검사 통과**를 확인했다. 기존 연결·새 연결, 자료 범위만 선택한 요구, 다른 판본의 평가, 미확정/비영향, 불완전 응답, 불가용 포인터, 편집 후보·원문 해석 정정의 두 경로, 변경 판본 미확인, 평가 포인터 동시 수정 경계를 포함한다.

W6 원본 전체 DB를 각각 복사한 수정 전·후 사본에서 실제 `business_changes.analyze`를 호출했다. 두 요구의 시작 상태만 원래 변경 실행에 저장된 정확한 변경 전 요구 스냅샷으로 복원했다. 원문 diff를 다시 계산해 원본과 같은지 확인한 뒤 저장 응답의 실제 변경 ID를 재사용했다. 모델 요청의 messages/schema/reference_map이 원래 요청과 같은 경우에만 기존 응답을 재생했다. 모델·임베딩 접근은 차단했다.

| 항목 | 수정 전 재생 | 수정 후 재생 |
|---|---|---|
| 재생 run | `96dcb4046fd7464ba8bf386c2f77fd8e` | `fae5ddd03c254b5bbb209435ccc1c5bc` |
| 공휴일 판정 / 새 관련 표시 | `affected / false` | `affected / true` |
| 정기휴관 판정 / 새 관련 표시 | `unaffected / false` | `unaffected / false` |
| 공휴일 저장 상태 / 평가 포인터 | `needs_review / null` | 동일 |
| 정상 평가 포인터·상태·history | 기존 값 | 동일 |
| 판정 이유·변경 근거 / 원 provider 응답 | 원래 값 | 동일 |
| 새 모델·임베딩 호출 | 0 / 0 | 0 / 0 |

정상 핵심 필드의 전후 SHA256은 `53ce345a10a058270d2288578e4869882313e36a4a208d1fc5aa9aef291fe885`로 같다. 정상 전체 필드도 추가된 변경 이력을 제외하고 같다. 기존 baseline 실행의 전체 payload도 두 재생에서 같다.

원본 실행 DB SHA256 `c76fb4ee18f4cfa9531f5ae32c6902633f818cb2439edc2777373723aaa853b6`과 원본 W6의 `new_relevance=false`를 그대로 확인했다. 재생 비교 영수증은 `/Users/hyeongi/.codex/artifacts/company-knowledge-pipeline-20261015/w6_official_condition_pair_v1/new_relevance_replay_v1/comparison.json`이며 SHA256은 `b952173625ccb7ff1739af2e1828abf604ac645b5c4efb6afe245dac8c64ff93`이다.

## 결과와 남은 범위

새 관련 표시가 저장 연결과 일치하도록 기록을 보완했다. 원래 W6의 영향 의미 판정과 정상 보존 행동은 같다. 새 모델·추출·검수·QA 호출은 없으며 W3 실행과 동결 코드는 건드리지 않았다.

이 결과는 저장 응답의 기록·행동 재생 검증이다. 실제 의미 품질 개선, 새 모델 검수 성공, 같은 block 내부의 독립성, 일반적인 변경 영향 누락 감소를 입증하지 않는다. UI는 기존 boolean 표시 경로를 유지했고 전체 화면 검사를 반복하지 않았다. 상위 #617의 완료 여부는 기존 전체 기준과 함께 조정 채팅에서 판단한다. 현재 사용자 결정이 필요한 사항 없음.
