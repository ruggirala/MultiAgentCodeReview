"""
Inline corpus of OWASP Top 10 (2021) categories + curated CWE entries.

The CWE list is a hand-picked subset — the classes the multi-agent reviewer
actually encounters in Python code (injection, credential handling, path
traversal, unsafe deserialization, etc.) — not an exhaustive dump of the full
1500-entry MITRE catalogue. Keeping it inline means the notebook is fully
reproducible (no slow first-run downloads, no upstream-URL dependency).

Each entry has:
    id          — "OWASP-A01" or "CWE-89"
    title       — short human-readable name
    text        — what the entry IS (what gets embedded for retrieval)
    examples    — a few code-pattern hints that frequently match (also embedded)

Source attribution: OWASP Top 10 2021 (owasp.org/Top10/) and MITRE CWE
(cwe.mitre.org). All entries are paraphrased summaries, not verbatim text.
"""

OWASP_TOP_10 = [
    {
        "id": "OWASP-A01",
        "title": "Broken Access Control",
        "text": (
            "Access control enforces that users cannot act outside of their "
            "intended permissions. Failures lead to unauthorized information "
            "disclosure, modification, or destruction of data. Common issues "
            "include violating least privilege, bypassing access control checks "
            "by modifying the URL, missing authorization on sensitive actions, "
            "elevation of privilege, and CORS misconfiguration."
        ),
        "examples": "missing @login_required; user-supplied IDs used without "
        "authorization checks; admin endpoints lacking role checks",
    },
    {
        "id": "OWASP-A02",
        "title": "Cryptographic Failures",
        "text": (
            "Failures related to cryptography (or lack of it) often lead to "
            "exposure of sensitive data. This includes plaintext storage of "
            "passwords, hardcoded secrets, weak hashing (MD5, SHA1), missing "
            "TLS, and improper random number generation."
        ),
        "examples": "passwords stored in plaintext; password == input comparison; "
        "hardcoded API keys; using random.random() for tokens",
    },
    {
        "id": "OWASP-A03",
        "title": "Injection",
        "text": (
            "User-supplied data is not validated, filtered, or sanitized by the "
            "application. SQL, NoSQL, OS command, and LDAP injection occur when "
            "untrusted data is concatenated into a query or command without "
            "parameterization. Object-Relational Mapping (ORM) helpers used "
            "incorrectly can also be injection-prone."
        ),
        "examples": 'cursor.execute("SELECT ... WHERE id=" + user_id); '
        "subprocess.run(cmd, shell=True) with user input; "
        "eval(user_input); os.system(user_input)",
    },
    {
        "id": "OWASP-A04",
        "title": "Insecure Design",
        "text": (
            "Risks related to design and architectural flaws — missing or "
            "ineffective control design. Threat modeling, secure design "
            "patterns, and reference architectures are missing. Distinct from "
            "implementation bugs: even a perfect implementation of a flawed "
            "design is still vulnerable."
        ),
        "examples": "no rate limiting on auth endpoints; password reset by "
        "security questions; trust boundaries unclear",
    },
    {
        "id": "OWASP-A05",
        "title": "Security Misconfiguration",
        "text": (
            "Missing appropriate security hardening across any part of the "
            "application stack: default accounts, unnecessary features enabled, "
            "directory listing on, error messages revealing stack traces, "
            "outdated software, debug mode in production."
        ),
        "examples": "Flask debug=True in production; verbose error pages; "
        "unused features enabled; default admin credentials",
    },
    {
        "id": "OWASP-A06",
        "title": "Vulnerable and Outdated Components",
        "text": (
            "Components such as libraries, frameworks, and other software "
            "modules run with the same privileges as the application. If a "
            "vulnerable component is exploited, attacks can lead to data loss "
            "or server takeover. Applications must inventory dependencies and "
            "patch known CVEs."
        ),
        "examples": "pinning to old library versions with known CVEs; using "
        "unmaintained dependencies; no vulnerability scanning in CI",
    },
    {
        "id": "OWASP-A07",
        "title": "Identification and Authentication Failures",
        "text": (
            "Confirmation of the user's identity, authentication, and session "
            "management is critical. Permits credential stuffing, brute force, "
            "weak passwords, missing MFA, exposed session IDs in URLs, missing "
            "or weak session expiration."
        ),
        "examples": "no rate limiting on /login; no account lockout; passwords "
        "compared with == instead of constant-time; session tokens in URL",
    },
    {
        "id": "OWASP-A08",
        "title": "Software and Data Integrity Failures",
        "text": (
            "Code and infrastructure that does not protect against integrity "
            "violations: unsigned updates, deserialization of untrusted data, "
            "CI/CD pipelines without integrity checks. Insecure deserialization "
            "(e.g. Python pickle on untrusted data) lets an attacker execute "
            "arbitrary code."
        ),
        "examples": "pickle.loads(user_input); yaml.load() without SafeLoader; "
        "auto-update without signature verification",
    },
    {
        "id": "OWASP-A09",
        "title": "Security Logging and Monitoring Failures",
        "text": (
            "Insufficient logging, detection, monitoring, and active response. "
            "Auditable events are not logged; logs are not monitored for "
            "suspicious activity; logs are stored only locally; alerting "
            "thresholds are not effective."
        ),
        "examples": "swallowed exceptions with bare `except: pass`; logs "
        "without timestamps; no alerting on auth failures",
    },
    {
        "id": "OWASP-A10",
        "title": "Server-Side Request Forgery (SSRF)",
        "text": (
            "SSRF occurs when a web app fetches a remote resource without "
            "validating the user-supplied URL. Allows an attacker to coerce the "
            "server into making requests to unintended destinations, often "
            "bypassing network ACLs to reach internal services or cloud "
            "metadata endpoints."
        ),
        "examples": "requests.get(user_supplied_url); urllib.urlopen on user "
        "input; image fetchers that follow redirects",
    },
]


# Curated CWEs — each one chosen because our agents have flagged something in
# its class on real PRs. Ordered by frequency-of-appearance, not CWE number.
CWE_ENTRIES = [
    {
        "id": "CWE-89",
        "title": "SQL Injection",
        "text": (
            "The software constructs all or part of an SQL command using "
            "externally-influenced input from an upstream component, but it "
            "does not neutralize or incorrectly neutralizes special elements "
            "that could modify the intended SQL command. Use parameterized "
            "queries, prepared statements, or an ORM."
        ),
        "examples": "f\"SELECT * FROM users WHERE id = {user_id}\"; "
        '"... WHERE name = " + name; cursor.execute with %s formatting',
    },
    {
        "id": "CWE-78",
        "title": "OS Command Injection",
        "text": (
            "The software constructs all or part of an OS command using "
            "externally-influenced input but does not neutralize special "
            "elements that could modify the intended OS command. Use "
            "subprocess with shell=False and a list of args, never shell=True "
            "with concatenated input."
        ),
        "examples": "os.system('ls ' + path); subprocess.run(cmd, shell=True); "
        "os.popen with user input",
    },
    {
        "id": "CWE-94",
        "title": "Code Injection",
        "text": (
            "The software constructs all or part of a code segment using "
            "externally-influenced input. Use of eval(), exec(), or compile() "
            "on untrusted input lets the attacker run arbitrary code in the "
            "process. Avoid these primitives or sandbox rigorously."
        ),
        "examples": "eval(user_input); exec(formula); compile() on dynamic strings",
    },
    {
        "id": "CWE-22",
        "title": "Path Traversal",
        "text": (
            "The software uses external input to construct a pathname intended "
            "to identify a file or directory beneath a restricted parent, but "
            "does not properly neutralize special elements like '..' that can "
            "escape the restriction. Always resolve to an absolute path and "
            "verify it stays under the intended root."
        ),
        "examples": "open(base + user_filename); os.path.join with unchecked "
        "user input; serving files by name without sandboxing",
    },
    {
        "id": "CWE-798",
        "title": "Use of Hard-coded Credentials",
        "text": (
            "The software contains hard-coded credentials (passwords, API "
            "keys, cryptographic keys) that it uses for inbound authentication, "
            "outbound communication, or encryption. Anyone with access to the "
            "source has the credential. Use environment variables, secret "
            "managers, or vaulted configuration."
        ),
        "examples": 'API_KEY = "sk_live_..."; password = "admin123"; '
        "credentials inlined in scripts",
    },
    {
        "id": "CWE-256",
        "title": "Plaintext Storage of a Password",
        "text": (
            "Storing a password in plaintext may result in system "
            "compromise. Hash passwords with a slow, salted algorithm "
            "(bcrypt, argon2, scrypt). Never store the plaintext or compare "
            "submitted passwords with == against stored values."
        ),
        "examples": "self.password = password; user.pwd = request.form['pwd']; "
        "password column of type VARCHAR with the literal value",
    },
    {
        "id": "CWE-319",
        "title": "Cleartext Transmission of Sensitive Information",
        "text": (
            "The software transmits sensitive data in cleartext over a "
            "communication channel that can be sniffed by unauthorized actors. "
            "Common in HTTP-only APIs, missing TLS on internal services, and "
            "logging tokens in plaintext."
        ),
        "examples": "http:// URLs for auth flows; tokens printed to logs; "
        "passwords compared in plaintext over the wire",
    },
    {
        "id": "CWE-327",
        "title": "Use of a Broken or Risky Cryptographic Algorithm",
        "text": (
            "The use of a broken or risky cryptographic algorithm is an "
            "unnecessary risk. MD5 and SHA1 are unsuitable for password "
            "hashing or signature verification. DES, RC4, and ECB-mode block "
            "ciphers are deprecated."
        ),
        "examples": "hashlib.md5(password); DES; ECB mode; rolling your own crypto",
    },
    {
        "id": "CWE-330",
        "title": "Use of Insufficiently Random Values",
        "text": (
            "The software uses insufficiently random numbers or values in a "
            "security context. The `random` module is NOT cryptographically "
            "secure. For tokens, session IDs, and salts use `secrets` (Python) "
            "or `os.urandom`."
        ),
        "examples": "random.random() for session tokens; random.randint for "
        "passwords; using time as a random seed",
    },
    {
        "id": "CWE-502",
        "title": "Deserialization of Untrusted Data",
        "text": (
            "The application deserializes untrusted data without sufficient "
            "verification, allowing an attacker to control the deserialization "
            "process. Python `pickle.loads()` on untrusted input is "
            "remote-code-execution. yaml.load() without SafeLoader is similar."
        ),
        "examples": "pickle.loads(request.body); yaml.load(user_yaml); "
        "marshal.loads(); dill.loads()",
    },
    {
        "id": "CWE-611",
        "title": "Improper Restriction of XML External Entity Reference (XXE)",
        "text": (
            "When the software parses XML and does not prevent XML entities "
            "from referencing external resources, attackers can read local "
            "files, perform SSRF, or deny service. Disable DTDs and external "
            "entities in your XML parser."
        ),
        "examples": "lxml.etree.parse without resolve_entities=False; "
        "xml.etree without restricting; xml.dom.minidom",
    },
    {
        "id": "CWE-918",
        "title": "Server-Side Request Forgery (SSRF)",
        "text": (
            "The web server receives a URL or similar request from an "
            "upstream component and retrieves the contents of this URL, but "
            "does not sufficiently ensure that the request is being sent to "
            "the expected destination. Validate against an allowlist of hosts."
        ),
        "examples": "requests.get(user_url); urllib.request.urlopen(arg); "
        "image proxies without host allowlist",
    },
    {
        "id": "CWE-209",
        "title": "Generation of Error Message Containing Sensitive Information",
        "text": (
            "The software generates an error message that includes sensitive "
            "information about its environment, users, or associated data. "
            "Stack traces, SQL errors, and file paths leak intelligence to "
            "attackers. Log details server-side; show generic messages to users."
        ),
        "examples": "Flask debug=True in prod; printing stack traces in HTTP "
        "responses; SQL errors echoed to clients",
    },
    {
        "id": "CWE-117",
        "title": "Improper Output Neutralization for Logs",
        "text": (
            "The software does not neutralize or incorrectly neutralizes "
            "output that is written to logs. Attackers can forge log entries, "
            "inject control characters, or exfiltrate data via log scrapers."
        ),
        "examples": "logger.info(user_input) without sanitization; logging "
        "raw HTTP headers; log injection via newlines",
    },
    {
        "id": "CWE-200",
        "title": "Exposure of Sensitive Information to an Unauthorized Actor",
        "text": (
            "The product exposes sensitive information to an actor that is "
            "not explicitly authorized to have access to that information. "
            "Often via verbose responses, debug endpoints, or returning more "
            "fields than necessary."
        ),
        "examples": "returning password_hash in JSON; /debug endpoint in prod; "
        "stack traces in HTTP 500 responses",
    },
    {
        "id": "CWE-352",
        "title": "Cross-Site Request Forgery (CSRF)",
        "text": (
            "The web application does not, or cannot, sufficiently verify "
            "whether a well-formed, valid, consistent request was intentionally "
            "provided by the user who submitted the request. Use CSRF tokens "
            "or the SameSite cookie attribute."
        ),
        "examples": "Flask views without CSRFProtect; state-changing GET "
        "requests; missing CSRF token on forms",
    },
    {
        "id": "CWE-79",
        "title": "Cross-site Scripting (XSS)",
        "text": (
            "The software does not neutralize or incorrectly neutralizes "
            "user-controllable input before it is placed in output that is "
            "used as a web page that is served to other users. Always escape "
            "based on context (HTML, JS, attribute, URL)."
        ),
        "examples": "Markup(user_input); render_template_string with user "
        "data; |safe filter on untrusted content",
    },
    {
        "id": "CWE-285",
        "title": "Improper Authorization",
        "text": (
            "The software does not perform an authorization check when an "
            "actor attempts to access a resource or perform an action. "
            "Different from authentication: the user IS who they say they are, "
            "but should not be allowed to do this."
        ),
        "examples": "endpoints checking only login, not ownership; IDOR "
        "(user/123 returns any user's data); admin checks missing on actions",
    },
    {
        "id": "CWE-862",
        "title": "Missing Authorization",
        "text": (
            "The software does not perform an authorization check when an "
            "actor attempts to access a resource or perform an action. The "
            "endpoint either has no decorator at all or only checks "
            "authentication."
        ),
        "examples": "@app.route on admin endpoints with no @admin_required; "
        "API routes that anyone authenticated can hit",
    },
    {
        "id": "CWE-863",
        "title": "Incorrect Authorization",
        "text": (
            "The software performs an authorization check when an actor "
            "attempts to access a resource or perform an action, but it does "
            "not correctly perform the check. This results in an actor being "
            "able to access or perform actions they should not."
        ),
        "examples": "checking role string with == without case-folding; "
        "comparing usernames with `in` instead of `==`",
    },
    {
        "id": "CWE-770",
        "title": "Allocation of Resources Without Limits or Throttling",
        "text": (
            "The software allocates a reusable resource or group of resources "
            "without imposing any restrictions on the size or number that can "
            "be allocated. Allows DoS by exhaustion."
        ),
        "examples": "no rate limiting; reading entire request body into memory; "
        "unbounded list growth from user input",
    },
    {
        "id": "CWE-400",
        "title": "Uncontrolled Resource Consumption",
        "text": (
            "The software does not properly control the allocation and "
            "maintenance of a limited resource, thereby enabling an actor to "
            "influence the amount of resources consumed, eventually leading to "
            "exhaustion."
        ),
        "examples": "regex with catastrophic backtracking on user input; "
        "while True without break; unbounded recursion",
    },
    {
        "id": "CWE-20",
        "title": "Improper Input Validation",
        "text": (
            "The product receives input or data, but it does not validate or "
            "incorrectly validates that the input has the properties required "
            "to process the data safely and correctly. Often the parent of "
            "more specific weaknesses (CWE-89, CWE-78, CWE-22)."
        ),
        "examples": "request.args.get without type-checking; trusting "
        "client-provided IDs; no length limits on string inputs",
    },
    {
        "id": "CWE-732",
        "title": "Incorrect Permission Assignment for Critical Resource",
        "text": (
            "The product specifies permissions for a security-critical "
            "resource in a way that allows the resource to be read or modified "
            "by unintended actors. World-writable files, overly permissive "
            "S3 buckets, weak file modes."
        ),
        "examples": "os.chmod(0o777); files written without umask; "
        "S3 bucket policies with Principal: '*'",
    },
    {
        "id": "CWE-601",
        "title": "URL Redirection to Untrusted Site (Open Redirect)",
        "text": (
            "A web application accepts a user-controlled input that specifies "
            "a link to an external site, and uses that link in a redirect. "
            "Phishing vector — attacker tricks user into thinking they are on "
            "a trusted domain."
        ),
        "examples": "redirect(request.args.get('next')); "
        'response.redirect(url) with no host check',
    },
    {
        "id": "CWE-396",
        "title": "Declaration of Catch for Generic Exception",
        "text": (
            "Catching overly broad exceptions promotes complex error handling "
            "code that is more likely to contain security vulnerabilities. "
            "Bare `except:` and `except Exception:` swallow important "
            "signals — including KeyboardInterrupt and SystemExit."
        ),
        "examples": "except: pass; except Exception: pass; broad exception "
        "handlers around critical security checks",
    },
    {
        "id": "CWE-710",
        "title": "Improper Adherence to Coding Standards",
        "text": (
            "The product does not follow certain coding rules for development, "
            "which can lead to resultant weaknesses or increase the severity "
            "of associated vulnerabilities. Examples: mutable default args, "
            "global mutable state, mixing tabs and spaces."
        ),
        "examples": "def f(x, history=[]): ...; using global state for "
        "request-scoped data; unclear naming",
    },
    {
        "id": "CWE-775",
        "title": "Missing Release of Resource after Effective Lifetime",
        "text": (
            "The software does not release a resource after its effective "
            "lifetime has ended. File handles, database connections, network "
            "sockets — all need explicit closing or use as a context manager."
        ),
        "examples": "f = open(path); without close; "
        "conn = sqlite3.connect; never closed; sockets leaked across requests",
    },
    {
        "id": "CWE-369",
        "title": "Divide By Zero",
        "text": (
            "The product divides a value by zero. Where the divisor is "
            "user-controllable or comes from untrusted aggregation, the "
            "exception either crashes the request or leaks information via "
            "the error message."
        ),
        "examples": "total / len(items) without checking len > 0; "
        "average over an empty list",
    },
    {
        "id": "CWE-561",
        "title": "Dead Code",
        "text": (
            "The software contains dead code, which can never be executed. "
            "Indicates incomplete logic or removed functionality, frequently "
            "hides bugs, and bloats audit surface."
        ),
        "examples": "code after unconditional return; unreachable except "
        "branches; commented-out blocks",
    },
    {
        "id": "CWE-908",
        "title": "Use of Uninitialized Resource",
        "text": (
            "The software uses or accesses a resource that has not been "
            "initialized. In Python this often manifests as accessing "
            "self.attr in a method when __init__ never assigned it under "
            "all code paths."
        ),
        "examples": "self.balance referenced when only set in some methods; "
        "attribute set conditionally in __init__",
    },
    {
        "id": "CWE-1188",
        "title": "Insecure Default Initialization of Resource",
        "text": (
            "The software initializes or sets a resource with an insecure "
            "default value. Debug modes left on, default admin credentials, "
            "permissive CORS by default."
        ),
        "examples": "Flask debug=True in app.run; CORS allow_origin='*' "
        "as a default; default tokens accepted",
    },
    {
        "id": "CWE-672",
        "title": "Operation on a Resource after Expiration or Release",
        "text": (
            "The software uses, accesses, or otherwise operates on a "
            "resource after that resource has been expired, released, or "
            "revoked. Examples: using closed file handles, dangling DB "
            "cursors, expired session tokens."
        ),
        "examples": "using a session after .close(); reading from a closed "
        "stream; expired JWT accepted",
    },
    {
        "id": "CWE-307",
        "title": "Improper Restriction of Excessive Authentication Attempts",
        "text": (
            "The software does not implement sufficient measures to prevent "
            "multiple failed authentication attempts within a short time "
            "frame. Enables credential stuffing and brute-force attacks."
        ),
        "examples": "no rate-limit on /login; no account lockout; same "
        "delay regardless of correct vs incorrect attempts (timing attack)",
    },
    {
        "id": "CWE-208",
        "title": "Observable Timing Discrepancy",
        "text": (
            "Two separate operations in a product require different amounts of "
            "time to complete, in a way that is observable to an actor and "
            "reveals security-relevant information. String-comparison of "
            "secrets in non-constant time leaks the secret one byte at a time."
        ),
        "examples": 'if password == request.password; if api_key == header; '
        "any sensitive == comparison without hmac.compare_digest",
    },
    {
        "id": "CWE-1004",
        "title": "Sensitive Cookie Without 'HttpOnly' Flag",
        "text": (
            "The software uses a cookie to store sensitive information, but "
            "the cookie is not marked with the HttpOnly flag. JavaScript can "
            "read the cookie, expanding the impact of XSS to session hijacking."
        ),
        "examples": "set_cookie without httponly=True; default Flask session "
        "config without SESSION_COOKIE_HTTPONLY",
    },
    {
        "id": "CWE-614",
        "title": "Sensitive Cookie in HTTPS Session Without 'Secure' Attribute",
        "text": (
            "The Secure attribute for sensitive cookies in HTTPS sessions is "
            "not set, which could cause the user agent to send those cookies "
            "in plaintext over an HTTP session."
        ),
        "examples": "set_cookie without secure=True; "
        "SESSION_COOKIE_SECURE not configured",
    },
]


def all_documents() -> list[dict]:
    """Return one flat list of {id, title, text} entries (OWASP + CWE)."""
    docs = []
    for src in (OWASP_TOP_10, CWE_ENTRIES):
        for entry in src:
            text = entry["text"]
            ex = entry.get("examples")
            if ex:
                text = f"{text}\n\nTypical patterns: {ex}"
            docs.append({"id": entry["id"], "title": entry["title"], "text": text})
    return docs
