"""
30 deliberately-bad code templates for load-testing the multi-agent pipeline
against the rahulilla/airflow fork.

Each template appends a small, self-contained buggy function to a real airflow
utility file on its own branch. The bug is intentional and clearly hits at
least one of {Security, Bug, Performance, Style/maintainability} so the
agents have something concrete to find.

Templates are deterministic — same input produces same PR every time — so a
load test produces consistent dashboard data.
"""

from __future__ import annotations

import ast
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["Security", "Bug", "Performance", "Style"]


class BuggyTemplate(BaseModel):
    """One PR's worth of intentionally bad code."""

    name: str = Field(description="kebab-case slug, used in branch + PR title")
    target_file: str = Field(description="airflow file path the bug is appended to")
    function_name: str = Field(description="unique function identifier")
    source: str = Field(description="lines to append to target_file")
    expected_findings: list[Category] = Field(description="categories agents should hit")
    rationale: str = Field(description="one-line PR-body explanation")


# Six small airflow utility files we rotate through. None of these are imported
# at airflow startup along the test path — the load test does NOT run airflow,
# only reviews the diff — so the buggy appends won't actually run.
F_STRINGS = "airflow-core/src/airflow/utils/strings.py"
F_FILE = "airflow-core/src/airflow/utils/file.py"
F_HELPERS = "airflow-core/src/airflow/utils/helpers.py"
F_JSON = "airflow-core/src/airflow/utils/json.py"
F_NET = "airflow-core/src/airflow/utils/net.py"
F_DATES = "airflow-core/src/airflow/utils/dates.py"


# --- Security (10) -----------------------------------------------------

_SQLI = '''
def lookup_user(db_conn, username: str):
    cursor = db_conn.cursor()
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchall()
'''

_CMDI = '''
import subprocess

def ping_host(hostname: str) -> str:
    return subprocess.check_output("ping -c 1 " + hostname, shell=True).decode()
'''

_EVAL = '''
def compute_expression(user_input: str):
    return eval(user_input)
'''

_PICKLE = '''
import pickle

def load_payload(blob: bytes):
    return pickle.loads(blob)
'''

_HARDCODED_KEY = '''
def call_payment_api(amount: float):
    api_key = "sk_live_4EC9aV3LzTpmf_REAL_LOOKING_SECRET_KEY"
    headers = {"Authorization": "Bearer " + api_key}
    return _post("https://api.payments.example.com/charge", amount, headers)
'''

_WEAK_HASH = '''
import hashlib

def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()
'''

_INSECURE_RNG = '''
import random
import string

def generate_session_token(length: int = 32) -> str:
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(length))
'''

_NO_TLS_VERIFY = '''
import requests

def fetch_internal(url: str) -> str:
    return requests.get(url, verify=False).text
'''

_PATH_TRAVERSAL = '''
def read_user_file(filename: str) -> str:
    with open("/var/data/user_uploads/" + filename) as f:
        return f.read()
'''

_XXE = '''
import xml.etree.ElementTree as ET

def parse_xml_doc(xml_text: str):
    return ET.fromstring(xml_text)
'''

# --- Bug (10) ---------------------------------------------------------

_MUTABLE_DEFAULT = '''
def append_log_entry(msg: str, log: list = []) -> list:
    log.append(msg)
    return log
'''

_BARE_EXCEPT = '''
def safe_divide(a, b):
    try:
        return a / b
    except:
        return None
'''

_OFF_BY_ONE = '''
def first_n_items(items: list, n: int) -> list:
    out = []
    for i in range(0, n + 1):
        out.append(items[i])
    return out
'''

_DIV_BY_ZERO = '''
def average(values: list) -> float:
    return sum(values) / len(values)
'''

_MISSING_RETURN = '''
def find_max_index(values: list) -> int:
    largest = values[0]
    largest_idx = 0
    for i, v in enumerate(values):
        if v > largest:
            largest = v
            largest_idx = i
'''

_INT_OVERFLOW_ASSUMPTION = '''
def cents_to_int32(cents: int) -> int:
    return cents & 0xFFFFFFFF
'''

_MUTATE_WHILE_ITER = '''
def remove_negatives(numbers: list) -> list:
    for n in numbers:
        if n < 0:
            numbers.remove(n)
    return numbers
'''

_RACE_CONDITION = '''
_global_counter = 0

def increment_counter() -> int:
    global _global_counter
    current = _global_counter
    _global_counter = current + 1
    return _global_counter
'''

_SHADOWED_BUILTIN = '''
def filter_positive(values):
    list = []
    for v in values:
        if v > 0:
            list.append(v)
    return list
'''

_UNAWAITED_COROUTINE = '''
import asyncio

async def fetch_data(url: str):
    await asyncio.sleep(0.1)
    return {"url": url}

def fetch_all(urls: list):
    results = []
    for u in urls:
        results.append(fetch_data(u))
    return results
'''

# --- Performance (5) --------------------------------------------------

_QUADRATIC_DUPS = '''
def find_duplicates(items: list) -> list:
    dups = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j] and items[i] not in dups:
                dups.append(items[i])
    return dups
'''

_LIST_COMP_AS_GENERATOR = '''
def total_squared(values: list) -> int:
    return sum([v * v for v in values])
'''

_STRING_CONCAT_LOOP = '''
def join_lines(lines: list) -> str:
    result = ""
    for line in lines:
        result = result + line + "\\n"
    return result
'''

_NAIVE_RECURSION = '''
def fib(n: int) -> int:
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)
'''

_BLOCKING_IN_ASYNC = '''
import time
import asyncio

async def process_batch(batch_id: int):
    time.sleep(2)
    return {"batch_id": batch_id, "ok": True}
'''

# --- Style/maintainability (5) ----------------------------------------

_HIGH_COMPLEXITY = '''
def classify_priority(score: int, urgent: bool, paid: bool, region: str, tier: int) -> str:
    if urgent:
        if paid:
            if score > 90:
                return "critical-paid-urgent"
            elif score > 70:
                if region == "US" or region == "EU":
                    if tier > 2:
                        return "high-paid-urgent-tier"
                    else:
                        return "high-paid-urgent"
                else:
                    return "high-paid-urgent-rest"
            else:
                return "medium-paid-urgent"
        else:
            if score > 80:
                return "high-free-urgent"
            elif score > 50:
                return "medium-free-urgent"
            else:
                return "low-free-urgent"
    else:
        if paid:
            if score > 70:
                return "high-paid"
            elif score > 40:
                return "medium-paid"
            else:
                return "low-paid"
        else:
            if score > 60:
                return "medium-free"
            else:
                return "low-free"
'''

_DUPLICATED_BLOCK = '''
def normalize_user(user: dict) -> dict:
    user["email"] = user.get("email", "").strip().lower()
    user["name"] = user.get("name", "").strip()
    if not user.get("created_at"):
        user["created_at"] = "1970-01-01"
    if user.get("status") not in ("active", "inactive", "pending"):
        user["status"] = "pending"
    return user

def normalize_admin(admin: dict) -> dict:
    admin["email"] = admin.get("email", "").strip().lower()
    admin["name"] = admin.get("name", "").strip()
    if not admin.get("created_at"):
        admin["created_at"] = "1970-01-01"
    if admin.get("status") not in ("active", "inactive", "pending"):
        admin["status"] = "pending"
    return admin
'''

_UNDOCUMENTED_API = '''
def aggregate_metrics(records, mode, threshold, window, decay, smooth):
    out = []
    for r in records:
        v = r.get(mode, 0)
        if v >= threshold:
            out.append(v * decay)
    return out
'''

_MAGIC_NUMBERS = '''
def schedule_retry(attempt: int) -> float:
    if attempt > 7:
        return 86400
    return min(2 ** attempt * 0.5, 3600) + (attempt * 1.7)
'''

_DEEP_NESTING = '''
def find_first_match(rows, target):
    for row in rows:
        if row is not None:
            if isinstance(row, dict):
                if "items" in row:
                    for item in row["items"]:
                        if item is not None:
                            if isinstance(item, dict):
                                if item.get("name") == target:
                                    return item
    return None
'''


TEMPLATES: list[BuggyTemplate] = [
    # --- Security ---
    BuggyTemplate(
        name="sqli-string-concat",
        target_file=F_HELPERS,
        function_name="lookup_user",
        source=_SQLI,
        expected_findings=["Security"],
        rationale="String-concatenated SQL query (CWE-89) — classic SQL injection.",
    ),
    BuggyTemplate(
        name="cmdi-shell-true",
        target_file=F_NET,
        function_name="ping_host",
        source=_CMDI,
        expected_findings=["Security"],
        rationale="subprocess with shell=True and unvalidated user input (CWE-78).",
    ),
    BuggyTemplate(
        name="eval-on-input",
        target_file=F_HELPERS,
        function_name="compute_expression",
        source=_EVAL,
        expected_findings=["Security"],
        rationale="eval() on user-controlled string (CWE-95).",
    ),
    BuggyTemplate(
        name="pickle-untrusted",
        target_file=F_JSON,
        function_name="load_payload",
        source=_PICKLE,
        expected_findings=["Security"],
        rationale="pickle.loads on untrusted bytes — RCE risk (CWE-502).",
    ),
    BuggyTemplate(
        name="hardcoded-api-key",
        target_file=F_HELPERS,
        function_name="call_payment_api",
        source=_HARDCODED_KEY,
        expected_findings=["Security"],
        rationale="Real-looking API key checked into source (CWE-798).",
    ),
    BuggyTemplate(
        name="weak-hash-md5",
        target_file=F_STRINGS,
        function_name="hash_password",
        source=_WEAK_HASH,
        expected_findings=["Security"],
        rationale="MD5 used to hash passwords (CWE-327, CWE-916).",
    ),
    BuggyTemplate(
        name="insecure-rng-token",
        target_file=F_STRINGS,
        function_name="generate_session_token",
        source=_INSECURE_RNG,
        expected_findings=["Security"],
        rationale="random.choice for session tokens — predictable (CWE-338).",
    ),
    BuggyTemplate(
        name="no-tls-verify",
        target_file=F_NET,
        function_name="fetch_internal",
        source=_NO_TLS_VERIFY,
        expected_findings=["Security"],
        rationale="HTTPS request with verify=False (CWE-295).",
    ),
    BuggyTemplate(
        name="path-traversal",
        target_file=F_FILE,
        function_name="read_user_file",
        source=_PATH_TRAVERSAL,
        expected_findings=["Security"],
        rationale="Path concat without normalization — directory traversal (CWE-22).",
    ),
    BuggyTemplate(
        name="xxe-elementtree",
        target_file=F_HELPERS,
        function_name="parse_xml_doc",
        source=_XXE,
        expected_findings=["Security"],
        rationale="xml.etree on untrusted input — XXE risk (CWE-611).",
    ),
    # --- Bug ---
    BuggyTemplate(
        name="mutable-default-arg",
        target_file=F_HELPERS,
        function_name="append_log_entry",
        source=_MUTABLE_DEFAULT,
        expected_findings=["Bug"],
        rationale="Mutable default argument — list shared across calls.",
    ),
    BuggyTemplate(
        name="bare-except",
        target_file=F_HELPERS,
        function_name="safe_divide",
        source=_BARE_EXCEPT,
        expected_findings=["Bug"],
        rationale="Bare except: swallows KeyboardInterrupt and SystemExit.",
    ),
    BuggyTemplate(
        name="off-by-one-loop",
        target_file=F_HELPERS,
        function_name="first_n_items",
        source=_OFF_BY_ONE,
        expected_findings=["Bug"],
        rationale="Loop reads index n+1 — IndexError when n == len(items).",
    ),
    BuggyTemplate(
        name="div-by-zero-unguarded",
        target_file=F_HELPERS,
        function_name="average",
        source=_DIV_BY_ZERO,
        expected_findings=["Bug"],
        rationale="ZeroDivisionError on empty list input.",
    ),
    BuggyTemplate(
        name="missing-return",
        target_file=F_HELPERS,
        function_name="find_max_index",
        source=_MISSING_RETURN,
        expected_findings=["Bug"],
        rationale="Function never returns — implicit None.",
    ),
    BuggyTemplate(
        name="int-overflow-assumption",
        target_file=F_HELPERS,
        function_name="cents_to_int32",
        source=_INT_OVERFLOW_ASSUMPTION,
        expected_findings=["Bug"],
        rationale="Truncates to 32-bit unsigned — silent corruption for large values.",
    ),
    BuggyTemplate(
        name="mutate-while-iter",
        target_file=F_HELPERS,
        function_name="remove_negatives",
        source=_MUTATE_WHILE_ITER,
        expected_findings=["Bug"],
        rationale="Mutating list while iterating skips elements.",
    ),
    BuggyTemplate(
        name="race-condition-counter",
        target_file=F_HELPERS,
        function_name="increment_counter",
        source=_RACE_CONDITION,
        expected_findings=["Bug"],
        rationale="Read-modify-write of global without lock — race under threads.",
    ),
    BuggyTemplate(
        name="shadowed-builtin-list",
        target_file=F_HELPERS,
        function_name="filter_positive",
        source=_SHADOWED_BUILTIN,
        expected_findings=["Bug", "Style"],
        rationale="Local variable named `list` shadows the builtin.",
    ),
    BuggyTemplate(
        name="unawaited-coroutine",
        target_file=F_HELPERS,
        function_name="fetch_all",
        source=_UNAWAITED_COROUTINE,
        expected_findings=["Bug"],
        rationale="Coroutine called but never awaited — collects coroutine objects.",
    ),
    # --- Performance ---
    BuggyTemplate(
        name="quadratic-duplicates",
        target_file=F_HELPERS,
        function_name="find_duplicates",
        source=_QUADRATIC_DUPS,
        expected_findings=["Performance"],
        rationale="O(n^2) duplicate detection where a set is O(n).",
    ),
    BuggyTemplate(
        name="list-comp-as-generator",
        target_file=F_HELPERS,
        function_name="total_squared",
        source=_LIST_COMP_AS_GENERATOR,
        expected_findings=["Performance"],
        rationale="sum() with list comprehension materializes; generator suffices.",
    ),
    BuggyTemplate(
        name="string-concat-loop",
        target_file=F_STRINGS,
        function_name="join_lines",
        source=_STRING_CONCAT_LOOP,
        expected_findings=["Performance"],
        rationale="Repeated string concatenation in a loop — O(n^2).",
    ),
    BuggyTemplate(
        name="naive-recursion-fib",
        target_file=F_HELPERS,
        function_name="fib",
        source=_NAIVE_RECURSION,
        expected_findings=["Performance"],
        rationale="Exponential-time fibonacci — needs memoization or iteration.",
    ),
    BuggyTemplate(
        name="blocking-in-async",
        target_file=F_HELPERS,
        function_name="process_batch",
        source=_BLOCKING_IN_ASYNC,
        expected_findings=["Performance"],
        rationale="time.sleep blocks the event loop inside an async function.",
    ),
    # --- Style/maintainability ---
    BuggyTemplate(
        name="high-cyclomatic-complexity",
        target_file=F_HELPERS,
        function_name="classify_priority",
        source=_HIGH_COMPLEXITY,
        expected_findings=["Style"],
        rationale="Cyclomatic complexity > 15 — table-driven or polymorphism preferred.",
    ),
    BuggyTemplate(
        name="duplicated-block",
        target_file=F_HELPERS,
        function_name="normalize_user_admin",
        source=_DUPLICATED_BLOCK,
        expected_findings=["Style"],
        rationale="20-line block duplicated across two functions.",
    ),
    BuggyTemplate(
        name="undocumented-public-api",
        target_file=F_HELPERS,
        function_name="aggregate_metrics",
        source=_UNDOCUMENTED_API,
        expected_findings=["Style"],
        rationale="Public function with 6 positional args and no docstring.",
    ),
    BuggyTemplate(
        name="magic-numbers",
        target_file=F_HELPERS,
        function_name="schedule_retry",
        source=_MAGIC_NUMBERS,
        expected_findings=["Style"],
        rationale="Multiple magic numbers (86400, 7, 3600, 1.7) without named constants.",
    ),
    BuggyTemplate(
        name="deep-nesting",
        target_file=F_HELPERS,
        function_name="find_first_match",
        source=_DEEP_NESTING,
        expected_findings=["Style"],
        rationale="7 levels of nesting — early returns / guard clauses preferred.",
    ),
]

assert len(TEMPLATES) == 30, f"Expected 30 templates, got {len(TEMPLATES)}"

# Validate every template's source is parseable Python.
for _t in TEMPLATES:
    ast.parse(_t.source)
