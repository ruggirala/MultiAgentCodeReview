"""
Orchestrator Agent.

Parses the input Python source into logical chunks (functions, classes) so the
analysis agents can reason about whole units rather than arbitrary line splits.

Uses tree-sitter when available (language-agnostic, robust), and falls back to
Python's built-in `ast` module otherwise — so this runs locally without the
tree-sitter wheels installed, and uses the richer parser on Colab.
"""

from __future__ import annotations

import ast

from models.schemas import CodeChunk, ReviewState


def _chunks_via_ast(source: str) -> list[CodeChunk]:
    """Extract top-level functions and classes using the stdlib AST."""
    chunks: list[CodeChunk] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Unparseable input — treat the whole file as one module chunk.
        lines = source.splitlines()
        return [
            CodeChunk(
                name="<module>",
                kind="module",
                start_line=1,
                end_line=len(lines) or 1,
                source=source,
            )
        ]

    lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            chunks.append(
                CodeChunk(
                    name=node.name,
                    kind=kind,
                    start_line=start,
                    end_line=end,
                    source="\n".join(lines[start - 1 : end]),
                )
            )

    if not chunks:
        chunks.append(
            CodeChunk(
                name="<module>",
                kind="module",
                start_line=1,
                end_line=len(lines) or 1,
                source=source,
            )
        )
    return chunks


def _chunks_via_tree_sitter(source: str) -> list[CodeChunk] | None:
    """Extract chunks with tree-sitter; return None if unavailable."""
    try:
        from tree_sitter import Parser
        from tree_sitter_languages import get_language
    except Exception:
        return None

    try:
        parser = Parser()
        parser.set_language(get_language("python"))
        tree = parser.parse(source.encode("utf-8"))
    except Exception:
        return None

    chunks: list[CodeChunk] = []
    wanted = {"function_definition": "function", "class_definition": "class"}
    for node in tree.root_node.children:
        if node.type in wanted:
            text = source.encode("utf-8")[node.start_byte : node.end_byte].decode(
                "utf-8", errors="replace"
            )
            name = "<anonymous>"
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = source.encode("utf-8")[
                    name_node.start_byte : name_node.end_byte
                ].decode("utf-8", errors="replace")
            chunks.append(
                CodeChunk(
                    name=name,
                    kind=wanted[node.type],
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    source=text,
                )
            )
    return chunks or None


def orchestrate(state: ReviewState) -> ReviewState:
    """Populate `state.chunks` from the source. Pipeline entry node."""
    chunks = _chunks_via_tree_sitter(state.source_code)
    if chunks is None:
        chunks = _chunks_via_ast(state.source_code)
    state.chunks = chunks
    print(f"[orchestrator] parsed {len(chunks)} chunk(s).")
    return state
