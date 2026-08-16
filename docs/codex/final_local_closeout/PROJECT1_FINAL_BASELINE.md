# 项目一最终事实基线

- 项目：智能运营分析项目
- 产品版本：v2.11.2
- 唯一最终目录：`E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807`
- 唯一最终分支：`release/beta10d-agent-rc-20260807`
- 起始 SHA：`adac8eca4eae70548a648c14b7f3c61242d1a1f3`
- 最终 SHA：以 annotated tag `project1-v2.11.2-local-final-rc-20260816^{}` 的解析值为准；40 位值同时写入 Git 后置核验证据。
- 最终标签：`project1-v2.11.2-local-final-rc-20260816`
- 启动命令：在唯一最终目录执行 `run_project.bat`
- 前端：`http://127.0.0.1:5173`
- 后端健康：`http://127.0.0.1:8000/api/health`
- 后端文档：`http://127.0.0.1:8000/docs`

## 运行关系

`run_project.bat` 先验证本地最小权限 PostgreSQL 身份与唯一 Alembic Head，再启动/复用 Redis、TLS Qdrant、健康 Celery worker、专用预测 Celery worker、Memory outbox worker、FastAPI 与 Vite。应用身份不是 PostgreSQL 超级管理员；Qdrant API 只加载只读 Key。

## 已完成能力

- 首页候选已正式集成并完成 1920/1536/1366 与 1672 视口验收。
- 系统状态三个读接口使用正确的应用读取连接缝，合法调用不再返回 500。
- 更新预测任务具备独立队列、可观测任务映射、成功/失败终态、重复提交和 worker 不可用门禁。
- 当前数据库唯一 Head 为 `0022_chatbi_semantic_v1`。
- 最终后端、前端、32 路由浏览器、两轮启动、安全与清理门禁均有证据。

## 本地 RC 边界

这是一份本地预发布 RC，不是生产上线。生产域名/TLS 终止、正式密钥托管与轮换、灾备演练、生产监控告警、容量压测、外部审批、Candidate 晋升 Active、RAG production alias 切换均未执行。

## 入口约束

不要再从历史 GUI 批处理、历史 Day/候选 worktree 或普通仓库目录启动最终版。普通仓库 `E:\智能运营分析项目` 当前属于用户工作区，含未提交代码与未跟踪资产，已全程只读保护，因此不是最终入口。
