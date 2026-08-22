# 项目一 v2.12.0 文件所有权冻结

## 1. 总则

所有权按“路径 + 业务职责”双重判断。路径未明确列出、需要跨任务修改或同一文件同时落入两个职责域时，任务分支必须停止并把建议交给 Final Integration。任务分支不得通过复制、重命名或新增平行实现绕开所有权。

冻结契约文件 `docs/codex/v2_12_final/INTERFACE_CONTRACT.md`、本文件和 `ACCEPTANCE_MATRIX.md` 仅由 Final Integration 修改；A/B/C 只读。

## 2. A：核心 P0、预测和业务事实链

允许：

- `prediction_engine/**`
- `model_ops/**`
- `backend/app/workers/**` 中 forecast worker 与预测队列相关文件
- `backend/app/api/**`、`backend/app/services/**`、`backend/app/repositories/**`、`backend/app/schemas/**` 中仅与 forecast/model 事实、预测任务、预测到首页/策略/报告同一 `run_id` 链路直接相关的文件
- 必要时的 `migrations/**`，且仅限无法兼容实现的预测/模型事实变更，必须保持唯一 Head 和完整 downgrade
- 上述范围的后端测试、夹具与 `docs/codex/v2_12_final/A_CORE_STATUS.md`、`docs/codex/evidence/A_core/**`

禁止：

- `frontend/**`
- 后端 AI、ChatBI、model gateway、附件解析、RBAC capability
- `run_project*`、启动/停止/状态/日志/doctor 脚本
- `.github/workflows/**` 和 CI
- 模型 Active 晋升、RAG alias 或生产切流

## 3. B：全站前端、前端权限体验和全局 AI Shell

允许：

- `frontend/**`
- 前端 API client、TypeScript type、设计系统、组件、样式、路由、状态管理和前端测试
- `docs/codex/v2_12_final/B_UI_STATUS.md`、`docs/codex/evidence/B_ui/**`

禁止：

- `backend/**`
- `migrations/**`
- `prediction_engine/**`、`model_ops/**`
- 启动脚本、CI、数据库或后端权限实现
- 用 Mock、静态数据或接口失败后的成功态填补后端缺口

B 只能按照已冻结契约修改前端 client/type；若后端现状不满足契约，必须显示 `Unavailable`/明确失败并把缺口交给 C 或 Final Integration。

## 4. C：AI Runtime、附件、RBAC capability、启动与质量门禁

允许：

- `backend/app/ai/**`、`backend/app/ai_assistant/**`、`backend/app/chatbi/**`
- `backend/model_gateway/**` 及后端 model gateway 直接依赖
- 后端 AI 会话、流式响应、附件解析/会话绑定、页面上下文守卫、Citation/Trace 相关 endpoint/service/repository/schema
- 后端认证与 RBAC capability manifest，以及相关测试
- `run_project*`、`run_web_platform*`、`scripts/**` 中启动/停止/status/logs/doctor 与运行来源治理文件
- `.github/workflows/**`、质量门禁、发布入口文档和相关集成测试
- `docs/codex/v2_12_final/C_AI_RUNTIME_STATUS.md`、`docs/codex/evidence/C_ai_runtime/**`

禁止：

- `frontend/**`
- `prediction_engine/**`、`model_ops/**`
- forecast 核心事实、预测模型与预测结果算法
- 模型 Active 晋升、RAG production alias 或生产切流

## 5. 共享路径处置

- 若 `backend/app/main.py`、公共配置、公共错误模型或公共路由注册必须修改，默认归 C；A 需通过状态文件提交精确需求，由 Final Integration 协调。
- 若预测链需要策略/报告后端文件，A 可做最小事实一致性修改，但不得进入 AI 生成、附件或前端范围。
- 通用测试文件按被测主模块归属；跨域验收测试由 Final Integration 在合并后新增或修复。
- `docs/codex/TASK_STATUS.md`：各任务可只追加自己的单行状态；发生冲突由 Final Integration 处理。

## 6. 所有权验收

每个任务交付时必须提供：

```powershell
git diff --name-status <INTEGRATION_SEED_SHA>...HEAD
git status --short --branch
```

任何越权文件、未解释的生成物、敏感配置、模型二进制或异常大文件都会使 `READY_FOR_INTEGRATION=NO`。不得以“构建需要”或“顺手修复”为由扩大范围。
