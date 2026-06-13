"""
ChromaDB-backed retriever over the OWASP/CWE corpus.

Builds an in-memory ChromaDB collection on first use, embeds each document
with sentence-transformers' `all-MiniLM-L6-v2` (384-dim, ~80 MB model — runs
fine on CPU, fast on GPU). Module-level singleton so multiple agent calls
share the same index and embedder.

Used by `agents/security_agent.py` when `use_rag=True` is passed (see that
module for details). Designed to import cleanly even when chromadb /
sentence-transformers are missing — `get_retriever()` then raises a clear
ImportError so the caller can fall back to the non-RAG path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from rag.corpus import all_documents

DEFAULT_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_TOP_K = 4

_singleton: Optional["SecurityRetriever"] = None


@dataclass
class RetrievedDoc:
    """One hit from the retriever — id, title, the embedded text, and score."""

    id: str
    title: str
    text: str
    score: float


class SecurityRetriever:
    """
    Lazy ChromaDB index over the OWASP/CWE corpus.

    The index is built once on the first `query()` call and reused for the
    lifetime of the process.
    """

    def __init__(
        self,
        embed_model: str = DEFAULT_EMBED_MODEL,
        collection_name: str = "owasp_cwe_v1",
    ) -> None:
        self.embed_model = embed_model
        self.collection_name = collection_name
        self._collection = None
        self._embedder = None

    # --- lazy build ----------------------------------------------------

    def _build(self) -> None:
        """Create the ChromaDB collection and embed the corpus."""
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover — surfaces in Colab
            raise ImportError(
                "RAG requires chromadb and sentence-transformers. "
                "Install with: pip install chromadb sentence-transformers"
            ) from exc

        # Use the new in-memory client (replaces deprecated chromadb.Client()).
        client = chromadb.EphemeralClient()
        # If the collection already exists in this process, reuse it.
        try:
            self._collection = client.get_collection(self.collection_name)
            return
        except Exception:
            pass

        self._collection = client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"[rag] loading embedding model {self.embed_model}…")
        self._embedder = SentenceTransformer(self.embed_model)

        docs = all_documents()
        ids = [d["id"] for d in docs]
        texts = [f'{d["title"]}\n\n{d["text"]}' for d in docs]
        embeddings = self._embedder.encode(texts, show_progress_bar=False).tolist()

        self._collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=[{"title": d["title"]} for d in docs],
        )
        print(f"[rag] indexed {len(docs)} OWASP/CWE entries.")

    def _ensure(self) -> None:
        if self._collection is None:
            self._build()

    # --- query ---------------------------------------------------------

    def query(self, text: str, k: int = DEFAULT_TOP_K) -> list[RetrievedDoc]:
        """Return the top-k most-similar corpus entries to `text`."""
        self._ensure()
        # Embed the query with the same model (re-uses the cached embedder).
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(self.embed_model)
        q_emb = self._embedder.encode([text], show_progress_bar=False).tolist()
        result = self._collection.query(query_embeddings=q_emb, n_results=k)

        # ChromaDB returns parallel lists wrapped in an outer list (per-query).
        ids = result["ids"][0]
        docs = result["documents"][0]
        metas = result["metadatas"][0]
        # `distances` is cosine distance (lower=closer); convert to similarity.
        dists = result.get("distances", [[0.0] * len(ids)])[0]
        return [
            RetrievedDoc(id=i, title=m.get("title", ""), text=t, score=1.0 - d)
            for i, t, m, d in zip(ids, docs, metas, dists)
        ]


def get_retriever() -> SecurityRetriever:
    """Module-level singleton — one index per process."""
    global _singleton
    if _singleton is None:
        _singleton = SecurityRetriever()
    return _singleton


def format_context(hits: list[RetrievedDoc]) -> str:
    """Render hits as a compact prompt block to splice into the security agent."""
    if not hits:
        return ""
    lines = [
        "Relevant vulnerability classes (use these to label and explain "
        "your findings; cite the IDs in your `cwe` field where appropriate):",
        "",
    ]
    for h in hits:
        lines.append(f"- **{h.id} {h.title}** — {h.text.splitlines()[0]}")
    return "\n".join(lines)
