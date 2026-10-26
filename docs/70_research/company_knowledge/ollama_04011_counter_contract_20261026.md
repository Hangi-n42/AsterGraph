# Ollama 0.40.11 Qwen 텍스트 입력 계수 호환 — 2026-10-26

## 이유와 범위

`9b903252c91dc12037a10bef0e0f92f44cf0736e`의 실제 적용성 1회 검증 전에 현재 엔진이 0.40.11인 것을 확인했다.
기존 기준은 0.40.10이고 정확 계수 허용 목록도 그 버전까지였으므로 최초 준비는 생성 0회로 중단했다.
서버 변경·다운그레이드·재시작이나 버전 가드 우회 대신 공식 소스를 읽고 현재 Qwen 텍스트 계수 계약만 검증했다.

기존 9b worktree와 최초 차단 산출물은 보존했다. 별도 `codex/ollama-04011-counter` 브랜치에서 허용 버전·새 metaspace 모드 거부·해당 검사만 변경했다.
적용성의 메시지·스키마·참조·모델·요구·30조합·34블록과 49,152/8,192/1,000 한도는 변경하지 않았다.

## 공식 소스 근거

- Ollama [0.40.10](https://github.com/ollama/ollama/tree/f52b9e742d8c9a308f7b23cd1f0ab52c7ddb694d) → [0.40.11](https://github.com/ollama/ollama/tree/675150d6ad2747df1e218ef59de9194bc4a7e538): 실제 변경 파일 33개를 대조했다.
- `model/renderers/qwen35.go`의 qwen3.8 변형, renderer 선택, `server/prompt.go`, `llm/llama_server.go`, GBNF와 qwen35 parser, llama 호환 패치는 blob이 같다.
- [LLAMA_CPP_VERSION](https://github.com/ollama/ollama/blob/675150d6ad2747df1e218ef59de9194bc4a7e538/LLAMA_CPP_VERSION)은 b11803→b11845로 변경됐다. 이 의존성 변경도 별도로 조사했다.
- llama.cpp [b11803](https://github.com/ggml-org/llama.cpp/tree/a37cc46104eb50900d5ab4a9ba02a0abdac039db) → [b11845](https://github.com/ggml-org/llama.cpp/tree/9ff0d7e90f0faaa7c16017e6dcf9cf91c50a100e)의 sampler·grammar·JSON schema 변환·Unicode 파일도 같다. 전체 동일 blob 근거는 18개다.
- 변경된 [llama-vocab.cpp](https://github.com/ggml-org/llama.cpp/blob/9ff0d7e90f0faaa7c16017e6dcf9cf91c50a100e/src/llama-vocab.cpp)는 qwen35 정규식/타입/clean_spaces=false 분기와 BPE 병합 후반을 유지한다. 새 Nemotron 정규화는 해당 타입에만 적용된다.
- 공통 BPE에 새 `tokenizer.ggml.metaspace.prepend_scheme` 처리가 추가됐다. 실제 현재 모델에는 이 키·clean_spaces override·normalizer nfc/lowercase/strip_accents 키가 없다. metaspace 기본은 never이며 이번 모델은 새 모드가 발동하지 않는다.

제품 계수기는 새 metaspace 모드가 있는 모델을 조용히 지원하지 않는다. absent/never만 기존 경로로 처리하고 first/always/unknown/빈 값은 정확 계수 미지원으로 반환한다.
다른 메시지 이력·도구·매체·renderer·미검증 엔진의 기존 거부 경계도 유지했다.

## 실제 메타데이터와 검사

모델은 `qwen3.8:27b-q4_K_M`, digest `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`로 같다.
모델 parameters의 실제 키·값은 같고 원시 문자열 행 순서는 다르다. 이를 원시 hash 동일로 가장하지 않는다.
현재 엔진의 원시 `execution_identity`와, 정렬된 parameters를 포함하는 기존 budget configuration 지문을 따로 기록한다.
제품 runtime identity 전반을 리팩터링하지 않았다.

관련 단위 검사 38개가 통과했고 소켓 접속 시도는 0회다. 이 검사는 작은 byte-BPE/MockTransport fixture이며 실제 의미 효과 검증이 아니다.
그 뒤 현재 0.40.11 메타데이터와 검증된 로컬 모델 파일을 읽어 최초 고정 요청을 실제 정확 계수했다. 가짜 버전·예산 stub·추론 요청은 사용하지 않았다.

| 항목 | 토큰 |
|---|---:|
| 정확 prompt | 16,984 |
| 별도 schema 예약 | 575 |
| 출력 예약 | 8,192 |
| 안전 여유 | 1,000 |
| 합계 / 문맥 한도 | **26,751 / 49,152** |

계수 전후 `/api/ps`는 모델 점유가 없었다. 이 호환성 준비 단계의 생성은 0회다.
기존 보호 자료와 최초 차단 기록을 포함한 811개 파일의 해시를 확인했다.

## 다음 단계와 한계

현재 0.40.11에서의 연결 검증으로 별도 기록하며 0.40.10과 같은 추론 실행이나 수치·출력 동등성이라고 주장하지 않는다.
이전 응답은 새 엔진의 native 성공으로 재사용하지 않는다. 기존 configuration 7·6/6·remaining 0·no_reset은 유지한다.
다음은 고정 요청·현재 runtime·정확 예산을 전송 직전에 다시 대조한 후 승인된 적용성 생성 최대 1회와 저장/API GET뿐이다.
일반 R·join·교정은 결과를 조율 세션에 보고한 뒤 진행 여부를 결정한다. 현재 사용자 결정이 필요한 사항 없음.

근거 산출물:
`/Users/hyeongi/.codex/artifacts/retail-knowledge-pilot-20261018/retail_ollama_04011_counter_contract_20261026_v1`
