# Rollback

- Revert the final remediation commit with ordinary `git revert <task-commit>` from this worktree.
- No reset, clean, worktree removal, database rollback, model restore or RAG alias restore is needed.
- Runtime attachment objects are Git-ignored and already support idempotent delete/TTL cleanup.
