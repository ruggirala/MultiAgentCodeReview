"""
RAG layer for grounding security findings in OWASP Top 10 + curated CWE entries.

The retriever returns small text snippets that get spliced into the security
agent's prompt so its findings cite real vulnerability classes instead of
hallucinating CWE numbers.

Public surface:
    - corpus.OWASP_TOP_10, corpus.CWE_ENTRIES   — the data
    - retriever.SecurityRetriever                — ChromaDB-backed lookup
    - retriever.get_retriever()                  — module-level singleton
"""

from rag.retriever import SecurityRetriever, get_retriever

__all__ = ["SecurityRetriever", "get_retriever"]
