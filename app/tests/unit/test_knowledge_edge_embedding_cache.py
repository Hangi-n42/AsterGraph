from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from app.knowledge import graph_retrieval as gr
from app.tests.unit.test_knowledge_graph_retrieval import snapshot


class Encoder:
    def __init__(self):
        self.tokenizer = SimpleNamespace(encode=lambda text, **kwargs: list(text))
        self.max_seq_length = 100
        self.device = 'cpu'
        self.parameter = SimpleNamespace(dtype='float32')
        self.truncate_dim = None
        self.default_prompt_name = None
        self.prompts = {}
        self.dimension = 2
        self.calls = []
        self.failure = None

    def parameters(self):
        return iter([self.parameter])

    def get_sentence_embedding_dimension(self):
        return self.dimension

    def encode(self, texts, **kwargs):
        assert kwargs == dict(normalize_embeddings=True, show_progress_bar=False)
        self.calls.append(list(texts))
        if self.failure:
            raise ValueError(self.failure)
        return np.asarray([[1., 0.] if len(text) % 2 else [0., 1.] for text in texts])


@pytest.fixture
def encoder(monkeypatch):
    model = Encoder()
    monkeypatch.setattr(gr, 'encoder', lambda: model)
    return model


def test_exact_text_reuse_preserves_order_duplicates_float_and_current_pool(encoder):
    service = SimpleNamespace()
    first = gr.embed(['a', 'bb', 'a'], service=service)
    assert encoder.calls == [['a', 'bb']]
    assert first.dtype == np.dtype(float) and np.array_equal(first[0], first[2])
    changed = gr.embed(['bb', 'ccc', 'a', 'bb'], service=service)
    assert encoder.calls == [['a', 'bb'], ['ccc']]
    assert changed[[0, 2]].tobytes() == first[[1, 0]].tobytes()
    assert service._graph_edge_embedding_stats['reused_rows'] == 3
    gr.embed(['ccc', 'bb'], service=service)
    assert len(encoder.calls) == 2 and set(service._graph_edge_embedding_cache[1]) == {'ccc', 'bb'}
    changed[0] = 0  # Returned matrices cannot corrupt retained vectors.
    assert np.array_equal(gr.embed(['bb'], service=service), first[[1]])
    gr.embed(['bb'], service=SimpleNamespace())
    assert encoder.calls[-1] == ['bb'] and len(encoder.calls) == 3


@pytest.mark.parametrize('change', ['model', 'tokenizer', 'dtype', 'device', 'length', 'dimension', 'prompt'])
def test_actual_model_contract_changes_invalidate_cache(encoder, monkeypatch, change):
    service = SimpleNamespace()
    gr.embed(['a'], service=service)
    if change == 'model':
        replacement = Encoder()
        monkeypatch.setattr(gr, 'encoder', lambda: replacement)
    elif change == 'tokenizer':
        encoder.tokenizer = SimpleNamespace(encode=lambda text, **kwargs: list(text))
    elif change == 'dtype':
        encoder.parameter.dtype = 'float16'
    elif change == 'device':
        encoder.device = 'mps'
    elif change == 'length':
        encoder.max_seq_length = 90
    elif change == 'dimension':
        encoder.truncate_dim = 2
    else:
        encoder.default_prompt_name = 'query'
        encoder.prompts['query'] = 'query: '
    gr.embed(['a'], service=service)
    assert len(replacement.calls if change == 'model' else encoder.calls) == (1 if change == 'model' else 2)


@pytest.mark.parametrize('bad', [None, np.array([1.]), np.array([np.nan, 0.]),
    np.array([1., 0.], dtype=np.float32), np.array([0., 0.])])
def test_missing_invalid_or_wrong_dimension_vector_is_reencoded(encoder, bad):
    service = SimpleNamespace()
    gr.embed(['a'], service=service)
    service._graph_edge_embedding_cache[1]['a'] = bad
    gr.embed(['a'], service=service)
    assert encoder.calls == [['a'], ['a']]


def test_failure_and_incomplete_batch_are_not_cached_or_partially_committed(encoder, monkeypatch):
    service = SimpleNamespace()
    original = gr.embed(['a'], service=service)
    before = service._graph_edge_embedding_cache
    encoder.failure = 'native failure'
    with pytest.raises(ValueError, match='native failure'):
        gr.embed(['a', 'bb'], service=service)
    assert service._graph_edge_embedding_cache is before and set(before[1]) == {'a'}
    encoder.failure = None
    encode = encoder.encode
    monkeypatch.setattr(encoder, 'encode', lambda *args, **kwargs: np.ones((0, 2)))
    with pytest.raises(ValueError, match='관계 임베딩'):
        gr.embed(['a', 'bb'], service=service)
    assert service._graph_edge_embedding_cache is before
    monkeypatch.setattr(encoder, 'encode', encode)
    assert np.array_equal(gr.embed(['a', 'bb'], service=service)[[0]], original)
    assert encoder.calls == [['a'], ['bb'], ['bb']]


def test_current_pool_cache_has_a_byte_limit_and_still_checks_input_length(encoder, monkeypatch):
    monkeypatch.setattr(gr, 'EDGE_CACHE_BYTES', 16)
    service = SimpleNamespace()
    gr.embed(['a', 'bb'], service=service)
    assert service._graph_edge_embedding_stats['retained_bytes'] == 16
    assert set(service._graph_edge_embedding_cache[1]) == {'bb'}
    encoder.max_seq_length = 1
    with pytest.raises(ValueError, match='한도'):
        gr.embed(['bb'], service=service)
    assert len(encoder.calls) == 1


def test_same_text_shares_only_vectors_and_preserves_distinct_graph_items(encoder):
    source = snapshot()
    other = deepcopy(source['claims'][0])
    other.update(id='other-claim', chunk_id='other-chunk', source_version_ids=['v2'])
    other['evidence'][0].update(source_version_id='v2', parse_run_id='p2', block_id='other-block')
    source['claims'].append(other)
    before = deepcopy(source)
    graph, edges, passages, _ = gr.build(source, 'full')
    texts = [e['text'] for e in edges]
    vectors = gr.embed(texts, service=SimpleNamespace())
    repeated = [i for i, e in enumerate(edges) if e['text'] == '기관 허용 신청']
    assert len(repeated) == 2 and edges[repeated[0]]['id'] != edges[repeated[1]]['id']
    assert edges[repeated[0]]['claim_id'] != edges[repeated[1]]['claim_id']
    assert vectors[repeated[0]].tobytes() == vectors[repeated[1]].tobytes()
    assert len(encoder.calls[0]) == len(set(texts)) < len(edges)
    assert source == before and len(graph.edges) > len(edges) and len(passages) == 5
