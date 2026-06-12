# AI 自动化说明

本项目当前采用以下分层：

- `高峰尖刺增强版_电力市场电价预测与智能分析系统_v4_fix1.py`
  - 预测引擎
- `00_local_model_inventory.py`
  - 盘点本机硬件、Ollama 与 HF 本地模型
- `01_run_prediction.py`
  - 包装并执行预测引擎
- `02_build_ai_summary.py`
  - 从 `结果-3/结果表` 提取关键结果，生成 `ai_input_summary.json`
- `03_llm_generate_report.py`
  - 调用本地 Ollama 模型生成日报
- `04_dispatch_report.py`
  - 本地归档并预留 webhook 派发
- `main_daily_run.py`
  - 自动化总控

默认模型选择：

- 默认：`qwen3:4b`
- 可选升级：`qwen3:8b`
- 不建议作为本机默认：`qwen3:14b`、`qwen3:30b`

当前默认使用 `Ollama native API`，原因是 `qwen3` 在本机环境下通过 native API 更稳定，能正确关闭 thinking 并按 JSON schema 输出结构化结果。

主要输出目录：

- `自动化输出/current`
  - 当前最新一次摘要、日报、告警
- `自动化输出/dispatch/latest`
  - 当前最新一次归档派发结果
- `自动化输出/dispatch/<时间戳>`
  - 历史归档
- `自动化输出/logs`
  - 自动化运行日志

调度建议：

- Windows 任务计划直接调用：
  - `run_daily_pipeline.bat`
- 只想复用已有预测结果重新生成日报时调用：
  - `run_daily_pipeline_skip_prediction.bat`

## 阶段一稳定性优化说明

- 新增 `.env.example`，真实数据库密码、PJM Key、LLM 地址/模型等配置应写入项目根目录 `.env` 或系统环境变量，不再写入代码和 YAML。
- 新增 `requirements.txt`，用于 Python 3.11 环境复现依赖。
- `04_dispatch_report.py` 已移除整目录递归删除逻辑，最新归档通过 `自动化输出/dispatch/latest_pointer.txt` 指向。
- `main_daily_run.py --skip-prediction` 会先检查正式预测表和 AI 报告依赖结果表，缺失时会明确终止并提示原因。
- LLM 报告生成已增加 JSON 片段提取、schema 校验、指数退避重试和模板回退。
- 所有一键启动 `.bat` 已启用 UTF-8，并在缺少 `.env` 时给出提示。

注意：

- 当前 `18_未来24小时预测结果_演示版.xlsx` 仍是演示版，不是真实线上前瞻预测。
- 因此 AI 日报中已经固定写明“演示版预测”限制。

## 阶段二工程化重构说明

- 新增 `prediction_engine/` 包，对 v4_fix1 的特征工程、模型选择、模型训练、正式前瞻、评估、绘图和流水线入口做兼容模块化封装。
- v4_fix1 已增加 `main()` 和 main guard，作为兼容入口保留；导入模块时不会直接触发完整训练流程。
- 新增 `services/` 服务层，`main_daily_run.py` 现在通过 `services.pipeline_steps.run_pipeline_step()` 调度数据刷新、预测、AI 摘要、LLM 报告和归档派发。
- 每次预测训练完成后会尝试写入 `model_artifacts/model_<run_id>/`，包括 `base_model.joblib`、`peak_model.joblib`、`spike_classifier.joblib`、`feature_cols.json`、`training_config.json`、`metrics.json`、`thresholds.json`、`input_schema.json` 和 `model_card.md`。
- 正式未来 24 小时预测结果新增残差分布法 P10/P90 预测区间字段，用于表达价格波动风险范围，不改变原点预测逻辑。
- 新增 `migrations/`，包含 `model_registry`、`prediction_tracking`、`model_evaluation_runs` 和 `monitoring_metrics` 等幂等 SQL；可通过 `database_utils.apply_database_migrations()` 执行。
- 新增阶段二测试：字段标准化、泄漏过滤、正式前瞻预测区间、模型 artifact、migrations，并保留阶段一安全测试。

## 阶段三/四模型自优化与运维说明

- 预测流程在数据库可用时会把本次 `model_artifacts/model_<run_id>/` 登记到 `model_registry`，并把未来 24 小时预测写入 `prediction_tracking`。
- 新增 `05_update_actuals_and_errors.py`：从 `raw_da_price` 回填真实日前价格，计算 `abs_error`、`pct_error`，并刷新 `model_performance_daily`。
- 新增 `06_model_monitor.py` / `run_model_ops_daily.bat`：执行真实值回填、近期误差监控，并在模型退化时登记 `model_retrain_jobs`。
- 新增 `07_compare_and_promote_model.py`：按 RMSE、高峰 RMSE、尖峰 RMSE 阈值对比候选模型与 active 模型，支持人工指定版本上线。
- 新增 `09_health_check.py` / `run_health_check.bat`：检查 Python、依赖、数据库、关键文件和输出目录；报告写入 `自动化输出/logs/health_check_*.json`。
- 新增 `10_smoke_test.py` / `run_smoke_test.bat`：执行轻量整体自检，验证启动链路和关键模块，不强制跑完整训练。
- 一键启动 `.bat` 已统一转换为 Windows CRLF、启用 `chcp 65001`，失败时显示错误码并停留窗口；计划任务通过 `NO_PAUSE=1` 后台运行，不会被 pause 卡住。
- 缺少 `.env` 或 `DB_PASSWORD` 时，主流程会自动切换为本地文件模式，继续生成 AI 摘要、模板报告和归档；数据库同步、模型注册和追踪落库会明确跳过。

## v2.6.0 Web 产品化二次优化

- 新增 FastAPI 后端 `backend/app/main.py`，将预测结果、策略建议、AI 问答、异常解释、AI 报告、模型监控和任务运行封装为 API。
- 新增 React + Vite + TypeScript + Ant Design 前端 `frontend/`，用于浏览器访问完整本地工作台。
- 新增 Web 一键启动脚本 `run_web_platform.bat`，访问地址为 `http://127.0.0.1:5173`。
- 新增 Web 自检脚本 `run_web_smoke_test.bat`。
- 新增数据库迁移 `migrations/009_create_web_platform_tables.sql`，用于策略建议、AI 会话、异常解释、报告审核和 Web 任务记录。
- 预测模型仍复用现有 v4_fix1 兼容流程，Web 版只做产品化封装和业务增强。

## v2.6.1 Web 交互与启动稳定性优化

- `run_web_platform.bat` 新增端口检测，重复双击时会复用已有 8000/5173 服务，不再因端口占用直接失败。
- Web 前端新增可拖动 AI 悬浮助手、页面级 AI 解读、数据源官网展示和定时任务新增/删除管理。
- 放大整体字号，并优化左侧导航、模型监控和任务日志布局。

## v2.6.3 AI 问答助手与报告中心修复

- 新增 `run_project.bat` 作为统一核心启动菜单，日常不再需要在大量脚本中查找入口。
- AI 问答助手按开发文档落地为“意图识别 + 工具调用 + 结构化上下文 + Answer Guard”流程，不再无论问什么都返回同一套模板。
- 新增 `backend/app/ai/` 模块和 `migrations/010_create_ai_assistant_tables.sql`，记录工具调用日志和 Prompt 模板。
- 前端问答输入框改为稳定原生多行输入，回答下方展示意图、数据依据和相关跳转。
- 修复 AI 报告中心操作建议被压成逐字竖排的问题。

## v2.7.0 第一阶段 AI 智能问答落地

- 新增第一阶段标准数据接口，覆盖预测概览、预测明细、历史电价、天气、负荷、新能源状态、模型解释和风险等级。
- 新增 Dify 可选接入与本地千问 OpenAI-compatible 模型网关；未配置 Dify 时自动使用本地数据增强助手兜底。
- 新增 `knowledge_base/` 电力业务知识库和 `migrations/011_create_ai_chat_feedback.sql` 问答反馈表。
- Web AI 助手新增历史会话、复制回答、清空会话、点赞/点踩反馈、数据使用标签和建议关注展示。

## v2.7.1 AI 助手交互与数据表查看修复

- AI 助手增加发送防抖和请求锁，避免一次输入触发重复发送。
- 输入框增加中文输入法组合输入保护，支持逐字逐字符中英文输入。
- 新增 weather_analysis 意图，普通天气问题直接回答天气，不再强行转成电价分析。
- 抽屉与主界面补充响应式布局，移动/窄屏下优先保证聊天区和输入区完整可见。
- 数据接入中心新增数据库表查看、表名筛选和单表内容筛选。

## v2.9.1 LangGraph 多 Agent 分析落地

- 新增 `backend/langgraph_agent/` 第二阶段工作流模块，可按意图、数据、预测、风险、报告和答案整合节点追踪执行过程。
- 新增 `/api/ai/agent/analyze` 接口，复杂业务问题会联合预测、负荷、天气、历史价格、模型解释、风险和知识库数据生成专业回答。
- `/api/ai/chat` 已切换到多 Agent 兜底逻辑，普通天气和通用问题不再强行套用电价模板。
- 本地模型服务可用时参与答案整合；未连接时返回明确状态，并使用工具链证据生成回答。


