# 并行集成登记

本文件由主线唯一集成负责人维护。Day 4 未合并、未 cherry-pick、未复制任何 RAG-R1 工作区内容。

| 分支 | 任务包 | 文件范围 | 依赖 | 共享契约 | 提交哈希 | 测试 | 已集成 | 冲突 | 回滚方式 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `beta10d/day4-data-access-security-v2` | Day 4 数据访问安全 | 注册表、数据 API、AI 受控查询、数据库身份/ACL、Compose、数据中心、测试和证据 | Day 3 PASS `45092b8…` | API 权限矩阵；`dataset_id` 契约；运行/安全/迁移身份 | `3eaaf572`、`67655c83`、`027e1c3b`、`5d4b73a9`、`7359dd53`、`4254dc65`、`11a239b8`；收口见本文件所在提交 | 268 项隔离回归、91 项专项、真实角色/ACL、Node 7 项、TypeScript/Vite、双 Compose、浏览器 | 是（仅本 Day 4 主线原子提交） | RAG-R1 外部工作树持续推进；未 merge、未 cherry-pick、未复制，未覆盖主线契约 | 逆序逐笔 `git revert`；ACL 按检查点策略精确撤销；停止服务后恢复本地配置 |
| `codex/rag-enterprise-ingestion` | RAG ingestion 支线 | 未收到正式交付清单，本轮不检查、不集成 | 未声明 | 不得修改正式迁移、公共配置、权限矩阵、Router、数据库 ACL | 无 | 无可核验交付 | 否 | 潜在共享配置/Router/数据库冲突仅登记 | 不 cherry-pick；无主线变更 |
| `codex/rag-enterprise-runtime` | RAG runtime 支线 | 未收到正式交付清单，本轮不检查、不集成 | 未声明 | 不得覆盖 Day 4 数据白名单、运行身份、权限矩阵和正式 Router | 无 | 无可核验交付 | 否 | 潜在 AI/数据访问契约冲突仅登记 | 不 cherry-pick；无主线变更 |

## 集成门禁

支线交付必须同时满足：不超过 20 文件、不超过 1000 行有效代码、工作树干净、独立测试和证据完整、无当前 PostgreSQL 写入、无正式 Alembic revision、无真实密钥、未超出文件所有权。共享文件冲突由主线重新实现，不直接 merge 整支线。
