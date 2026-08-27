# 回滚方案

## 发布状态

1. 保持独立发布 Worker 健康，使用同一租户、审计 run/trace 调用受控 `rollback` 动作。
2. 验证 PostgreSQL `RAG-R1` 不再为 current，前一发布版本按状态机恢复；若没有前一版本，Alias 应为空且 Search fail-closed。
3. 验证 Qdrant Alias 与 PostgreSQL current 一致、snapshot 可读、审计存在 rollback 事实。
4. 禁止手工 UPDATE `kb_releases.is_current/status`，禁止直接绕过 Worker 改 Alias。

本任务未实际执行回滚，因为用户要求最终保持已发布可搜索状态；回滚/幂等路径由专项自动化覆盖。

## 本地发布配置

- 精确备份：`E:\智能运营分析项目_本地配置\beta10d_day4_runtime.env.pre_rag_release_20260827_232339.bak`。
- 恢复前先停止发布 Worker 和后端，核对目标文件绝对路径，再用备份单文件替换。
- 恢复后重新启动后端时，不得输出连接 URL 或密码。

## BM25 运行资产

- 目标：`E:\智能运营分析项目\.runtime\rag\releases\RAG-R1\bm25_profile.json`。
- 文件可从已发布 8,339 个片段按冻结算法重建，不属于业务原始数据。
- 若需撤回，先停止后端并确认 Search 允许进入不可用状态，再对该单一明确文件操作；不得递归删除 `.runtime`。

## Git 证据

- 仅证据提交需要撤回时执行 `git revert <本任务提交>`。
- Git revert 不会回滚 PostgreSQL/Qdrant/外部配置，三者必须按上面的受控路径分别处理。
