"""Frozen lexical ranking shared by source graphs and business review."""
from collections import defaultdict
import re


class FrozenIndex:
    """One in-memory index per execution; only ranking utilities from K6 are reused."""
    def __init__(self, blocks, *, preserve_numbers=False):
        import bm25s
        from app.retrieval.tokenization import _tokenize_korean, _to_bm25s_tokens
        self.blocks = blocks
        def tokenize(texts):
            tokens = _tokenize_korean(texts)
            if preserve_numbers:
                for text, row in zip(texts, tokens):
                    row.extend('numeric_' + n.replace('.', '_') for n in
                               re.findall(r'(?<![0-9A-Za-z_.])\d+(?:\.\d+)?(?![0-9A-Za-z_.])', text))
            return tokens
        self.tokenize = tokenize
        self.convert = _to_bm25s_tokens
        self.tokens = self.tokenize([b['text'] for b in blocks])
        self.engine = bm25s.BM25()
        self.ready = bool(blocks and any(self.tokens))
        if self.ready:
            self.engine.index(self.convert(self.tokens), show_progress=False)

    def rank(self, query, allowed):
        """Raw positive-score ranking, before consumer-specific selection policies."""
        if not self.ready:
            return []
        tokens = self.tokenize([query])
        if not tokens[0]:
            return []
        ids, scores = self.engine.retrieve(self.convert(tokens), k=len(self.blocks), show_progress=False)
        return [dict(block_id=self.blocks[int(index)]['id'], score=float(score),
                     file_id=self.blocks[int(index)]['file_id'])
                for index, score in zip(ids[0], scores[0])
                if float(score) > 0 and self.blocks[int(index)]['id'] in allowed]

    def search(self, query, allowed, limit=6):
        blocks = {b['id']: b for b in self.blocks}
        groups, duplicates, seen = defaultdict(list), [], set()
        for hit in self.rank(query, allowed):
            block = blocks[hit['block_id']]
            text = re.sub(r'\s+', '', block['text'])
            if text in seen:
                duplicates.append(hit)
            else:
                groups[block['source_group']].append(hit); seen.add(text)
        ranked = []
        while groups:
            for key in list(groups):
                ranked.append(groups[key].pop(0))
                if not groups[key]:
                    del groups[key]
        return (ranked + duplicates)[:limit]
