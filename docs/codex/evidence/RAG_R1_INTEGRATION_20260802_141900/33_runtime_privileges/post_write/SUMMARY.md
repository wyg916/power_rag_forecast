# RAG-R1 runtime privilege post-write checkpoint

- 目标：`localhost:5432/postgres`，用户 `postgres`。
- 事务：`READ ONLY`；数据库写入：0。
- Alembic：`0018_rag_enterprise_r1`。
- public 对象：73 tables / 8 views / 47 sequences / 37 functions。
- public structure SHA-256：`15d4fd97a193c57b6b3bc0b6ad484902be2463cce3048fd3cb8fecd7b7e208be`。
- RAG 行数：`{"audit_logs": 41, "kb_access_policies": 0, "kb_assets": 0, "kb_chunks": 8384, "kb_citations": 0, "kb_document_versions": 45, "kb_documents": 85, "kb_qa_evaluations": 0, "kb_qa_tests": 0, "kb_rag_audit_events": 2, "kb_release_items": 83, "kb_releases": 1, "kb_retrieval_runs": 0, "kb_search_results": 0}`。
- 恢复：代码使用逐提交 `git revert`；正式 migration 若需回滚，先恢复本快照对应的业务备份，再在无新增 RAG 事实时执行 `alembic downgrade 0017_day6_operational`。
- 本快照不含密码、连接串、模型路径或业务正文。
