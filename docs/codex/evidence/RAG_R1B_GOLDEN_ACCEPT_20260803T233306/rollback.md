# Rollback

- Verified pre-acceptance HEAD: `320ff07d78292ff4d84151670b21641bc7845a1e`
- Accepted cherry-pick commit: `428d62b0249d43e806011f9bfed47ed6256694cb`
- Database impact: none
- Runtime/release/alias/snapshot impact: none
- Rollback: ordinary `git revert` of the registration commit followed by `git revert 428d62b0249d43e806011f9bfed47ed6256694cb`.
- Checkpoint: `E:\智能运营分析项目\backups\phase3\20260803T231859_RAG_R1B_GOLDEN_ACCEPT_PRE`.
