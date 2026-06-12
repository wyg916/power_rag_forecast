# 售电交易 AI 辅助决策平台 Web 版说明

版本：v2.9.1

本次二次优化在原有预测、AI 报告、MySQL 闭环和模型运维基础上新增本地 Web 产品化能力：

- FastAPI 后端：`backend/app/main.py`
- React + Vite + TypeScript + Ant Design 前端：`frontend/`
- Web 任务调度、预测结果、策略建议、AI 问答、异常解释、AI 报告、报告审核、模型监控接口
- v2.6.3 新增：AI 问答助手按“意图识别 + 工具调用 + 数据依据 + Answer Guard”落地，修复报告中心操作建议竖排显示，输入框改为稳定原生多行输入
- v2.7.0 新增：第一阶段标准预测接口、Dify 可选接入、本地千问模型网关、电力知识库、问答反馈和前端复制/历史/清空/评分能力
- v2.7.1 新增：AI 助手输入防重复发送、中文输入法友好处理、天气查询意图、响应式抽屉布局、数据库表浏览和内容筛选
- 上一版新增：第二阶段 LangGraph 多 Agent 工作流、`/api/ai/agent/analyze` 复杂分析接口、AI 助手工作流可追踪展示和本地模型不可用兜底
- v2.9.1 新增：AI 问答链路重构，覆盖细粒度 intent、上下文记忆、确定性工具、Ollama/qwen3 本地模型总结、增强兜底模板、Answer Guard、Trace、问答反馈和 QA 测试集；数据库表查看增加连接错误提示，一键启动会自动启动并预热 Ollama qwen3。
- 数据库迁移：`migrations/009_create_web_platform_tables.sql`、`migrations/010_create_ai_assistant_tables.sql`、`migrations/011_create_ai_chat_feedback.sql`、`migrations/012_ai_assistant_accuracy_tables.sql`
- Docker/Nginx 轻量部署文件

## 本地启动

推荐双击统一入口：

```text
run_project.bat
```

只启动 Web 平台时也可以双击：

```text
run_web_platform.bat
```

也可以分开启动：

```powershell
python -X utf8 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
cd frontend
npm install
npm run dev
```

访问：

- 前端：http://127.0.0.1:5173
- API 文档：http://127.0.0.1:8000/docs

## 能力范围

第一版 Web 平台优先复用现有本地能力，不重写预测模型：

- 首页驾驶舱读取最新预测、报告、模型和数据状态
- 数据接入中心展示 `output/` 下核心数据源状态
- 预测分析中心展示未来 24 小时曲线和明细
- 策略建议中心基于 P25/P75、尖峰概率、高峰负荷生成可追溯建议
- AI 助手基于当前系统数据回答最高价、低价窗口、风险时段、小时解释、交易策略、储能建议、模型误差、日报摘要和数据状态，并展示可追溯数据依据
- 第一阶段标准接口包括 `/api/prediction/latest`、`/api/prediction/detail`、`/api/market/history`、`/api/weather/forecast`、`/api/load/forecast`、`/api/renewable/forecast`、`/api/model/explain` 和 `/api/risk/level`
- 数据接入中心支持数据库表列表、表名筛选、单表数据预览和当前表内容筛选
- 异常解释中心为高价、高风险、高峰负荷时段生成解释和建议
- 报告中心支持下载、通过、驳回、发布
- 模型监控展示 Active 模型、版本列表、误差趋势和重训建议
- 任务日志页面可以启动今日分析、预测、报告、健康检查和模型自优化
- 任务日志页面可以新增、刷新、删除当前项目相关 Windows 定时任务

## 核心启动入口

日常只建议使用以下少量入口：

- `run_project.bat`：统一菜单入口，覆盖 Web、每日刷新预测、健康检查、模型自优化、Web 自检和桌面 GUI。
- `run_web_platform.bat`：直接启动 Web 平台。
- `run_web_smoke_test.bat`：快速验证 Web 后端接口。

其他 `run_*.bat` 保留给 Windows 计划任务、历史兼容和高级调试，不再建议日常逐个双击。

## 说明

服务器部署建议先使用轻量模式：展示已有预测结果、报告样例、策略建议和 AI 问答，不建议在低配服务器直接跑完整训练、大规模数据刷新或本地大模型推理。


