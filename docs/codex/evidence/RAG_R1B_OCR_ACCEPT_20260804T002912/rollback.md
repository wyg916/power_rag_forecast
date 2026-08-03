# Rollback

- Pre-receive HEAD: `5755d85bd75dedfd1bc73b058daaa3c6d51e4123`.
- Accepted commit: `0398496846905fb3c931c37aa1f89ddc6409fc00`.
- Checkpoint: `E:\智能运营分析项目\backups\phase3\20260804T002640_RAG_R1B_OCR_ACCEPT_PRE`.
- Database/Qdrant/release/alias/snapshot impact: none.
- Roll back the registration commit and accepted commit with ordinary `git revert`, in reverse order.
