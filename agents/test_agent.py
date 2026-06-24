"""
Test Generation Agent.

Generates a pytest suite for the patched code so the fixes can be validated.
Targets the public functions/classes identified by the Orchestrator and writes
tests for normal cases plus the edge cases the reviewers flagged.
"""

from __future__ import annotations

from agents.common import extract_code_block
from llm.backend import call_llm
from models.schemas import GeneratedTest, ReviewState

AGENT_NAME = "test_agent"

SYSTEM = (
    "You write clear, runnable pytest test suites that verify code does "
    "what it actually does, not what you wish it did."
)

PROMPT = """Write a pytest test suite for the Python code below.

ASSERT-ONLY-WHAT-THE-CODE-DOES RULES (important — most failures come from
ignoring these):
- Read the code carefully. Every assertion you write must reflect the
  actual implemented behavior, not the behavior you think would be "good."
- DO NOT assert that empty inputs return empty results, that None inputs
  raise specific errors, or that any other input validation happens —
  UNLESS the code visibly implements that validation.
- DO NOT invent edge cases beyond what the code handles. A test that
  fails because the code "should" do something is a broken test.
- When mocking, re-set return_value between calls if you change the
  expected output. A mock keeps returning the same value until you
  change it.
- Cover normal/expected behavior of each public function. If you can
  show a meaningful edge case the code DOES handle (visible from the
  source), include it. Otherwise stop.

Assume the code under test is importable from a module named `solution`
(i.e. use `from solution import ...`). Use only the standard library and
pytest. The proposer rewrites the placeholder `solution` to the real
module path before the test is committed — write tests as if the module
were truly named `solution`.

Respond with the complete test file inside a single ```python code block.

FUNCTIONS/CLASSES TO TEST: {symbols}

CODE UNDER TEST:
```python
{code}
```
"""


def generate(state: ReviewState) -> ReviewState:
    """Produce a pytest suite for the patched (or original) code."""
    try:
        code_to_test = state.patch.fixed_code if state.patch else state.source_code
        symbols = [c.name for c in state.chunks if c.kind in ("function", "class")]
        symbols_str = ", ".join(symbols) if symbols else "all public symbols"

        raw = call_llm(
            PROMPT.format(symbols=symbols_str, code=code_to_test), system=SYSTEM
        )
        test_code = extract_code_block(raw, "python")

        if not test_code:
            state.errors.append("test_agent: could not extract test code")
            test_code = "# Test generation failed to produce a usable suite.\n"

        state.tests = GeneratedTest(
            framework="pytest",
            test_code=test_code,
            covered_functions=symbols,
        )
        print(f"[test] suite generated for {len(symbols)} symbol(s).")
    except Exception as exc:  # noqa: BLE001
        state.errors.append(f"test_agent failed: {exc}")
        print(f"[test] ERROR: {exc}")
    return state
