# 统一 RC 状态

## 结论

`release/beta10d-agent-rc-20260807` 已达到“本地统一 RC 基础服务可复现启动”门槛：默认双击入口、最小权限数据库身份、单迁移 head、Redis、隔离 Celery、FastAPI、前端和组合健康任务均通过。

本结论不是生产发布许可，不代表模型切换、RAG 发布、正式预测、报告或策略闭环完成。

## 身份与版本

- 集成输入 HEAD：`0f6f1841e64b6f4bd83e01d57584c901254c3302`。
- 最终闭环提交：以本文件所在提交为准。
- Alembic：`0018_rag_enterprise_r1`，单 head。
- 数据库：`localhost:5432/postgres`。
- Web 运行身份：`beta10d_app_login`。
- 安全仓储身份：`beta10d_security_login`。
- 启动入口：`run_project.bat`；维护菜单：`run_project.bat menu`。

## 当前验证

- 启动前检：PASS，凭据未输出。
- 一键启动：PASS；Redis、隔离 Celery、后端、前端、组合健康任务全部健康。
- 后端健康：HTTP 200。
- 前端：HTTP 200，生产构建 3675 modules PASS。
- Python 目标回归：87 passed。
- 数据库只读指纹：73 tables / 8 views / 47 sequences / 37 routines，Alembic `0018`，写入 0。
- RAG 数据库状态：`RAG-R1` 为 `candidate`、`is_current=false`，未验证、未发布。

## 未授权或未执行

- 数据库迁移、Seed、业务同步、预测、报告、策略和外网调用：0。
- 模型二进制反序列化、训练、注册、Candidate 晋升或 Active 切换：0。
- Qdrant 启动、snapshot、alias 切换、RAG 发布：0。
- 生产切换：NO。

## 证据与回滚

- 证据：`docs/codex/evidence/DAY1_UNIFIED_RC_20260808_164500`。
- 任务前检查点：`E:\智能运营分析项目\backups\phase3\20260808_163406634_DAY1_UNIFIED_RC_PRE`。
- 代码回滚：按本任务提交逆序 `git revert`；主工作树用户改动未被修改。
- 运行态回滚：停止本 RC 启动的 Web 进程和隔离 Celery；Redis 停止时保留数据卷。不得自动终止未知进程。
