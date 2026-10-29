"""
프로젝트 설정 관리

환경 변수와 기본 설정값을 로드하고 관리한다.
"""

import os
from pathlib import Path

# 기본 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIGS_DIR = PROJECT_ROOT / "configs"
LOGS_DIR = PROJECT_ROOT / "logs"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except Exception:
    # dotenv is optional. Runtime environment variables and code defaults still work.
    pass


class Settings:
    """회사 지식 런타임 설정. 기존 모델·검색 기본값은 유지한다."""
    API_TITLE: str = "AsterGraph Knowledge API"
    API_VERSION: str = "0.1.0"
    API_DESCRIPTION: str = "출처 기반 기업 지식 구축·검수·갱신 및 검색 API"
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", 8000))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    KNOWLEDGE_ENABLED: bool = os.getenv("KNOWLEDGE_ENABLED", "false").lower() == "true"
    KNOWLEDGE_DB_PATH: str = str(PROJECT_ROOT / os.getenv("KNOWLEDGE_DB_PATH", "data/knowledge/knowledge.db"))
    KNOWLEDGE_SEARCH_MODEL: str = os.getenv("KNOWLEDGE_SEARCH_MODEL", "")
    KNOWLEDGE_REVIEW_MODEL: str = os.getenv("KNOWLEDGE_REVIEW_MODEL", "qwen3.8:27b-q4_K_M")
    KNOWLEDGE_GENERATION_PROVIDER: str = os.getenv("KNOWLEDGE_GENERATION_PROVIDER", "ollama")
    KNOWLEDGE_GENERATION_ENDPOINT: str = os.getenv("KNOWLEDGE_GENERATION_ENDPOINT", "")
    KNOWLEDGE_GENERATION_AUTH_ENV: str = os.getenv("KNOWLEDGE_GENERATION_AUTH_ENV", "KNOWLEDGE_API_KEY")
    KNOWLEDGE_GENERATION_CONTEXT_LENGTH: int = int(os.getenv("KNOWLEDGE_GENERATION_CONTEXT_LENGTH", "49152"))
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma4:31b-it-q4_K_M")
    OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", 180))
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    EMBEDDING_DEVICE: str = os.getenv("EMBEDDING_DEVICE", "cpu")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    API_LOG_FILE: str = str(LOGS_DIR / "api" / "app.log")
    PIPELINE_LOG_FILE: str = str(LOGS_DIR / "pipeline" / "pipeline.log")
    EVALUATION_LOG_FILE: str = str(LOGS_DIR / "evaluation" / "evaluation.log")

    # 지식 구축 모델의 기존 환경변수 이름. 민원 엔진과 무관하게 호환 유지.
    STRUCTURING_MODEL: str = os.getenv("STRUCTURING_MODEL", "gemma4:31b-it-q4_K_M")


settings = Settings()
