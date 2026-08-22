# Startup control summary

- `status`, `logs` and `doctor` all returned exit 0 from the exact C worktree.
- Status displayed branch, SHA, tag, PID, port, working directory, health, log path and `visible_consoles=1`.
- Doctor returned `ok=true` for exact Git root, approved E-drive Python, runtime configs, frontend dependencies and a single Alembic head.
- 8000 PID 24144 and 5173 PID 12856 were both reported as `source_owned=false`; no stop, kill, overwrite or port takeover was attempted.
- Existing consolidated logs remained under `logs/runtime/20260822_195459/`; log output was redacted by the controller.
