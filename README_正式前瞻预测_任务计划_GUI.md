# 正式前瞻预测、任务计划与 GUI 使用说明

## 1. 本次新增内容

- 预测引擎已把“未来24小时演示版”改为“未来24小时正式前瞻版（递推预测）”
- 新增 Windows 任务计划创建脚本
- 新增可视化 GUI 控制台，可一键启动全流程

## 2. 正式前瞻预测的输出文件

运行预测引擎或全流程后，正式版文件会输出到：

- `<项目根目录>\结果-3\结果表\18_未来24小时预测结果_正式版.xlsx`
- `<项目根目录>\结果-3\结果表\18_未来24小时预测输入特征_正式版.xlsx`
- `<项目根目录>\结果-3\图表\21_未来24小时日前电价预测图_正式版.png`

说明：

- 正式版不是再拿历史最后 24 行直接预测
- 它会从最后一个可用历史时点往后逐小时递推
- 已预测出的前一小时价格会回填给后续小时作为滞后特征
- 未来负荷优先使用 `forecast_load_selected.xlsx`
- 未来天气优先尝试 Open-Meteo Forecast API，失败时回退到历史同小时代理

## 3. GUI 启动方式

直接双击：

- `<项目根目录>\启动智能运营分析GUI.bat`

或者命令行运行：

```powershell
cd <项目根目录>
python gui_launcher.py
```

GUI 主要按钮说明：

- `更新数据并全流程`
  先执行 `fetch_power_market_data.py` 更新本地数据，再执行预测、摘要、AI 日报和归档
- `直接全流程`
  不刷新数据，直接基于当前本地数据跑完整链路
- `仅生成 AI 报告`
  跳过预测引擎，直接读取现有结果生成 AI 日报
- `仅运行预测引擎`
  只重新训练并输出建模结果和正式版前瞻预测
- `模型盘点`
  重新盘点本机可用模型与推荐模型
- `停止当前任务`
  停止当前正在运行的命令

## 4. Windows 任务计划创建方式

### 方式 A：双击脚本

直接双击：

- `<项目根目录>\create_windows_task.bat`

它会按默认参数创建一个每日任务：

- 任务名称：`PowerMarketDailyAutomation`
- 默认时间：`06:30`
- 默认模式：`refresh_data`

### 方式 B：PowerShell 自定义

```powershell
cd <项目根目录>
powershell -ExecutionPolicy Bypass -File .\create_windows_task.ps1 -TaskName "PowerMarketDailyAutomation" -RunTime "06:30" -Mode "refresh_data"
```

可选模式：

- `refresh_data`
  每天先更新数据，再跑正式前瞻预测和 AI 日报。推荐。
- `full`
  不刷新数据，直接跑全流程。
- `skip_prediction`
  跳过预测引擎，只生成 AI 报告。

## 5. 命令行入口

### 首次环境配置

1. 复制 `.env.example` 为 `.env`。
2. 在 `.env` 中填写 `DB_PASSWORD` 等本机真实配置。`PJM_SUBSCRIPTION_KEY` 可选；未填写时系统会默认从 Data Miner 2 公开前端配置自动发现 subscription key。
3. 安装依赖：

```powershell
cd <项目根目录>
python -m pip install -r requirements.txt
```

说明：真实密码不保存在 `llm_service_config.yaml` 或 Python 代码中；生产环境仍建议把自有 PJM Key 写入 `.env` 或系统环境变量。未配置 PJM Key 时，数据刷新会尝试自动发现 Data Miner 2 前端公开 key，失败后才降级复用本地/数据库现有数据。

### 全流程

```powershell
cd <项目根目录>
python main_daily_run.py
```

### 先刷新数据再全流程

```powershell
cd <项目根目录>
python main_daily_run.py --refresh-data
```

### 跳过预测，只生成 AI 日报

```powershell
cd <项目根目录>
python main_daily_run.py --skip-prediction
```

### 批处理入口

- `<项目根目录>\run_daily_pipeline.bat`
- `<项目根目录>\run_daily_pipeline_refresh_data.bat`
- `<项目根目录>\run_daily_pipeline_skip_prediction.bat`

## 6. 建议的日常使用方式

推荐直接用 GUI：

1. 打开 `启动智能运营分析GUI.bat`
2. 点击 `更新数据并全流程`
3. 等待日志显示完成
4. 在 GUI 中直接打开 `自动化输出` 或 `结果目录`

推荐的定时任务方式：

1. 用 GUI 或 `create_windows_task.ps1` 创建 `refresh_data` 模式任务
2. 设定为每天 06:30 自动执行
3. 查看输出目录：
   `<项目根目录>\自动化输出\current`
4. 查看结果目录：
   `<项目根目录>\结果-3`

## 7. 常见说明

- 如果正式版天气预报接口暂时不可用，系统会自动切换到历史同小时天气代理，不会中断流程
- 如果未来负荷预测文件缺少个别小时，系统会自动用历史同小时代理补齐
- 任务计划脚本使用 `/F` 强制覆盖同名任务，不会弹确认框
- GUI 和批处理优先使用项目 `.venv\Scripts\python.exe`，不存在时使用 `PATH` 中的 `python`。

## 8. 阶段二工程化更新

- GUI 和计划任务入口不变，仍调用 `main_daily_run.py`；内部已切换为 `services` 服务层调度。
- `01_run_prediction.py` 现在是轻量兼容入口，实际调用 `services.prediction_service.run_prediction()`。
- 预测引擎核心函数已通过 `prediction_engine/` 拆分封装，v4_fix1 保留为兼容主入口。
- 训练后会生成 `model_artifacts/model_<run_id>/` 模型版本目录，用于后续模型注册、加载和回滚。
- 正式前瞻预测表会增加 P10/P90 预测区间字段，帮助判断高峰和尖峰风险范围。
- 数据库结构变更放入 `migrations/`，需要初始化模型追踪表时执行：

```powershell
python -c "from automation_common import load_config; from database_utils import apply_database_migrations; apply_database_migrations(load_config(), log=print)"
```

- 一键启动文件已更新为阶段二版本：`run_daily_pipeline.bat`、`run_daily_pipeline_refresh_data.bat`、`run_daily_pipeline_skip_prediction.bat`、`启动智能运营分析GUI.bat`、`create_windows_task.bat`。

## 9. 阶段三/四新增入口

- `run_model_ops_daily.bat`：每日模型运维入口，执行真实值回填、误差统计、模型健康监控和重训任务登记。
- `run_health_check.bat`：环境健康检查入口，适合在一键启动失败前先运行。
- `run_smoke_test.bat`：轻量整体自检入口，验证配置、关键文件、启动脚本、预测引擎导入和健康检查，不跑完整训练。
- `05_update_actuals_and_errors.py`：只做真实值回填和误差计算。
- `06_model_monitor.py`：完整模型运维检查。
- `07_compare_and_promote_model.py`：候选模型对比和受控上线。
- `09_health_check.py`：命令行健康检查。

计划任务 `Mode` 现在支持：

- `refresh_data`
- `full`
- `skip_prediction`
- `model_ops_daily`
- `health_check`
- `smoke_test`

说明：没有 `.env` 或 `DB_PASSWORD` 时，一键启动不再直接闪退；主流程会进入本地文件模式，窗口会保留错误或完成信息，数据库相关闭环会跳过。

## 10. v2.0.0 现代化桌面控制台

- 新版主入口：`启动智能运营分析GUI.bat`，内部执行 `python -m ui.app`，启动 PySide6 + qfluentwidgets 现代化控制台。
- 旧版 fallback：`启动旧版智能运营分析GUI.bat`，保留原 `gui_launcher.py` 的 Tkinter 入口，便于回退验证。
- 新版 UI 采用深色科技风、左侧导航、顶部状态栏、右侧快速状态面板、底部状态栏和终端风格日志面板。
- 已迁移旧 GUI 的核心动作：更新数据并全流程、直接全流程、仅生成 AI 报告、预测并生成报告、模型盘点、模型诊断检查、健康检查、数据库连接测试、停止当前任务、输出目录保存、打开目录、任务计划创建、数据库浏览/查询。
- 新增数据库闭环同步入口：`08_sync_database_closure.py`，用于在不重新训练完整模型时，把已有核心数据、结果表和未来 24 小时预测追踪记录同步到 MySQL。
- 新增一键入口：`run_daily_pipeline_prediction_report_only.bat`，对应任务计划模式 `prediction_report_only`。
- `run_model_ops_daily.bat` 已更新为先执行数据库闭环同步，再执行真实值/误差回填和模型健康监控。

启动方式：

```powershell
cd <项目根目录>
python -m ui.app
```

快速自检新版 UI：

```powershell
cd <项目根目录>
python -m ui.app --smoke-test
```

计划任务 `Mode` 当前支持：

- `refresh_data`
- `full`
- `skip_prediction`
- `prediction_report_only`
- `model_ops_daily`
- `health_check`
- `smoke_test`

## 11. v2.1.0 模型中心与 AI 报告中心

- 左侧导航新增正式“模型中心”和“AI报告中心”页面，不再只是通用操作入口。
- 模型中心优先读取 `model_registry`、`prediction_tracking`、`model_performance_daily`，展示 Active 模型、模型版本列表、MAE/RMSE/MAPE/R2/高峰 RMSE/尖峰 RMSE、最近误差趋势、artifact 路径、候选模型对比和每日模型运维入口。
- 模型中心在数据库不可用或 `model_registry` 暂无记录时，会从 `model_artifacts/` 与 `自动化输出/current/ai_input_summary.json` 降级展示，不会导致界面崩溃。
- AI 报告中心优先读取 `ai_report_runs`、`ai_input_summary_runs`，展示最新报告状态、历史报告列表、报告预览、Word/JSON 打开入口、重新生成 AI 报告入口和可信检查结果。
- AI 报告中心在数据库不可用时，会从 `自动化输出/current` 与 `全流程预测结果数据存放` 降级读取最新报告。
- 报告可信检查覆盖最高价/最低价时段、风险时段、fallback 生成、关键字段缺失，输出“通过 / 警告 / 失败”。

## 12. v2.2.0 预测结果中心

- 左侧导航新增正式“预测结果中心”，位置在“预测任务”和“模型中心”之间。
- 页面展示未来 24 小时正式前瞻预测摘要、预测表、价格趋势、风险时段、运行批次和本地规则业务解读。
- 数据读取优先级：数据库 `vw_latest_forward_24h_formal` / `result_forward_24h_formal` / `ai_input_summary_runs` / `pipeline_run_events`，数据库不可用时自动降级到 `结果-3`、`自动化输出/current`、`全流程预测结果数据存放` 和 `output` 下的最新正式预测文件。
- 预测表会自动兼容 `predicted_price`、`da_price_pred`、`forecast_price`、`预测电价`、`预测的未来24小时日前电价` 等字段名；P10/P90、温度、模型版本等字段缺失时自动隐藏，不会导致界面崩溃。
- 页面提供刷新、打开预测 Excel、打开结果目录、打开最新归档目录、重新运行预测并生成报告、仅重新生成 AI 报告、导出当前预测表、复制业务摘要等操作。
- 一键启动文件已更新为 v2.2.0：`启动智能运营分析GUI.bat` 会启动包含预测结果中心、模型中心和 AI 报告中心的新版 PySide6 控制台。

## 13. v2.3.0 统一图表与 AI 报告审批流

- 新增 `ui/components/forecast_chart.py` 与 `ui/components/matplotlib_canvas.py`，统一处理深色图表主题、中文字体、负号、图例、坐标轴和 PNG 保存。
- 预测结果中心趋势图改为基于当前页面实际加载的预测表实时渲染，不再依赖占位图；支持最高/最低价注释、Top 风险时段、高峰时段、峰谷价差和 P10/P90 区间。
- 顶部业务摘要压缩为紧凑 KPI 卡片，预测表与趋势图区域重新分配，图表高度提升，避免坐标轴、图例和注释被裁切。
- AI 报告中心新增审批流：待审核、已通过、已驳回、已派发；支持审核人、审核意见、通过报告、驳回报告、标记待审核和派发前检查。
- 新增数据库迁移 `migrations/007_create_ai_report_review_runs.sql`。数据库可用时审批状态写入 `ai_report_review_runs`，不可用时降级保存到 `自动化输出/current/ai_report_review_status.json` 与 `自动化输出/review_status/`。
- 报告派发前会检查审批状态是否已通过、可信检查是否无失败项、Word 报告是否存在；不满足条件时不会直接标记派发。
- 一键启动文件已更新为 v2.3.0。

## 14. v2.4.0 全局自适应布局

- 主窗口默认 `1600x900`、最小 `1280x720`，启动居中，支持最大化和手动缩放。
- 左侧导航升级为分组导航：运行控制、业务分析、系统管理；支持展开/折叠，菜单主体可滚动，底部保留版本、环境和折叠按钮。
- 控制台首页、预测结果中心、模型中心、AI 报告中心统一使用滚动区、响应式网格和 `QSplitter`，在 `1366x768` 下可通过滚动完整查看。
- 预测结果中心保留核心 KPI，数据来源和 `run_id` 放到二级信息行；预测表与趋势图默认 `45% / 55%`，支持拖拽调整，趋势图最小高度提升。
- AI 报告中心的工具栏和审批按钮改为响应式换行，历史列表、报告预览、可信检查使用三栏 `QSplitter`。
- 控制台首页右侧快速状态、运行模式说明、运行日志改为垂直 `QSplitter`，日志区域可获得更多空间。
- 一键启动文件已更新为 v2.4.0。

## 15. v2.4.1 数据刷新与数据库闭环容错

- main_daily_run.py --refresh-data 在未配置 PJM_SUBSCRIPTION_KEY 时不再直接中断；服务层会记录 WARNING，并降级复用本地/数据库现有数据继续全流程。
- orecast_load_selected.xlsx 如果为空文件，会优先从 orecast_load_raw.xlsx 自动重建，避免预测输入导出和数据库闭环失败。
- 数据库闭环同步新增 Excel 安全读取：遇到 0 字节、损坏或无法识别格式的 Excel 时记录 WARNING 并跳过该文件，不再导致整条同步任务退出。
- etch_power_market_data.py 直接运行时同样支持缺少 PJM Key 的本地降级同步。
- 所有一键启动 bat 已更新为 v2.4.1，并继续使用 UTF-8、CRLF 和失败保留窗口策略。

## 16. v2.5.0 快速预测与模型自学习闭环

- 新增日常快速预测模式：`python main_daily_run.py --fast-forecast`，加载 `model_registry` 中的 Active 模型和 `model_artifacts/model_<run_id>`，不重新训练。
- 新增刷新数据 + 快速预测：`python main_daily_run.py --refresh-data --fast-forecast`，先刷新/降级同步数据，再加载 Active 模型推理。
- 新增完整重训模式：`python main_daily_run.py --retrain-model`，保留旧完整训练能力，训练后保存 candidate artifact 并登记 `model_registry`。
- 新增模型自优化模式：`python main_daily_run.py --model-auto-optimize`，执行真实值回填、误差记忆更新、退化判断，必要时才触发候选重训和对比上线。
- 快速预测输出新增字段：`raw_predicted_price`、`bias_adjustment`、`corrected_predicted_price`、`predicted_price`、`correction_reason`、`model_version`、`feature_version`。
- 新增模型自学习记忆表：`model_error_memory` 和 `model_strategy_memory`。样本不足时不会强行校正，默认至少 10 个同类场景样本才启用偏差修正。
- 新增一键启动脚本：
  - `run_daily_pipeline_fast_forecast.bat`
  - `run_daily_pipeline_refresh_fast_forecast.bat`
  - `run_daily_pipeline_retrain_model.bat`
  - `run_model_auto_optimize.bat`
- `create_windows_task.ps1` 的 `Mode` 新增：`fast_forecast`、`refresh_fast_forecast`、`retrain_model`、`model_auto_optimize`。
- 模型中心新增 Active 可用性、Artifact 完整性、快速预测可用、误差记忆、自学习状态、偏差校正开关、自动优化和最新候选设为 Active 操作。
- 快速预测落库只同步正式预测结果、预测输入特征和业务摘要，避免日常推理重复写入历史训练大表。

## 17. v2.5.1 PJM 数据刷新更新

- `fetch_power_market_data.py` 新增 Data Miner 2 subscription key 自动发现：优先使用 `.env` / 系统环境变量中的 `PJM_SUBSCRIPTION_KEY`，未配置时读取 `https://dataminer2.pjm.com/config/settings.json` 中公开的 `subscriptionKey`。
- `services/data_service.py` 不再因为本地未配置 `PJM_SUBSCRIPTION_KEY` 提前跳过外部刷新，而是先尝试真实刷新，只有刷新失败时才降级复用本地/数据库现有数据。
- 新增配置项：`PJM_AUTO_DISCOVER_SUBSCRIPTION_KEY`、`PJM_SETTINGS_URL`，可在 `.env` 中关闭或替换自动发现地址。
- 一键启动脚本已更新为 v2.5.1。日常推荐继续使用 `run_daily_pipeline_refresh_fast_forecast.bat` 执行“刷新数据 + 快速预测”。

## 18. v2.6.0 Web 产品化二次优化

- 新增本地 Web 平台：`run_web_platform.bat` 会同时启动 FastAPI 后端和 React/Ant Design 前端。
- 后端入口：`backend/app/main.py`，API 文档访问 `http://127.0.0.1:8000/docs`。
- 前端入口：`frontend/`，开发访问 `http://127.0.0.1:5173`。
- 新增页面能力：首页驾驶舱、数据接入、预测分析、交易策略建议、AI 分析助手、异常解释、AI 报告中心、模型监控和任务日志。
- 新增数据库迁移：`migrations/009_create_web_platform_tables.sql`，包含 `analysis_runs`、`strategy_advice`、`ai_chat_sessions`、`ai_chat_messages`、`anomaly_explanations`、`report_reviews`。
- 新增一键脚本：`run_web_backend.bat`、`run_web_frontend.bat`、`run_web_platform.bat`、`run_web_smoke_test.bat`。
- 现有预测模型不重写，Web 版通过 API 复用当前数据刷新、快速预测、AI 报告、模型运维和数据库闭环能力。

## 19. v2.6.1 Web 交互与启动稳定性优化

- `run_web_platform.bat` 支持端口检测和已有服务复用，重复双击不再导致启动失败。
- Web 界面新增全局可拖动 AI 助手、预测 AI 解读、数据源官网展示、定时任务新增/删除管理。
- 优化左侧导航、整体字号、模型监控布局和任务日志管理区。

## 20. v2.6.3 AI 问答助手与报告中心修复

- 新增 `run_project.bat` 统一核心启动入口，整合 Web 平台、每日刷新预测、健康检查、模型自优化、Web 自检和桌面 GUI。
- AI 分析助手新增 `backend/app/ai/` 受控工具链，支持 forecast_extreme、risk_hours、hour_explain、strategy_advice、storage_advice、model_status、report_summary、data_status 等核心意图。
- `/api/ai/chat` 返回 `intent`、`evidence`、`tool_calls` 和 `related_actions`，回答必须基于系统工具数据，避免固定模板式答非所问。
- 前端问答输入框改为原生多行输入，回答展示数据依据折叠卡片和页面跳转按钮。
- AI 报告中心修复操作建议文本竖排显示问题，报告摘要继续保持面向非技术人员的结构化阅读方式。

## 21. v2.7.0 第一阶段 AI 智能问答落地

- 按两阶段落地文档完成第一阶段：标准预测接口、Dify 可选桥接、本地千问模型网关、电力知识库和问答日志/反馈能力。
- 新增 `/api/prediction/latest`、`/api/prediction/detail`、`/api/market/history`、`/api/weather/forecast`、`/api/load/forecast`、`/api/renewable/forecast`、`/api/model/explain`、`/api/risk/level`。
- AI 助手扩展 forecast_overview、factor_analysis、load_analysis、renewable_analysis 等意图，可回答文档验收问题并在数据不足时明确说明限制。
- Web 聊天窗口新增历史、复制、清空、评分、数据使用标签、建议关注和 Trace 展示；所有一键启动脚本版本同步到 v2.7.0。

## 22. v2.7.1 AI 助手交互与数据表查看修复

- 修复 AI 助手输入后重复发送的问题，增加请求锁、发送防抖和按键重复拦截。
- 修复中文输入法候选确认容易触发发送的问题，支持逐字逐字符输入和中英文混合输入。
- 新增天气查询意图，普通天气问题直接返回天气数据口径；涉及“天气影响电价”时再进入电价因素分析。
- 优化 Web 自适应布局和 AI 抽屉高度，避免底部输入区或内容显示不完全。
- 数据接入中心新增数据库表列表、表名筛选、表内容预览和内容筛选功能；一键启动脚本同步到 v2.7.1。

## 23. v2.9.1 LangGraph 多 Agent 分析落地

- 新增 `backend/langgraph_agent/` 第二阶段 Agent 模块，包含意图识别、数据查询、预测分析、风险判断、报告整合和答案整合节点。
- 新增 `/api/ai/agent/analyze` 复杂分析接口，返回 `workflow`、`agent_trace`、`data_used`、`risk_level`、`focus_periods` 和模型调用状态。
- `/api/ai/chat` 已接入第二阶段工作流，复杂业务问题会联合预测、负荷、天气、历史价格、模型解释、风险和知识库数据回答。
- 本地千问模型可用时参与最终答案整合；模型未连接时自动使用多 Agent 工具链兜底，避免固定模板答非所问。
- Web AI 助手新增 Agent 工作流标签和模型状态提示；所有一键启动脚本同步到 v2.9.1。


