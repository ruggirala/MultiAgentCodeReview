# Case studies

Five concrete bugs the Multi-Agent Code Review pipeline caught on real PRs to
[`rahulilla/airflow`](https://github.com/rahulilla/airflow) during the 30-PR
load test. Each study quotes the agent's actual review verbatim — these are
not paraphrased examples.

| # | Category | CWE | Severity | Live PR |
|---|---|---|---|---|
| [01](01-sql-injection.md) | Security | [CWE-89](https://cwe.mitre.org/data/definitions/89.html) | High | [#5](https://github.com/rahulilla/airflow/pull/5) |
| [02](02-hardcoded-api-key.md) | Security | [CWE-798](https://cwe.mitre.org/data/definitions/798.html) | High | [#9](https://github.com/rahulilla/airflow/pull/9) |
| [03](03-mutable-default-arg.md) | Bug | [CWE-582](https://cwe.mitre.org/data/definitions/582.html) | Medium | [#15](https://github.com/rahulilla/airflow/pull/15) |
| [04](04-string-concat-loop.md) | Performance | — | Low | [#27](https://github.com/rahulilla/airflow/pull/27) |
| [05](05-cyclomatic-complexity.md) | Style | — | Medium | [#30](https://github.com/rahulilla/airflow/pull/30) |

Across all 30 load-test PRs the pipeline produced **836 findings** (40 Security ·
140 Bug · 65 Performance · 382 Style/maintainability) at a median latency of
**56.5 s/PR**. These five are representative, not cherry-picked outliers.
