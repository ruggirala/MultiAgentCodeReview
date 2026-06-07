"""Hybrid LLM backend: GPT-4o primary, CodeLlama-7B (4-bit) fallback."""

from llm.backend import call_llm, get_backend, LLMBackend

__all__ = ["call_llm", "get_backend", "LLMBackend"]
