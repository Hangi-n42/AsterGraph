# 현재 기술 스택

Python 3.11 / FastAPI·Pydantic / SQLite / Next.js 16.2.3·React 19.2.4를 사용합니다. 버전 고정은 `requirements.txt`와 `frontend/package-lock.json`이 기준입니다.

- `app/knowledge`: 원문 파싱·출처 그래프·검수·부분 교정·지식 버전·탐색/검색
- `app/generation`: 모델 접속·loopback 주소 검사·입력 용량 계산
- `app/retrieval`: 한국어 BM25 토큰화와 공용 RRF 계산
- `app/evaluation`: 공용 데이터 로더·순위 지표
- 화면: Tailwind·Cytoscape 기반 지식 워크벤치

민원 엔진, ChromaDB, Streamlit, Leaflet은 현재 제품 경로에서 제거했습니다. 이전 스택·민원 평가는 분리 기준 커밋과 민원 저장소에 보존합니다. 현재 기능과 의미 품질·모델 성공률은 구분합니다.
