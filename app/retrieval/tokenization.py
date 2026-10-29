"""한국어 BM25 토큰화. 민원 저장소/색인 로더에 의존하지 않는다."""
from __future__ import annotations


_KIWI_KEEP_TAGS = {"NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "XR", "SL", "SH"}

def _tokenize_korean(texts: list[str]) -> list[list[str]]:
    """kiwipiepy로 형태소 분석 후 의미 있는 어절만 반환."""
    from kiwipiepy import Kiwi

    kiwi = Kiwi()
    result = []
    for text in kiwi.tokenize(texts, normalize_coda=True):
        morphs = [t.form for t in text if t.tag in _KIWI_KEEP_TAGS and len(t.form) > 1]
        result.append(morphs if morphs else text.split() if isinstance(text, str) else [])
    return result

def _to_bm25s_tokens(tokenized: list[list[str]]):
    """형태소 분석 결과를 bm25s가 받을 수 있는 형태로 변환한다."""
    import bm25s

    # bm25s.tokenize는 문자열 리스트를 받으므로, 이미 분리된 토큰은 공백으로 합쳐서 넘긴다
    joined = [" ".join(tokens) for tokens in tokenized]
    return bm25s.tokenize(joined, stopwords=None)
