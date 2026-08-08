# PROJECT_BASELINE_SUMMARY.md

## 1. 当前唯一 RC 基线

- 基线日期：2026-08-08。
- 产品版本：v2.11.2。
- 唯一 RC 分支：`release/beta10d-agent-rc-20260807`。
- 集成输入 HEAD：`0f6f1841e64b6f4bd83e01d57584c901254c3302`；最终闭环提交以本文件所在提交为准。
- RC 工作树：`E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807`。
- 主工作树 `E:\智能运营分析项目` 的未提交和未跟踪内容属于用户，未被本 RC 修改或接管。
- 当前阶段：本地统一 RC 基础服务可复现启动；不代表生产发布、模型切换、RAG 发布或外部系统联调完成。

## 2. 已集成来源

- Day 8 基线：`bc36715d6943c212197d2e3dce5d8f2c6949bd08`。
- RAG-R1 最终集成祖先：`1c8c2b195c01a18eb69715fa3017c0f5015498ce`。
- 证据闭环：`d5376bf899028b2353b73c84dfac2b25b3e6c7f9`。
- 检索性能契约：`63fc9fc`，集成提交 `9ff8caebe68f47e9481fa512b7c660af8691fc98`。
- 检索性能修复：`ef5217b58bb8c888d4f6e2c724775d065c0cd9e8`，集成提交 `0f6f1841e64b6f4bd83e01d57584c901254c3302`。
- `4a514d34113ee06a5725fa3f23bcf28298374040` 与已集成 `c622754bc2e42e1d488bce9d86c88b8c0084ea32` 补丁等价，未重复合入。

## 3. 当前运行事实

- Python：共享 E 盘项目虚拟环境，Python 3.11.9。
- Node.js：v24.18.0；前端复用 Git 公共工作树中已批准依赖，不自动联网安装。
- PostgreSQL：仅允许 `localhost:5432/postgres`；Web 运行态使用 `beta10d_app_login`，安全仓储使用 `beta10d_security_login`。
- Alembic：唯一 head `0018_rag_enterprise_r1`。
- 数据库只读指纹：73 tables / 8 views / 47 sequences / 37 routines；写入计数 0。
- Redis：Docker `redis:7-alpine`，仅监听 `127.0.0.1:6379`。
- Celery：Windows `solo`、并发 1、仅监听 `phase4_health`；组合健康任务已验证结果后端可回读。
- Web：FastAPI `127.0.0.1:8000`、Vite `127.0.0.1:5173`，均已通过 HTTP 200 冒烟。

## 4. 数据、模型与 RAG 边界

- Active 模型仍为 `model_20260620_063015` / `features_140db8af25f9`；本任务未反序列化模型、未训练、未注册或激活 Candidate。
- 历史源事实水位仍为 2026-06-18 23:00；不得宣称为当前实时数据。
- PostgreSQL 中 `RAG-R1` 仍为 `candidate`、`is_current=false`、`validated_at/published_at` 为空。
- 本任务未启动 Qdrant、未创建 snapshot、未切 alias、未发布 RAG；统一入口当前只承诺基础服务健康。
- 未执行迁移、Seed、同步、预测、报告、策略、外部网络调用或生产切换。

## 5. 默认入口与证据

- 默认双击：`run_project.bat`。
- 维护菜单：`run_project.bat menu`。
- Web 直接入口：`run_web_platform.bat`。
- Day1 证据：`docs/codex/evidence/DAY1_UNIFIED_RC_20260808_164500`。
- 集成与运行状态：`docs/codex/RC_INTEGRATION_MANIFEST.md`、`docs/codex/RC_STATUS.md`。
