# Rollback

Revert the final task commit using `git revert <final-task-commit>`. Runtime artifacts are written under ignored `logs/runtime/<timestamp>/`; no unknown process is terminated, and no database state is changed.
