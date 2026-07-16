# PROJECT_BASELINE_SUMMARY.md

## 1. 当前事实基线
- 基线日期：2026-07-14。
- 产品版本：v2.11.2。
- 当前分支：p5-frontend-ai-experience。
- HEAD：f8dc0bc；本地分支领先远端 10 个提交。
- 工作区存在较多未提交和未跟踪文件，因此 Git HEAD 不能单独代表磁盘基线。
- 当前阶段：开发演示。
- 工程完成度：64.6%（36 个活动模块中 14 已验证完成、16 部分完成、5 被阻塞、1 尚未开始）。
- 下一阶段目标：先达到“可稳定本地运行”，再推进企业试点与私有化部署。

## 2. 当前五项 P0
1. 模型事实源分裂，读请求可能通过 seed 逻辑改变 Active 状态。
2. 模型加载与特征契约不安全，运行时存在缺列静默补 0。
3. 刷新、预测、同步缺少统一 run_id 与原子事务，存在全表覆盖和半成品风险。
4. 认证默认开放、默认 JWT、前后端认证口径不一致，生产环境必须 fail-closed。
5. seed/demo/fallback 可能在真实页面或 AI 回答中冒充业务事实。

## 3. 模型与预测事实
- 唯一最新完整候选 artifact：`model_artifacts/model_20260620_063015`。
- 模型身份：Candidate，不是 Active。
- feature_version：`features_140db8af25f9`。
- 目标：`da_price`；特征数量：170。
- 当前 `model_registry=0`，`model_versions=5` 条展示/seed 记录。
- 当前 `forecast_runs=1`、`forecast_results=0`，不能视为有效预测闭环。
- joblib 尚未完成授权安全加载，快速预测当前不可安全执行。

## 4. 已验证能力
- React/Vite 主页面可启动并构建。
- FastAPI 最小运行栈、health、DB/task health 可用。
- Redis/Celery 最小无副作用任务可用。
- DeepSeek 最小真实调用可用。
- PJM/Open-Meteo 小窗口采集可用。

## 5. 当前不可作为稳定能力宣称的内容
- 真实唯一 Active 快速预测。
- 统一 run_id 的刷新—预测—同步链。
- 真实模型中心。
- 当前 RAG 评分和 AI 100 题通过率。
- 报告审核/发布/派发状态机和真实收益闭环。
- Ollama 本地推理。

## 6. 第一批任务顺序
- 安全线：T004 可独立实施。
- 模型预测主线：T001 → T002 → T003 → T005。
- 完成上述任务并通过双跑、幂等、失败回滚、旧批次共存和来源一致性验收后，才可将状态升级为“可稳定本地运行”。
