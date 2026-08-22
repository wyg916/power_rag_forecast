# Test summary

| Gate | Result |
|---|---|
| Start-SHA full diagnostic | 1010 passed / 20 skipped / 29 failed / 21 errors; 50/50 classified |
| Composite C/RBAC/Provider/ChatBI/startup | 156 passed / 5 isolated-only skipped |
| Attachment API + lifecycle + closure | 37 passed |
| ChatBI packages 1–5 + closure | 52 passed / 5 isolated-only skipped |
| Catalog / Golden | 13 metrics / 21 dimensions / 2 joins; 50/50 PASS; raw SQL 0 |
| Real MiMo general / vision | PASS / PASS |
| Real DeepSeek AnalysisPlan | 6/6 PASS; schema 6/6; repair 0; fallback 0 |
| Real Kimi explicit Premium | PASS; unconfirmed request denied; unexpected usage 0 |
| status / logs / doctor | exit 0 / 0 / 0; doctor ok=true |
| Alembic / permission matrix | single head `0022_chatbi_semantic_v1`; 207/191/7/200 |
| compileall / diff / CI YAML / raw-SQL scan | PASS |

The five skips are pre-existing tests that explicitly require the restricted isolated-schema runner. No unconditional skip was added.
