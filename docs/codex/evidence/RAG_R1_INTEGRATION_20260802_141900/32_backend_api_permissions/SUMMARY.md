# RAG-R1 后端只读 API 与权限收口

- 状态：`PASS`（仅只读 Release API、诊断权限和发布 fail-closed；完整检索与发布尚未完成）。
- 新增 PostgreSQL Release 只读适配器，事务显式 `READ ONLY`，仅接受服务端 `default` tenant。
- 新增 Release 列表、创建、验证、发布、回滚路由及诊断路由；客户端 tenant 覆盖一律 400。
- 普通 Release 响应仅暴露 `release_id/status/created_at/updated_at`，不暴露 Collection、模型、Provider、维度、manifest、run/trace 等技术追溯字段。
- 冻结角色矩阵已落实：Admin 全权；Analyst 只读；Reviewer 读/写/发布；Developer 仅诊断；Viewer 无知识库读取权限。
- 所有企业写动作仍返回 `enterprise_release_write_control_not_configured`，不会误发布、切 alias 或晋升 Candidate。
- 权限矩阵已可复现更新为 201 个 method+path、188 个唯一路径、7 个公开、194 个受保护。
- 定向测试 83 passed；py_compile、权限矩阵 `--check`、`git diff --check` 均 PASS。

## 真实只读验证

- 目标：`localhost:5432/postgres`；身份：`beta10d_forecast_login`；危险角色属性全为 false。
- 受限身份对 documents、versions、chunks、releases、release_items 仅有 SELECT，Release 列表 API 返回 200。
- 发布请求返回 503；数据库仍为 `RAG-R1 / candidate / is_current=false`，持久写入 0。
- 该身份尚无 `kb_retrieval_runs`、`kb_citations`、`kb_rag_audit_events` 的 INSERT 权限；后续检索审计接入前必须建立独立最小 GRANT 与回滚证据。
- 主项目 `.env` 当前仍指向 postgres 管理身份且缺少独立 SECURITY_DATABASE_URL；本包没有覆盖配置，不能据此宣称完整应用生产化运行。

## 回滚

- 代码和文档：对本包提交执行 `git revert <commit>`。
- 数据库：本包持久写入为 0，无数据库回滚动作。
- Candidate Collection、Qdrant alias/snapshot、Published/生产切换均未改变。
