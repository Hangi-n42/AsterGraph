"""공용 로컬 모델 주소 검증. 민원 처리 엔진과 독립적으로 사용한다."""
from ipaddress import ip_address
from urllib.parse import urlsplit


def local_ollama_url(url: str) -> str:
    """Discovery permits loopback literals only; localhost cannot resolve externally."""
    parsed = urlsplit(url)
    host = parsed.hostname
    if parsed.scheme != 'http' or parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
        raise ValueError('discovery 모델 주소는 loopback HTTP 기본 주소여야 합니다.')
    host = '127.0.0.1' if host == 'localhost' else host
    if not host or not ip_address(host).is_loopback:
        raise ValueError('discovery 모델은 loopback에서만 호출할 수 있습니다.')
    return f"http://{'['+host+']' if ':' in host else host}:{parsed.port or 80}"
