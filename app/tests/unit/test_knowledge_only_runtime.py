"""The product boots and persists sources without civil engines or model calls."""
import json
import sys

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routers import knowledge
from app.generation.endpoint import local_ollama_url


def test_knowledge_only_startup_storage_and_retired_routes(tmp_path, monkeypatch):
    knowledge.shutdown_knowledge_service()
    monkeypatch.setattr(knowledge.settings, 'KNOWLEDGE_ENABLED', True)
    monkeypatch.setattr(knowledge.settings, 'KNOWLEDGE_DB_PATH', str(tmp_path / 'isolated.db'))
    raw = '상품,보관\n두부,냉장\n'.encode()
    with TestClient(app) as client:
        assert client.get('/health').json()['status'] == 'ok'
        assert client.get('/api/v1/health').status_code == 200
        paths = client.get('/openapi.json').json()['paths']
        assert all(p in {'/', '/health', '/api/v1/health'} or p.startswith('/api/v1/knowledge/') for p in paths)
        for path in ['/api/v1/search', '/api/v1/qa', '/api/v1/ui/cases', '/complaint-intelligence/dashboard']:
            assert client.get(path).status_code == 404
        reply = client.post('/api/v1/knowledge/sources',
            files={'file': ('products.csv', raw)},
            data={'metadata': json.dumps(dict(title='독립 자료', publisher='검사', namespace='split', external_id='one'))})
        assert reply.status_code == 200
        saved = reply.json()['data']
        url = f'/api/v1/knowledge/sources/{saved["source_id"]}/versions/{saved["source_version_id"]}'
        assert client.get(url + '/raw').content == raw
        first = client.get(url).json()['data']
        assert first['version']['processing_status'] == 'registered'
        assert client.get('/api/v1/knowledge/workbench/scopes').status_code == 200
    assert knowledge.get_knowledge_service.cache_info().currsize == 0
    # Reopen the actual configured DB through the product lifespan, not a replacement router.
    with TestClient(app) as client:
        assert client.get(url).json()['data'] == first
        assert client.get(url + '/raw').content == raw
    assert not any(n.startswith(('app.complaint_intelligence', 'app.structuring', 'app.generation.service')) for n in sys.modules)


@pytest.mark.parametrize(('url', 'expected'), [
    ('http://localhost:11434/', 'http://127.0.0.1:11434'),
    ('http://127.0.0.1:11434', 'http://127.0.0.1:11434'),
    ('http://[::1]:11434', 'http://[::1]:11434'),
])
def test_shared_model_address_preserves_loopback(url, expected):
    assert local_ollama_url(url) == expected


@pytest.mark.parametrize('url', [
    'https://localhost:11434', 'http://example.com:11434', 'http://192.168.0.1:11434',
    'http://user:secret@localhost:11434', 'http://localhost:11434/api',
    'http://localhost:11434/?x=1', 'http://localhost:11434/#x',
])
def test_shared_model_address_does_not_relax_remote_or_path_guards(url):
    with pytest.raises(ValueError):
        local_ollama_url(url)
