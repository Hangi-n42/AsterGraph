# AsterGraph 로컬 개발 실행

현재 제품은 지식 API와 Next.js 워크벤치입니다. 민원 서버·ChromaDB·replay seed는 필요하지 않습니다. 기존 실행 서버나 DB를 교체하지 말고 새 작업에는 별도 경로·포트를 사용합니다.

## 환경

Python 3.11 환경을 만들고 `python -m pip install -r requirements.txt`, Node.js 20.9 이상에서 `npm --prefix frontend ci`를 실행합니다. OS별 가상환경 활성화 방법을 사용하며, 다른 작업의 공유 환경은 삭제하거나 재설치하지 않습니다.

`.env.example`을 참고해 새 `.env`를 구성합니다. 이미 있는 `.env`를 덮어쓰지 않습니다.

```dotenv
API_HOST=127.0.0.1
API_PORT=8001
KNOWLEDGE_ENABLED=true
KNOWLEDGE_DB_PATH=data/knowledge/knowledge.db
EMBEDDING_DEVICE=cpu
```

`KNOWLEDGE_DB_PATH`는 절대 경로 또는 프로젝트 루트 상대 경로입니다. 서비스 생성 전에 경로를 확인합니다. 기존 결과 검증에는 복사 DB를 사용합니다. `KNOWLEDGE_ENABLED`의 코드 기본값은 false로 유지됩니다.

## 실행

API: `python scripts/run_api.py`.

화면: `frontend/.env.local`에 `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001`을 지정한 뒤 `npm run dev`. 충돌하면 `npm --prefix frontend run dev -- --port <별도 포트>`를 사용합니다. 화면 시작은 DB 초기화나 모델 실행을 하지 않습니다.

`http://127.0.0.1:8001/health`, `/api/v1/knowledge/sources`, `/docs`로 API를 확인합니다. 첫 화면은 `/knowledge`로 이동합니다. health 성공은 모델·검색 품질 검증을 뜻하지 않습니다.

## 모델·검색 경계

- Ollama 주소는 loopback HTTP 기본 주소만 허용합니다. 외부 공급자는 명시적 generation provider 설정이 필요합니다.
- 모델 태그와 문맥 상한은 `.env.example` 및 `app/core/config.py`를 확인합니다. `STRUCTURING_MODEL`은 기존 지식 구축 모델 환경변수 이름으로 보존했으며 민원 엔진을 실행하지 않습니다.
- 한국어 BM25·그래프 검색·토큰 계수는 유지합니다. 지식 API 시작·저장 자료 조회는 모델 호출 없이 가능합니다. 새 구축/검색 생성은 별도의 실행입니다.

## 검사

`python -m pytest app/tests/unit` / `npm --prefix frontend test` / `npm --prefix frontend run build -- --webpack`.
검증은 별도 임시 DB에서 수행하며 원본 DB·원시 응답·검수 상태를 바꾸지 않습니다. 신규 모델 호출이 없는 저장 재생 검사와 실제 생성 평가는 구분합니다.
