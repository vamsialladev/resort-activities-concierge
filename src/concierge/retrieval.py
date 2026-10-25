"""Resort FAQ and policy search: BM25, optionally fused with embeddings (reciprocal rank fusion), property-filtered.

Documents are the Markdown files in data/docs (front matter: title, property). Each "## " section is one passage,
labelled "Title > Section" so an answer can cite it exactly. A search for one property sees that property's
passages and the shared ones, never the other property's.

RETRIEVAL=hybrid (default) uses rank-bm25 and fastembed (BAAI/bge-small-en-v1.5, ONNX, no PyTorch) and fuses the
two rankings with RRF (k=60). RETRIEVAL=bm25 uses BM25 only, and hybrid falls back to it if the model can't load
(no network on first start, say). docs/DECISIONS.md #3 has the measured trade-off: same recall on keyword
questions, 5 of 6 paraphrases found instead of 0, for about 260 MB of memory and 10 s of start-up.

Passages are data: instruction-like sentences are removed by guard.quarantine before a passage leaves this module.
"""

import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from concierge import config, guard

WORD = re.compile(r"[a-z0-9]+")
STOP = {
    "a", "an", "the", "of", "in", "on", "at", "for", "to", "and", "or", "is", "are", "can", "i", "we", "my", "our",
    "you", "your", "do", "does", "what", "how", "there", "it", "be", "with", "any", "me", "us", "this", "that",
}  # fmt: skip
SYNONYMS = {
    "kid": "kids children child",
    "kids": "children child kid",
    "children": "kids child",
    "child": "kids children",
    "son": "child children kids",
    "daughter": "child children kids",
    "toddler": "child under age",
    "massage": "spa treatment",
    "spa": "massage treatment",
    "free": "price charge",
    "cost": "price charge",
    "costs": "price charge",
    "price": "cost charge",
    "pay": "payment charge",
    "charged": "payment charge",
    "cancel": "cancellation cancelled",
    "refund": "cancellation charge",
    "rain": "weather",
    "boat": "cruise",
    "hike": "trek",
    "hiking": "trek",
    "walk": "trek stargazing",
    "swim": "pool",
    "swimming": "pool",
    "old": "age ages",
    "age": "ages",
    "confirm": "request pending approve",
    "booking": "request",
    "book": "request",
}
RRF_K = 60


@dataclass(frozen=True)
class Passage:
    id: str
    property: str
    title: str
    section: str
    text: str

    @property
    def label(self) -> str:
        return f"{self.title} > {self.section}"


def stem(word: str) -> str:
    for suffix in ("ing", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> list[str]:
    out = []
    for w in WORD.findall(text.lower()):
        if w in STOP:
            continue
        out.append(stem(w))
        out += [stem(s) for s in SYNONYMS.get(w, "").split()]
    return out


def parse(path: Path, root: Path) -> list[Passage]:
    raw = path.read_text(encoding="utf-8")
    meta, body = {}, raw
    if raw.startswith("---"):
        head, body = raw[3:].split("---", 1)
        meta = dict(line.split(":", 1) for line in head.strip().splitlines() if ":" in line)
        meta = {k.strip(): v.strip() for k, v in meta.items()}
    title = meta.get("title", path.stem)
    prop = meta.get("property", path.parent.name)
    out = []
    for i, block in enumerate(re.split(r"^## ", body, flags=re.MULTILINE)[1:]):
        section, _, text = block.partition("\n")
        text = " ".join(text.split())
        if text:
            rel = path.relative_to(root).as_posix()
            out.append(Passage(f"{rel}#{i}", prop, title, section.strip(), text))
    return out


def load(root: Path | None = None) -> list[Passage]:
    root = root or config.DOCS_DIR
    return [p for path in sorted(root.rglob("*.md")) for p in parse(path, root)]


class Embedder:
    """fastembed, loaded lazily (downloads ~67 MB of ONNX model on first use)."""

    MODEL = "BAAI/bge-small-en-v1.5"

    def __init__(self):
        from fastembed import TextEmbedding

        self.model = TextEmbedding(self.MODEL, cache_dir=str(config.EMBED_CACHE_DIR))

    def embed(self, texts: list[str]):
        import numpy as np

        vectors = np.array(list(self.model.embed(texts)))
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


class Index:
    def __init__(
        self,
        passages: list[Passage] | None = None,
        mode: str | None = None,
        embedder=None,
    ):
        self.passages = passages if passages is not None else load()
        self.mode = mode or config.RETRIEVAL
        self.bm25 = BM25Okapi([tokens(f"{p.title} {p.section} {p.text}") for p in self.passages])
        self.vectors = None
        if self.mode == "hybrid":
            try:
                self.embedder = embedder or Embedder()
                self.vectors = self.embedder.embed([f"{p.title}. {p.section}. {p.text}" for p in self.passages])
            except Exception:  # noqa: BLE001 - a missing model must not take the concierge down
                logging.getLogger(__name__).warning("embeddings unavailable; using BM25 only", exc_info=True)
                self.mode = "bm25"

    def _allowed(self, prop: str) -> list[int]:
        return [i for i, p in enumerate(self.passages) if p.property in (prop, "shared")]

    def search(self, query: str, prop: str, k: int | None = None) -> list[Passage]:
        k = k or config.TOP_K
        allowed = self._allowed(prop)
        scores = self.bm25.get_scores(tokens(query))
        bm25_rank = [i for i in sorted(allowed, key=lambda i: -scores[i]) if scores[i] > 0]
        if self.vectors is None:
            ranked = bm25_rank
        else:
            sims = self.vectors @ self.embedder.embed([query])[0]
            dense_rank = sorted(allowed, key=lambda i: -sims[i])
            fused = {}
            for rank_list in (bm25_rank, dense_rank):
                for r, i in enumerate(rank_list):
                    fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
            ranked = sorted(fused, key=lambda i: -fused[i])
        return [self.passages[i] for i in ranked[:k]]


def clean(passage: Passage) -> tuple[dict, bool]:
    """The passage as a tool result, with planted instructions removed."""
    text, removed = guard.quarantine(passage.text)
    return {
        "cite_as": passage.label,
        "property": passage.property,
        "text": text,
    }, removed


_INDEX: Index | None = None
_LOCK = threading.Lock()


def index() -> Index:
    """The shared index, built once per process (the first build loads the embedding model)."""
    global _INDEX
    with _LOCK:
        _INDEX = _INDEX or Index()
    return _INDEX


def warm_up() -> None:
    """Build the index in the background at app start, so the first FAQ question doesn't wait for the model."""
    threading.Thread(target=index, daemon=True).start()
