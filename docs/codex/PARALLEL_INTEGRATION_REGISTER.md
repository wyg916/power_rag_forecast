# 并行集成登记

本文件由主线唯一集成负责人维护。Day 4、Day 5、Day 6、Day 6A 输入门禁均未合并、未 cherry-pick、未复制任何 RAG-R1 或两条 RAG 支线内容。

| 分支 | 任务包 | 文件范围 | 依赖 | 共享契约 | 提交哈希 | 测试 | 已集成 | 冲突 | 回滚方式 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `beta10d/day4-data-access-security-v2` | Day 4 数据访问安全 | 注册表、数据 API、AI 受控查询、数据库身份/ACL、Compose、数据中心、测试和证据 | Day 3 PASS `45092b8…` | API 权限矩阵；`dataset_id` 契约；运行/安全/迁移身份 | `3eaaf572`、`67655c83`、`027e1c3b`、`5d4b73a9`、`7359dd53`、`4254dc65`、`11a239b8`；收口见本文件所在提交 | 268 项隔离回归、91 项专项、真实角色/ACL、Node 7 项、TypeScript/Vite、双 Compose、浏览器 | 是（仅本 Day 4 主线原子提交） | RAG-R1 外部工作树持续推进；未 merge、未 cherry-pick、未复制，未覆盖主线契约 | 逆序逐笔 `git revert`；ACL 按检查点策略精确撤销；停止服务后恢复本地配置 |
| `beta10d/day5-data-truth` | Day 5 数据真实性与时效语义 | 统一事实元数据、报告/预测/策略/首页状态、响应式、测试和证据；17 个代码/测试文件 | Day 4 PASS `e1be5d0…` | Day4 `dataset_id`；统一 `run_id`/model/feature/window/freshness；七态页面契约 | `245cd3e3`、`6d285b9f`、`ff625e59`、`8e3c5a1e`、`974d1e98`、`5e82fbc5`、`beb4bc28`、`6e7dcde6`；收口见本文件所在提交 | 110 项 Day5 隔离、268 项 Day3/4 回归、Node 7、TypeScript/Vite、20 个浏览器矩阵、DB 指纹 | 是（仅 Day5 主线原子提交） | 与 RAG 的来源/时效元数据、Router、公共配置和数据库契约存在潜在共享面；本轮未处理 | 逆序 `git revert` Day5 提交；数据库 public 无变更 |
| `beta10d/day6-business-loop` | Day 6 当前输入门禁 | 独立 Worktree、Git/数据库/模型只读门禁、同步能力审计、NOT PASS 证据 | Day 5 PASS `e907a50…` | 后续仍需统一 `run_id`、模型/特征/窗口/报告/策略/审核/反馈契约；本轮未产生业务事实 | 本行所在文档收口提交 | 当前数据止于 2026-06-18，未来 24 小时负荷/天气输入缺失；数据库写入 0 | 否（业务闭环未启动） | RAG 来源/Router/权限/迁移与 Day 6 共享面均未触碰；后续不得把 RAG 支线作为输入补齐旁路 | 仅 `git revert` 文档收口提交；数据库无需回滚 |
| beta10d/day6a-forecast-input-pipeline | Day 6A Active 特征可用性门禁 | 凭据事件收口、脱敏检查点、170 项特征矩阵、NOT PASS 证据 | Day 6 基线 92a1989；安全修复 49201c4 / 6a55cd1 / d04af4a | Active 170 项 schema、预测时点语义、来源/时效、最小权限；未创建迁移或输入批次 | 本行所在文档收口提交 | 170/170 契约审计；15 项结构性阻断；18 项防泄露、7 项 schema/泄漏测试 | 否（停在阶段 A） | RAG 两支线 HEAD 不变、clean、非 Day 6A 祖先；共享 Router、权限、配置、迁移和数据库均未触碰 | 逆序 git revert Day 6A 提交；数据库无业务变更；凭据不回退 |
| `beta10d/day6b-online-safe-model` | Day 6B online-safe 契约与 Candidate 重训 | 170 项对照、52 项 Candidate 契约、可复现训练/评估、独立 artifact、NOT PASS 证据 | Day 6A `669436d…`；Active 只读基线 | target-24h/25h 历史截止、固定顺序/dtype、无未来 actual/RT spread/补零、Candidate 不自动激活 | `7602c20d7dc102ceb4e66b5932c4d8f043b4da83`；收口见本文件所在提交 | 6 项专项、38 项相关回归、24 项凭据复验、artifact 15/15 hash；性能门禁失败 | 否（Candidate 未注册、未激活） | RAG ingestion/runtime/R1 HEAD 不变且 clean；merge/cherry-pick/复制/数据库写入均为 0 | 逆序 revert 收口与实现提交；本地 Candidate 未激活，无数据库回滚 |
| `codex/rag-enterprise-ingestion` | RAG ingestion 支线 | 未收到正式交付清单，本轮只读核验、不集成 | 未声明 | 不得修改正式迁移、公共配置、权限矩阵、Router、数据库 ACL；后续需适配 Day5 真实性元数据 | `4cce50bf40fe1b50ddbe3bdd62e2c33aaf657227` | worktree clean；无主线可核验交付 | 否 | 潜在来源元数据/公共配置/Router/数据库冲突仅登记 | 不 cherry-pick；无主线变更 |
| `codex/rag-enterprise-runtime` | RAG runtime 支线 | 未收到正式交付清单，本轮只读核验、不集成 | 未声明 | 不得覆盖 Day4 白名单、运行身份、权限矩阵、正式 Router；后续需适配 Day5 freshness/run 契约 | `c79671c82b2b2cd6deedc0f9cb136349fc3d0b1d` | worktree clean；无主线可核验交付 | 否 | 潜在 AI/来源分类/时效契约冲突仅登记 | 不 cherry-pick；无主线变更 |

## Day 5 隔离复核

- 旧 RAG-R1 `beta10d/day4-data-access-security`：`7eaf8d3152f8ffe5bd983068a99145c9693b4925`，接管前后相同，worktree clean。
- RAG ingestion/runtime：接管前后 HEAD 均相同，worktree clean。
- Day4 v2：`e1be5d0bb4213daa52025e01cf84320f271d0898`，只读且 clean。
- Day5 对 RAG merge、cherry-pick、文件复制和当前 PostgreSQL RAG 数据写入均为 0。

## Day 6 输入门禁隔离复核

- RAG Ingestion：`codex/rag-enterprise-ingestion` / `4cce50bf40fe1b50ddbe3bdd62e2c33aaf657227`，worktree clean，未集成。
- RAG Runtime：`codex/rag-enterprise-runtime` / `c79671c82b2b2cd6deedc0f9cb136349fc3d0b1d`，worktree clean，未集成。
- 旧 RAG-R1 工作树：`beta10d/day4-data-access-security` / `7eaf8d3152f8ffe5bd983068a99145c9693b4925`，未读取交付内容、未集成。
- 已完成任务包仅为 Day 6 Worktree 与只读输入门禁；待集成契约仍是 `run_id`、来源/时效元数据、权限矩阵、Router 和迁移边界。
- 主线状态：`CURRENT FORECAST INPUT GATE NOT PASS`；未执行 Day 6 业务写链，未进入 Day 7。

## Day 6B 隔离复核

- RAG Ingestion：`codex/rag-enterprise-ingestion` / `4cce50bf40fe1b50ddbe3bdd62e2c33aaf657227`，worktree clean。
- RAG Runtime：`codex/rag-enterprise-runtime` / `c79671c82b2b2cd6deedc0f9cb136349fc3d0b1d`，worktree clean。
- 旧 RAG-R1：`beta10d/day4-data-access-security` / `7eaf8d3152f8ffe5bd983068a99145c9693b4925`，worktree clean。
- Day 6B merge、cherry-pick、文件复制和 RAG 数据库写入均为 0；未修改 Router、权限矩阵、迁移、公共配置或 RAG 数据。
- 主线状态：`DAY6B NOT PASS`、`DAY6A REENTRY NO`、`DAY7 NO`。

## 集成门禁

支线交付必须同时满足：不超过 20 文件、不超过 1000 行有效代码、工作树干净、独立测试和证据完整、无当前 PostgreSQL 写入、无正式 Alembic revision、无真实密钥、未超出文件所有权。共享文件冲突由主线重新实现，不直接 merge 整支线。
