# Test Summary

- Bootstrap head gate: PASS; documentation-only delta.
- A merge: PASS; merge SHA `814bf633d09853b7e29d13c8734399fc9e4cfb05`.
- Targeted pytest: 128 passed, 28 skipped, 1 deselected after applying the documented ignored-asset root; initial 24 environment setup errors retained in the report.
- Formal Celery lifecycle: PASS; task `task_932b3a30cc4b`.
- Forecast: PASS; run `run_20260822T142807620068Z_ed7f7a4549`, 24 rows, 0 partial.
- Idempotency, four failure rollback cases, API/task readback, worker restart persistence: PASS.
- Prediction to report to strategy/review chain and stale publish guard: PASS.
- Python AST parse (11 files) and `git diff --check`: PASS.
