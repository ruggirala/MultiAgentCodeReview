"""
Builds the shareable Google Colab notebook for the single-agent code review system.
Run: python3 build_notebook.py  ->  produces code_review_agent_colab.ipynb
"""

import json


def md(*lines):
    return {"cell_type": "markdown", "metadata": {}, "source": _src(lines)}


def code(*lines):
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": _src(lines),
    }


def _src(lines):
    # nbformat stores source as a list of strings, each ending in \n except the last
    out = []
    for i, line in enumerate(lines):
        if i < len(lines) - 1:
            out.append(line + "\n")
        else:
            out.append(line)
    return out


cells = [
    md(
        "# 🤖 Single-Agent Code Review System",
        "",
        "An AI agent that reviews a Python file, finds issues (security, bugs, style, performance), "
        "and generates a fixed version of the code.",
        "",
        "**Powered by:** OpenAI GPT-4o",
        "",
        "---",
        "",
        "## ⚙️ Setup (do this first)",
        "",
        "This notebook needs your **OpenAI API key**, stored securely in Colab Secrets:",
        "",
        "1. Click the **🔑 key icon** in the left sidebar of Colab.",
        "2. Click **+ Add new secret**.",
        "3. Name it exactly: `OPENAI_API_KEY`",
        "4. Paste your OpenAI API key as the value.",
        "5. Toggle **Notebook access** ON for this secret.",
        "",
        "Then run the cells below in order (or use **Runtime > Run all**).",
        "",
        "> Don't have a key? Get one at https://platform.openai.com/api-keys",
    ),
    md("## 1. Install dependencies"),
    code(
        "!pip install -q openai>=1.0.0",
    ),
    md(
        "## 2. Load your OpenAI API key from Colab Secrets",
        "",
        "This reads the `OPENAI_API_KEY` secret you set up above. "
        "Your key is never written into the notebook.",
    ),
    code(
        "from google.colab import userdata",
        "from openai import OpenAI",
        "",
        "try:",
        "    api_key = userdata.get('OPENAI_API_KEY')",
        "except Exception:",
        "    api_key = None",
        "",
        "if not api_key:",
        "    raise ValueError(",
        "        'OPENAI_API_KEY not found in Colab Secrets.\\n'",
        "        'Click the key icon (left sidebar) -> Add new secret named OPENAI_API_KEY, '",
        "        'paste your key, and enable Notebook access. Then re-run this cell.'",
        "    )",
        "",
        "client = OpenAI(api_key=api_key)",
        "print('OpenAI client ready.')",
    ),
    md(
        "## 3. Define the Code Review Agent",
        "",
        "The agent sends the code to GPT-4o with a structured prompt and parses out the fixed code.",
    ),
    code(
        "from pathlib import Path",
        "",
        "REVIEW_PROMPT = '''You are an expert Python code reviewer. Analyze the following code and provide:",
        "",
        "1. **ISSUES FOUND** - List each issue with:",
        "   - Line number (approximate)",
        "   - Category: [Security | Bug | Style | Performance]",
        "   - Severity: [Critical | High | Medium | Low]",
        "   - Description of the problem",
        "   - Why it matters",
        "",
        "2. **FIXED CODE** - Provide the complete corrected version of the code with all issues resolved.",
        "   Place the fixed code between triple-backtick python markers.",
        "",
        "Be thorough but practical. Fix real problems, not nitpicks.",
        "",
        "CODE TO REVIEW:",
        "```python",
        "{code}",
        "```",
        "'''",
        "",
        "",
        "def review_code(source_code: str) -> str:",
        "    prompt = REVIEW_PROMPT.format(code=source_code)",
        "    response = client.chat.completions.create(",
        "        model='gpt-4o',",
        "        messages=[",
        "            {'role': 'system', 'content': 'You are a senior Python developer performing a code review.'},",
        "            {'role': 'user', 'content': prompt},",
        "        ],",
        "        temperature=0.2,",
        "    )",
        "    return response.choices[0].message.content",
        "",
        "",
        "def extract_fixed_code(review_response: str):",
        "    marker = '```python'",
        "    start = review_response.rfind(marker)",
        "    if start == -1:",
        "        return None",
        "    start += len(marker)",
        "    end = review_response.find('```', start)",
        "    if end == -1:",
        "        return None",
        "    return review_response[start:end].strip()",
        "",
        "",
        "def save_fixed_code(original_name: str, fixed_code: str) -> str:",
        "    path = Path(original_name)",
        "    fixed_path = f'{path.stem}_fixed{path.suffix}'",
        "    Path(fixed_path).write_text(fixed_code)",
        "    return fixed_path",
        "",
        "print('Agent functions defined.')",
    ),
    md(
        "## 4. Provide some code to review",
        "",
        "**Option A** (default): use the built-in sample of deliberately bad code below.",
        "",
        "**Option B**: skip this cell and run the **Upload your own file** cell instead (Section 4b).",
    ),
    code(
        "SAMPLE_BAD_CODE = '''import os",
        "import sys",
        "",
        "def get_user_data(id):",
        "    import sqlite3",
        "    conn = sqlite3.connect('users.db')",
        "    query = \"SELECT * FROM users WHERE id = \" + str(id)  # SQL injection",
        "    cursor = conn.execute(query)",
        "    return cursor.fetchone()",
        "",
        "def calculate_average(numbers):",
        "    total = 0",
        "    for i in range(len(numbers)):",
        "        total = total + numbers[i]",
        "    return total / len(numbers)  # ZeroDivisionError if empty",
        "",
        "def read_file(filename):",
        "    f = open(filename, 'r')  # never closed",
        "    return f.read()",
        "",
        "class userAccount:  # should be PascalCase",
        "    def __init__(self, name, password):",
        "        self.name = name",
        "        self.password = password  # plain text password",
        "",
        "    def check_password(self, input_password):",
        "        return self.password == input_password",
        "",
        "def process_items(items):",
        "    result = []",
        "    for item in items:",
        "        try:",
        "            result.append(item.strip().lower())",
        "        except:  # bare except",
        "            pass",
        "    return result",
        "",
        "def find_duplicates(lst):",
        "    duplicates = []",
        "    for i in range(len(lst)):",
        "        for j in range(len(lst)):  # O(n^2)",
        "            if i != j and lst[i] == lst[j]:",
        "                if lst[i] not in duplicates:",
        "                    duplicates.append(lst[i])",
        "    return duplicates",
        "",
        "password_list = [\"admin123\", \"password\", \"qwerty\"]  # hardcoded creds",
        "'''",
        "",
        "source_code = SAMPLE_BAD_CODE",
        "file_name = 'sample_bad_code.py'",
        "print(f'Loaded sample code ({len(source_code.splitlines())} lines).')",
    ),
    md(
        "### 4b. (Optional) Upload your own Python file",
        "",
        "Run this cell **only** if you want to review your own file instead of the sample. "
        "It overrides the sample code above.",
    ),
    code(
        "from google.colab import files",
        "",
        "uploaded = files.upload()  # opens a file picker",
        "if uploaded:",
        "    file_name = list(uploaded.keys())[0]",
        "    source_code = uploaded[file_name].decode('utf-8')",
        "    print(f'Loaded {file_name} ({len(source_code.splitlines())} lines).')",
    ),
    md("## 5. Run the review"),
    code(
        "print('Reviewing', file_name, '...\\n')",
        "review_response = review_code(source_code)",
        "print(review_response)",
    ),
    md(
        "## 6. Save & download the fixed code",
        "",
        "Extracts the corrected code from the review and saves it as `<name>_fixed.py`, "
        "then downloads it to your computer.",
    ),
    code(
        "fixed_code = extract_fixed_code(review_response)",
        "",
        "if fixed_code:",
        "    output_path = save_fixed_code(file_name, fixed_code)",
        "    print(f'Fixed code saved to: {output_path}\\n')",
        "    print('--- Preview ---')",
        "    print(fixed_code)",
        "    files.download(output_path)",
        "else:",
        "    print('Could not extract fixed code from the response.')",
    ),
    md(
        "---",
        "",
        "✅ **Done!** You reviewed a file and downloaded the fixed version.",
        "",
        "This is the single-agent foundation. The full project extends this into a "
        "**multi-agent pipeline** (security, bug, style, patch, and test agents orchestrated with LangGraph).",
    ),
]

notebook = {
    "nbformat": 4,
    "nbformat_minor": 0,
    "metadata": {
        "colab": {"provenance": [], "toc_visible": True},
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"},
    },
    "cells": cells,
}

with open("code_review_agent_colab.ipynb", "w") as f:
    json.dump(notebook, f, indent=1)

print(f"Built code_review_agent_colab.ipynb with {len(cells)} cells.")
