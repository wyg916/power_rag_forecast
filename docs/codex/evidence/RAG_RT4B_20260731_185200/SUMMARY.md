# RAG-RT4B Embedding Profile 漂移门禁证据

## 范围与检查点

- 基线：`ed5f16f2fa30e5b0eff5002dbdb1e4f515d99932`
- 检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_184937_RAG_RT4B_PRE`
- 范围仅限发布运行时准入、fake 漂移测试和本证据。

## 修复结果

- `ReleasePublisher` 构造时必须显式注入部署期 expected `ReleaseEmbeddingProfile`，没有默认值。
- expected profile 自身必须满足 BGE Large 1024、已知 provider/model、非空版本和 Sparse Profile 基础契约。
- preflight 要求 Candidate profile 与 expected 全等，不再接受任意非空版本。
- Collection profile 必须与 expected 全等。
- Qdrant payload profile 必须唯一且与 expected 全等。
- Dense version 或 Sparse Profile 任一漂移均 fail-closed，且 Candidate 保持未验证状态。
- publish 重试会重新执行相同 preflight，不能绕过部署期 expected profile。

## 验证

- RT4/RT4A/RT4B 发布状态机与漂移测试：`19 passed in 3.43s`。
- Release DTO、Schema 与运行时联合回归：`52 passed in 0.75s`。
- 覆盖 Candidate、Collection、Payload 的 Dense version 与 Sparse Profile 漂移。

## 外部影响与回滚

- 仅使用内存 fake；未连接 PostgreSQL、Qdrant、网络或缓存服务。
- 未修改真实配置、Compose、alias、current release 或 Collection。
- 回滚使用 `git revert <RAG-RT4B-commit>`；没有外部状态需要恢复。
