"""검색 평가 데이터셋 로더."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class CorpusDocument:
    docid: str
    text: str
    title: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalQuery:
    qid: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QrelRecord:
    qid: str
    docid: str
    relevance: int


@dataclass(frozen=True)
class RetrievalEvalDataset:
    corpus: list[CorpusDocument]
    queries: list[EvalQuery]
    qrels: list[QrelRecord]
    eval_dir: Path | None = None
    eval_set_hash: str = ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_paths(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def load_eval_dataset(eval_dir: str | Path) -> RetrievalEvalDataset:
    root = Path(eval_dir)
    corpus_path = root / "corpus.jsonl"
    queries_path = root / "queries.jsonl"
    qrels_path = root / "qrels.tsv"

    corpus = load_corpus_jsonl(corpus_path) if corpus_path.exists() else []
    queries = load_queries_jsonl(queries_path)
    qrels = load_qrels_tsv(qrels_path)
    existing = [path for path in (corpus_path, queries_path, qrels_path) if path.exists()]

    return RetrievalEvalDataset(
        corpus=corpus,
        queries=queries,
        qrels=qrels,
        eval_dir=root,
        eval_set_hash=sha256_paths(existing),
    )


def load_corpus_jsonl(path: str | Path) -> list[CorpusDocument]:
    documents: list[CorpusDocument] = []
    for row in _iter_jsonl(Path(path)):
        docid = str(row.get("_id") or row.get("docid") or row.get("id") or "").strip()
        if not docid:
            continue
        metadata = dict(row.get("metadata") or {})
        for key, value in row.items():
            if key not in {"_id", "docid", "id", "text", "title", "metadata"}:
                metadata.setdefault(key, value)
        documents.append(
            CorpusDocument(
                docid=docid,
                text=str(row.get("text") or row.get("contents") or ""),
                title=str(row.get("title") or ""),
                metadata=metadata,
            )
        )
    return documents


def load_queries_jsonl(path: str | Path) -> list[EvalQuery]:
    queries: list[EvalQuery] = []
    for row in _iter_jsonl(Path(path)):
        qid = str(row.get("_id") or row.get("qid") or row.get("query_id") or row.get("id") or "").strip()
        text = str(row.get("text") or row.get("query") or "").strip()
        if not qid or not text:
            continue
        metadata = dict(row.get("metadata") or {})
        for key, value in row.items():
            if key not in {"_id", "qid", "id", "text", "query", "metadata"}:
                metadata.setdefault(key, value)
        queries.append(EvalQuery(qid=qid, text=text, metadata=metadata))
    return queries


def load_qrels_tsv(path: str | Path) -> list[QrelRecord]:
    qrels: list[QrelRecord] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                raise ValueError(f"qrels.tsv {line_number}번째 줄 형식이 올바르지 않습니다: {raw_line!r}")
            if line_number == 1 and parts[0].lower() in {"qid", "query_id"}:
                continue
            # 3컬럼(qid docid rel) 또는 TREC 4컬럼(qid iter docid rel) 모두 지원
            if len(parts) >= 4:
                qid, _, docid, relevance = parts[:4]
            else:
                qid, docid, relevance = parts[:3]
            qrels.append(QrelRecord(qid=str(qid), docid=str(docid), relevance=int(relevance)))
    return qrels


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path} {line_number}번째 줄은 JSON object여야 합니다")
            yield row

