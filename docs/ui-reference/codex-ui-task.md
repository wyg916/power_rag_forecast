# codex-ui-task.md

# Codex UI 落地开发任务书

## 1. 任务目标

请基于当前 React + TypeScript + Vite + Ant Design 项目，将前端界面重构为“浅绿色新能源 AI 售电交易决策平台”。

本任务优先完成 UI 骨架、页面结构、Mock 数据和通用组件。后端接口可以后续逐步替换，首版不要求所有真实接口联通。

## 2. 输入资料

请优先参考以下资料：

```text
docs/ui-reference/
├── images/
│   ├── 00_info_architecture.png
│   ├── 01_dashboard.png
│   ├── 02_data_center.png
│   ├── 03_forecast_center.png
│   ├── 04_strategy_center.png
│   ├── 05_ai_assistant.png
│   ├── 06_report_center.png
│   ├── 07_model_center.png
│   ├── 08_knowledge_base.png
│   ├── 09_task_center.png
│   └── 10_settings.png
├── theme-spec.md
├── page-spec.md
├── assets-list.md
└── codex-ui-task.md
```

如果部分图片素材不存在，请先使用占位图、图标或 Mock 区块实现，不要阻塞页面开发。

## 3. 技术要求

必须保留：

- React
- TypeScript
- Vite
- Ant Design
- ECharts

允许使用：

- lucide-react
- @ant-design/icons
- echarts-for-react
- dayjs

不建议引入：

- 新的重型 UI 框架
- 大量动画库
- 复杂 3D 引擎
- 影响构建速度的过重依赖

## 4. 前端目录结构

请按以下结构整理：

```text
frontend/src/
├── app/
│   ├── App.tsx
│   ├── router.tsx
│   └── providers.tsx
├── layout/
│   ├── BasicLayout.tsx
│   ├── Sidebar.tsx
│   ├── HeaderBar.tsx
│   └── PageContainer.tsx
├── pages/
│   ├── dashboard/
│   │   └── DashboardPage.tsx
│   ├── data/
│   │   └── DataCenterPage.tsx
│   ├── forecast/
│   │   └── ForecastCenterPage.tsx
│   ├── strategy/
│   │   └── StrategyCenterPage.tsx
│   ├── assistant/
│   │   └── AssistantPage.tsx
│   ├── report/
│   │   └── ReportCenterPage.tsx
│   ├── model/
│   │   └── ModelCenterPage.tsx
│   ├── knowledge/
│   │   └── KnowledgeBasePage.tsx
│   ├── task/
│   │   └── TaskCenterPage.tsx
│   └── settings/
│       └── SettingsPage.tsx
├── components/
│   ├── cards/
│   ├── charts/
│   ├── common/
│   ├── status/
│   └── tables/
├── services/
│   ├── dashboardApi.ts
│   ├── dataApi.ts
│   ├── forecastApi.ts
│   ├── strategyApi.ts
│   ├── assistantApi.ts
│   ├── reportApi.ts
│   ├── modelApi.ts
│   ├── knowledgeApi.ts
│   └── taskApi.ts
├── mock/
│   ├── dashboardMock.ts
│   ├── dataMock.ts
│   ├── forecastMock.ts
│   ├── strategyMock.ts
│   ├── assistantMock.ts
│   ├── reportMock.ts
│   ├── modelMock.ts
│   ├── knowledgeMock.ts
│   ├── taskMock.ts
│   └── settingsMock.ts
├── theme/
│   ├── themeConfig.ts
│   └── variables.css
├── types/
├── utils/
└── assets/
```

## 5. 统一布局任务

请先实现统一布局，不要直接开发单页。

### 5.1 BasicLayout

要求：

- 左侧导航栏
- 顶部状态栏
- 内容区
- 支持菜单收起
- 支持页面内容滚动

尺寸：

```text
左侧展开宽度：220px
左侧收起宽度：72px
顶部栏高度：64px
内容区 padding：24px
```

### 5.2 Sidebar

一级菜单：

```text
首页
数据中心
预测中心
策略中心
AI助手
报告中心
模型中心
知识库
任务中心
系统设置
```

要求：

- 当前菜单高亮
- 二级菜单展开
- 支持收起
- 图标统一
- 选中项使用主绿色

### 5.3 HeaderBar

展示：

- 项目选择
- 数据时间
- 当前地区
- 模型版本
- 通知
- 帮助
- 用户头像

## 6. 主题配置任务

请创建 `theme/themeConfig.ts`，使用 Ant Design ConfigProvider 注入主题。

主题必须包含：

```text
主色：#00B894
主色深色：#008F72
主色浅色：#E6F7F1
页面背景：#F7F9FC
卡片背景：#FFFFFF
边框色：#E5EAF0
风险红：#FF4D4F
告警橙：#FAAD14
信息蓝：#1677FF
```

请同步创建 `theme/variables.css`，将核心颜色注册为 CSS 变量。

## 7. 通用组件任务

请优先抽取通用组件：

```text
MetricCard
SectionCard
StatusTag
RiskAlertCard
PageHeaderFilters
ForecastCurveChart
TrendLineChart
TaskLogTable
ReportPreviewCard
TracePanel
```

### 7.1 MetricCard

用于首页、数据中心、预测中心、模型中心等顶部指标。

字段：

```ts
title: string
value: string | number
unit?: string
icon?: ReactNode
trend?: number
trendLabel?: string
status?: 'success' | 'warning' | 'danger' | 'info'
```

### 7.2 SectionCard

统一卡片容器。

字段：

```ts
title: string
extra?: ReactNode
children: ReactNode
```

### 7.3 StatusTag

统一状态标签。

支持状态：

```text
success
running
warning
danger
offline
pending
published
rejected
```

### 7.4 TracePanel

用于 AI 助手右侧展示。

内容：

- 识别意图
- 调用工具
- 数据来源
- 知识库引用
- Trace ID
- 可信度

## 8. 页面开发顺序

请严格按阶段执行。

### 阶段 1：UI 骨架

任务：

1. 创建统一 Layout。
2. 创建主题配置。
3. 创建 10 个空页面。
4. 配置路由。
5. 实现左侧菜单跳转。
6. 运行构建。

验收：

- 所有页面能打开。
- 菜单高亮正常。
- 主题生效。
- `npm run build` 通过。

### 阶段 2：首页 Dashboard

任务：

1. 顶部 6 个指标卡。
2. 中部能源系统主视觉区。
3. 24小时电价趋势图。
4. 储能充放电建议。
5. 风险预警。
6. 最新报告。
7. 任务日志。

说明：

- 首页 3D 主视觉图可以先用 `assets/hero/energy-scene-placeholder.svg` 占位。
- 不要等待正式图片。

### 阶段 3：数据中心 + 预测中心

数据中心任务：

1. 数据源指标卡。
2. 数据接入流程。
3. 数据质量图表。
4. 数据库表浏览。
5. 导入导出记录。

预测中心任务：

1. 筛选区。
2. 指标卡。
3. 24小时预测曲线。
4. 历史对比。
5. 峰谷分析。
6. 预测明细表。

### 阶段 4：策略中心 + AI助手

策略中心任务：

1. 策略指标卡。
2. 策略时间轴。
3. 储能充放电建议表。
4. 风险分级卡片。
5. 人工复核清单。
6. 右侧策略说明面板。

AI助手任务：

1. 会话历史。
2. 常用问题。
3. 对话窗口。
4. 工具调用面板。
5. 数据来源。
6. 知识库引用。
7. Trace ID。
8. 可信度。

### 阶段 5：报告中心 + 模型中心 + 知识库

报告中心任务：

1. 报告统计卡。
2. 报告列表。
3. 报告预览。
4. 审核操作。
5. 发布记录。

模型中心任务：

1. 模型指标卡。
2. 模型对比表。
3. 误差趋势图。
4. 预测效果对比图。
5. 模型详情。
6. 回滚操作。

知识库任务：

1. 文档指标卡。
2. 文档分类树。
3. 文档列表。
4. 检索测试。
5. 检索结果。
6. AI 整理答案。

### 阶段 6：任务中心 + 系统设置

任务中心任务：

1. 任务统计卡。
2. 任务调度表。
3. 失败重试队列。
4. 运行日志表。
5. 监控告警列表。

系统设置任务：

1. 用户管理。
2. 权限矩阵。
3. 参数配置。
4. 接口配置。
5. 模型端点配置。
6. 数据源配置。
7. 通知配置。
8. 系统健康信息。

## 9. Mock 数据要求

所有页面首版使用 Mock 数据。

Mock 文件放在：

```text
frontend/src/mock/
```

每个页面必须有单独 Mock 文件，避免全部堆在一个文件中。

要求：

- 字段名尽量贴近真实后端。
- 数值保持业务合理。
- 图表数据长度合理。
- 表格数据不少于 5 条。
- 状态覆盖成功、运行中、失败、告警等情况。

## 10. 服务层要求

每个页面都需要预留 services 文件。

例如：

```ts
// frontend/src/services/forecastApi.ts
import { forecastMock } from '@/mock/forecastMock';

export async function getForecastSummary() {
  return Promise.resolve(forecastMock.summary);
}
```

后续替换真实接口时，只改 services，不改页面组件。

## 11. 图表要求

全部图表使用 ECharts。

至少实现：

- 24小时电价预测曲线
- 历史对比曲线
- 峰谷分析图
- 模型误差趋势图
- 预测效果对比图
- 数据质量趋势图
- 任务统计图

图表需遵守主题色规范。

## 12. 代码质量要求

1. 不要把所有页面写进 `main.tsx`。
2. 页面代码超过 400 行时需要拆组件。
3. 类型定义必须放在 `types` 目录。
4. Mock 数据必须和页面分离。
5. 样式尽量复用主题变量。
6. 不要写死大量颜色。
7. 所有页面必须通过 TypeScript 检查。
8. 不要删除现有业务逻辑。
9. 不要破坏已有 API 调用。
10. 完成后运行 `npm run build`。

## 13. 验收标准

最终交付需满足：

1. 10 个页面全部可访问。
2. 侧边栏和顶部栏统一。
3. 主题风格统一。
4. 首页有明显新能源视觉主区。
5. 预测中心有可用电价曲线。
6. AI 助手有三栏布局和 Trace 面板。
7. 知识库有检索测试区。
8. 任务中心有调度和日志。
9. 系统设置有权限矩阵和配置卡片。
10. `npm run build` 成功。

## 14. 迭代建议

不要一次性开发所有细节。

推荐顺序：

```text
Layout + Theme
→ 首页
→ 数据中心 + 预测中心
→ 策略中心 + AI助手
→ 报告中心 + 模型中心 + 知识库
→ 任务中心 + 系统设置
→ 接口联调
→ 视觉细节优化
```
