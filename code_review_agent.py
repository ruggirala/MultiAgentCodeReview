"""
Single Agent Code Review System
Reads a Python file, analyzes it using GPT-4o, and generates:
1. A review report (printed to console)
2. A fixed version of the code (saved as *_fixed.py)
"""

import os
import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

REVIEW_PROMPT = """You are an expert Python code reviewer. Analyze the following code and provide:

1. **ISSUES FOUND** — List each issue with:
   - Line number (approximate)
   - Category: [Security | Bug | Style | Performance]
   - Severity: [Critical | High | Medium | Low]
   - Description of the problem
   - Why it matters

2. **FIXED CODE** — Provide the complete corrected version of the code with all issues resolved.
   Place the fixed code between ```python and ``` markers.

Be thorough but practical. Fix real problems, not nitpicks.

CODE TO REVIEW:
```python
{code}
```
"""


def read_source_file(filepath: str) -> str:
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File '{filepath}' not found.")
        sys.exit(1)
    if not path.suffix == ".py":
        print(f"Error: Expected a .py file, got '{path.suffix}'")
        sys.exit(1)
    return path.read_text()


def review_code(source_code: str) -> str:
    prompt = REVIEW_PROMPT.format(code=source_code)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a senior Python developer performing a code review."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content


def extract_fixed_code(review_response: str) -> str | None:
    marker = "```python"
    start = review_response.rfind(marker)
    if start == -1:
        return None
    start += len(marker)
    end = review_response.find("```", start)
    if end == -1:
        return None
    return review_response[start:end].strip()


def save_fixed_code(original_path: str, fixed_code: str) -> str:
    path = Path(original_path)
    fixed_path = path.parent / f"{path.stem}_fixed{path.suffix}"
    fixed_path.write_text(fixed_code)
    return str(fixed_path)


def main():
    if len(sys.argv) < 2:
        print("Usage: python code_review_agent.py <path_to_python_file>")
        print("Example: python code_review_agent.py sample_bad_code.py")
        sys.exit(1)

    filepath = sys.argv[1]
    print(f"\n{'='*60}")
    print(f"  CODE REVIEW AGENT")
    print(f"  Reviewing: {filepath}")
    print(f"{'='*60}\n")

    source_code = read_source_file(filepath)
    print("Sending code to GPT-4o for review...\n")

    review_response = review_code(source_code)

    print(review_response)
    print(f"\n{'='*60}")

    fixed_code = extract_fixed_code(review_response)
    if fixed_code:
        output_path = save_fixed_code(filepath, fixed_code)
        print(f"\nFixed code saved to: {output_path}")
    else:
        print("\nWarning: Could not extract fixed code from response.")

    print()


if __name__ == "__main__":
    main()
