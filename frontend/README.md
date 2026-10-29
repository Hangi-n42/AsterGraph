# AsterGraph 지식 워크벤치 화면

Next.js 16.2.3 / React 19.2.4. Node.js 20.9.0 이상을 사용합니다.

```bash
npm --prefix frontend ci
npm run dev
```

`frontend/.env.local`에 `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001`을 지정하고 API 포트와 맞춥니다. 화면 기본 API 포트는 8001, 백엔드 코드 기본값은 8000이므로 명시적으로 설정합니다.

- `/`: `/knowledge`로 이동
- `/knowledge`: 자료 등록, 구축·검수, 사용 버전, 그래프 탐색, 검색·저장 답변
- `lib/api.ts`: 공용 API 주소
- `lib/knowledgeWorkbench.ts`: 지식 API 요청·타입

민원 선택/처리/통계/Intelligence 화면과 replay 초기화 스크립트는 독립 저장소로 분리했습니다. 화면 시작은 DB를 초기화하거나 모델을 호출하지 않습니다.

검사: `npm --prefix frontend test` / 빌드: `npm --prefix frontend run build -- --webpack`.
Next.js 변경 전 [AGENTS.md](AGENTS.md)와 설치 패키지의 관련 안내를 확인합니다. API·DB 준비는 [로컬 개발 안내](../docs/30_manuals/local_dev_runbook.md)를 따릅니다.
