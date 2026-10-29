"""FastAPI 애플리케이션 진입점"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager

from app.api.error_utils import error_response, make_request_id
from app.core.config import settings
from app.core.logging import api_logger
from app.api.routers.knowledge import router as knowledge_router, shutdown_knowledge_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # 시작
    api_logger.info("API 서버 시작")
    api_logger.info(f"Ollama: {settings.OLLAMA_BASE_URL}")
    try:
        yield
    finally:
        shutdown_knowledge_service()
    # 종료
    api_logger.info("API 서버 종료")


# FastAPI 애플리케이션 생성
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(knowledge_router, prefix="/api/v1")


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request, exc: RequestValidationError):
    """FastAPI 기본 422를 공통 에러 래퍼로 통일한다."""
    return error_response(
        request_id=make_request_id(),
        error_code="VALIDATION_ERROR",
        message="요청 본문 형식이 올바르지 않습니다.",
        status_code=422,
        retryable=False,
        details={
            "path": str(request.url.path),
            "errors": exc.errors(),
        },
    )


# 헬스 체크 엔드포인트
@app.get("/health")
async def health_check():
    """API 상태 확인"""
    return {
        "status": "ok",
        "service": settings.API_TITLE,
        "version": settings.API_VERSION,
    }


# 버전 헬스 체크 엔드포인트 (contract alias)
@app.get("/api/v1/health")
async def health_check_v1():
    """API v1 상태 확인"""
    return await health_check()


# 루트 엔드포인트
@app.get("/")
async def root():
    """API 정보"""
    return {
        "title": settings.API_TITLE,
        "description": settings.API_DESCRIPTION,
        "version": settings.API_VERSION,
        "docs_url": "/docs",
        "endpoints": {
            "health": "/api/v1/health",
            "health_legacy": "/health",
            "knowledge": "/api/v1/knowledge",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
