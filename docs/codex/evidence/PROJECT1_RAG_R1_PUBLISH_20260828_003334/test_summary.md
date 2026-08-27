# 测试摘要

## 自动化

结果：`105 passed in 17.19s`。

覆盖：

- Qdrant HTTPS 只读 transport、BM25 稀疏向量与缓存签名。
- Qdrant store 的 ACL、发布事实、payload 契约和混合检索。
- 独立发布 Worker 鉴权、运行时、状态机、交接与回滚契约。
- 知识库业务 API、RBAC、上传边界与只读 QA。
- 知识库前端布局和技术溯源字段隐藏契约。

## 实时正向

- validate：200、9/9。
- publish：200、published/current。
- release/health：200、RAG-R1/normal。
- Search：200、available、BGE、1 citation；热态 1.469 秒。
- QA：200、passed、1 citation；0.730 秒。
- batch：200、2/2、100%；3.155 秒。
- Web → Worker：重复 validate 返回预期 409，而非 503。

## 实时负向

- 缺失 BM25 时 Search 如实返回 `bm25_profile_unavailable`，未假成功。
- 宽泛跨领域候选由 QA 按 `domain_conflict` 语义拒答，Search 本身仍 available。
- 已发布版本不允许再次 validate，状态机返回冲突且不产生非法状态变更。
