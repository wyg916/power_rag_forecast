# 并行集成登记

本文件由主线唯一集成负责人维护。Day 4、Day 5 均未合并、未 cherry-pick、未复制任何 RAG-R1 或两条 RAG 支线内容。

| 分支 | 任务包 | 文件范围 | 依赖 | 共享契约 | 提交哈希 | 测试 | 已集成 | 冲突 | 回滚方式 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `beta10d/day4-data-access-security-v2` | Day 4 数据访问安全 | 注册表、数据 API、AI 受控查询、数据库身份/ACL、Compose、数据中心、测试和证据 | Day 3 PASS `45092b8…` | API 权限矩阵；`dataset_id` 契约；运行/安全/迁移身份 | `3eaaf572`、`67655c83`、`027e1c3b`、`5d4b73a9`、`7359dd53`、`4254dc65`、`11a239b8`；收口见本文件所在提交 | 268 项隔离回归、91 项专项、真实角色/ACL、Node 7 项、TypeScript/Vite、双 Compose、浏览器 | 是（仅本 Day 4 主线原子提交） | RAG-R1 外部工作树持续推进；未 merge、未 cherry-pick、未复制，未覆盖主线契约 | 逆序逐笔 `git revert`；ACL 按检查点策略精确撤销；停止服务后恢复本地配置 |
| `beta10d/day5-data-truth` | Day 5 数据真实性与时效语义 | 统一事实元数据、报告/预测/策略/首页状态、响应式、测试和证据；17 个代码/测试文件 | Day 4 PASS `e1be5d0…` | Day4 `dataset_id`；统一 `run_id`/model/feature/window/freshness；七态页面契约 | `245cd3e3`、`6d285b9f`、`ff625e59`、`8e3c5a1e`、`974d1e98`、`5e82fbc5`、`beb4bc28`、`6e7dcde6`；收口见本文件所在提交 | 110 项 Day5 隔离、268 项 Day3/4 回归、Node 7、TypeScript/Vite、20 个浏览器矩阵、DB 指纹 | 是（仅 Day5 主线原子提交） | 与 RAG 的来源/时效元数据、Router、公共配置和数据库契约存在潜在共享面；本轮未处理 | 逆序 `git revert` Day5 提交；数据库 public 无变更 |
| `codex/rag-enterprise-ingestion` | RAG ingestion 支线 | 未收到正式交付清单，本轮只读核验、不集成 | 未声明 | 不得修改正式迁移、公共配置、权限矩阵、Router、数据库 ACL；后续需适配 Day5 真实性元数据 | `4cce50bf40fe1b50ddbe3bdd62e2c33aaf657227` | worktree clean；无主线可核验交付 | 否 | 潜在来源元数据/公共配置/Router/数据库冲突仅登记 | 不 cherry-pick；无主线变更 |
| `codex/rag-enterprise-runtime` | RAG runtime 支线 | 未收到正式交付清单，本轮只读核验、不集成 | 未声明 | 不得覆盖 Day4 白名单、运行身份、权限矩阵、正式 Router；后续需适配 Day5 freshness/run 契约 | `c79671c82b2b2cd6deedc0f9cb136349fc3d0b1d` | worktree clean；无主线可核验交付 | 否 | 潜在 AI/来源分类/时效契约冲突仅登记 | 不 cherry-pick；无主线变更 |

## Day 5 隔离复核

- 旧 RAG-R1 `beta10d/day4-data-access-security`：`7eaf8d3152f8ffe5bd983068a99145c9693b4925`，接管前后相同，worktree clean。
- RAG ingestion/runtime：接管前后 HEAD 均相同，worktree clean。
- Day4 v2：`e1be5d0bb4213daa52025e01cf84320f271d0898`，只读且 clean。
- Day5 对 RAG merge、cherry-pick、文件复制和当前 PostgreSQL RAG 数据写入均为 0。

## 集成门禁

支线交付必须同时满足：不超过 20 文件、不超过 1000 行有效代码、工作树干净、独立测试和证据完整、无当前 PostgreSQL 写入、无正式 Alembic revision、无真实密钥、未超出文件所有权。共享文件冲突由主线重新实现，不直接 merge 整支线。
