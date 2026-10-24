# 회사 지식·민원 활용 프론트엔드

- 문서 버전: v2.1
- 상태: 현재 구현 실행 안내
- 기준일: 2026-10-24
- 확인 범위: 현재 명령·API client·화면 파일. 변경 검증의 실행 범위와 결과는 해당 PR에 기록.

프로젝트의 주 제품은 [회사 지식 온톨로지·지식그래프](../docs/00_overview/company_knowledge_prd.md)이며, 이 디렉터리는 회사 지식 워크벤치(`/knowledge`)와 기존 민원 활용 UI를 제공한다. 지식 화면은 원문·출처 지식 버전·업무 검토·그래프 탐색·새 검색·저장 답변을 연결한다. 구현된 검색 계약과 의미 품질·사람 승인은 구분한다.

## 실행

Next.js 16.2.3 / React 19.2.4를 사용한다. Node.js >=20.9.0, Python 3.11.9 환경을 준비하고 저장소 루트에서:

```bash
npm --prefix frontend ci
```

`frontend/.env.local`에 실제 API 주소를 설정한다:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001
```

FE 코드 기본값은 8001, 백엔드 코드 기본값은 8000이다. 루트 `.env`의 `API_PORT`와 맞춰야 한다. Python 의존성·Ollama·Chroma·DB 준비 및 API 실행은 [로컬 개발 안내](../docs/30_manuals/local_dev_runbook.md)를 따른다.

Mac·Windows 공통 (루트):

```bash
npm run dev
```

일반 `dev`는 Next.js 화면만 시작하며 Python 준비 스크립트나 DB 초기화를 실행하지 않는다. 관제 자료가 없다면 명시적으로 준비한다.

```bash
# Mac: replay 준비에 사용할 Python
export CIVIL_PYTHON="$PWD/.venv/bin/python"
npm run replay:prepare
```

Windows PowerShell에서는 `$env:CIVIL_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path`로 선택한 뒤 같은 준비 명령을 사용한다. `CIVIL_PYTHON`은 셸 환경변수다. Node 준비 스크립트는 Next.js의 `.env.local`을 직접 읽지 않는다.

**`replay:prepare`는 민원 관제 replay DB를 초기화·재구성한다.** 기본 대상은 `data/complaint_intelligence/complaint_intelligence_real_replay.db`이며 `COMPLAINT_INTELLIGENCE_DB_PATH`와 별도로 정해진다. 기존 replay 검토·상태가 필요하면 먼저 백업한다. 회사 지식의 `KNOWLEDGE_DB_PATH`와는 별도 DB다. 같은 replay를 보려면 API도 준비한 파일을 사용해야 한다.

준비 명령은 기존 Python 옵션을 전달한다. 복사 seed와 저장소 내부의 별도 DB를 지정할 수 있다:

```bash
npm run replay:prepare -- --skip-build --seed tmp/replay/events.json --db-path tmp/replay/replay.db --run-report tmp/replay/report.json
```

`--input <경로>`를 명시하면 그 입력으로 seed를 빌드한다. `--skip-build`를 함께 명시하면 기존 seed만 사용한다. 저장소 밖 DB 초기화 차단과 빈 seed/PII 검사는 유지한다.

## 화면과 연결 코드

| 경로 | 현재 기능 |
|---|---|
| `/` | 민원 케이스 선택·진입 |
| `/workbench` | 검색 결과와 QA 답변 초안 |
| `/intelligence` | 관제 대시보드·급증·인사이트·중복 민원 |
| `/admin` | 관리자 통계 |
| `/knowledge` | 회사 지식 구축·검토·버전·탐색·검색·저장 답변 |

개발 주소는 `http://localhost:3000`이다. `lib/api.ts`가 API 주소와 호출·응답 변환을 담당하고 `lib/draft.ts`가 초안 관련 처리를 담당한다. 페이지 진입점은 `app/` 아래에 있다.

## 스크립트

| 명령 (`frontend`에서) | 용도 |
|---|---|
| `npm run dev` | DB 준비 없이 webpack 개발 서버 |
| `npm run replay:prepare` | 명시적 민원 replay 초기화·재구성 |
| `npm run build` | 배포 빌드 |
| `npm start` | 빌드된 Next.js 서버 |
| `npm run lint` | ESLint |
| `npm test` | Vitest 단회 실행 |
| `npm run test:watch` | Vitest 감시 모드 |

문서만 수정할 때 이 명령들을 모두 실행할 필요는 없다. FE를 변경할 때에는 영향받는 테스트와 필요한 빌드 확인만 수행한다. Next.js 코드를 수정하기 전에는 [AGENTS.md](AGENTS.md)와 설치된 `node_modules/next/dist/docs/`의 관련 가이드를 확인한다.

[프로젝트 문서 지도](../docs/README.md) · [회사 지식 구현 설계](../docs/05_plans/company_knowledge/implementation.md) · [회사 지식 마일스톤](../docs/05_plans/company_knowledge/milestones.md)
