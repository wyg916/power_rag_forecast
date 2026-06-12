# assets-list.md

# AI售电交易决策平台 UI 素材清单

## 1. 素材准备原则

本项目不需要一开始准备全部素材图片。首版 UI 可以先使用占位图、Ant Design 图标、lucide-react 图标和 ECharts 图表完成。

必须准备的是：

- Logo
- UI 参考图
- 主题规范
- 页面说明
- Mock 数据

建议准备的是：

- 首页 3D 能源主视觉图
- 空状态插画
- 默认头像
- 报告图标

可以后补的是：

- 文档封面
- 告警插画
- 装饰背景
- 更多设备插画

## 2. 推荐目录结构

```text
frontend/src/assets/
├── logo/
│   ├── logo.svg
│   ├── logo-mini.svg
│   └── logo-dark.svg
├── hero/
│   ├── energy-3d-scene.png
│   ├── energy-3d-scene-placeholder.svg
│   └── grid-line-bg.svg
├── icons/
│   ├── menu/
│   ├── status/
│   └── file-types/
├── illustrations/
│   ├── empty-data.svg
│   ├── empty-report.svg
│   ├── empty-task.svg
│   ├── empty-knowledge.svg
│   └── system-error.svg
├── avatars/
│   └── default-avatar.png
└── backgrounds/
    ├── page-watermark.svg
    └── card-gradient.svg
```

## 3. 必须准备素材

### 3.1 Logo

文件：

```text
frontend/src/assets/logo/logo.svg
frontend/src/assets/logo/logo-mini.svg
```

建议风格：

- 绿色
- 闪电 / 叶子 / 电网节点 / AI 符号
- 简洁、扁平、适合侧边栏

用途：

- 左上角平台标识
- 浏览器标题图标
- 登录页或后续品牌页

没有正式 Logo 时，可临时使用 lucide-react 的 `Zap`、`Leaf`、`Network` 图标组合。

### 3.2 UI 参考图

文件目录：

```text
docs/ui-reference/images/
```

建议命名：

```text
00_info_architecture.png
01_dashboard.png
02_data_center.png
03_forecast_center.png
04_strategy_center.png
05_ai_assistant.png
06_report_center.png
07_model_center.png
08_knowledge_base.png
09_task_center.png
10_settings.png
```

用途：

- 给 Codex 参考页面结构
- 给设计和开发统一风格
- 给后续版本迭代做对照

## 4. 首页主视觉素材

### 4.1 正式图

文件：

```text
frontend/src/assets/hero/energy-3d-scene.png
```

画面要求：

- 浅色 3D 风格
- 包含光伏电站、储能柜、电网节点
- 白色或透明背景
- 绿色流光线路
- 不要带文字
- 不要带按钮
- 横向构图
- 主体偏中间或偏右
- 左侧可留出指标浮层空间

建议比例：

```text
16:6 或 16:7
推荐尺寸：1600 x 600
最小尺寸：1200 x 450
```

### 4.2 占位图

文件：

```text
frontend/src/assets/hero/energy-3d-scene-placeholder.svg
```

如果没有正式 3D 图，先做：

- 浅绿色渐变背景
- 光伏图标
- 储能柜图标
- 电网塔图标
- 绿色连线
- 简单浮层卡片

开发阶段不要因为没有正式主视觉图而停工。

## 5. 图标素材

### 5.1 菜单图标

推荐直接使用图标库，不建议单独准备图片。

菜单映射：

| 菜单 | 推荐图标含义 |
|---|---|
| 首页 | Home |
| 数据中心 | Database |
| 预测中心 | TrendingUp |
| 策略中心 | ShieldCheck |
| AI助手 | Bot |
| 报告中心 | FileText |
| 模型中心 | Box / Cube |
| 知识库 | BookOpen |
| 任务中心 | ClipboardCheck |
| 系统设置 | Settings |

推荐库：

- lucide-react
- @ant-design/icons

### 5.2 状态图标

状态图标建议：

| 状态 | 图标含义 |
|---|---|
| 成功 | CheckCircle |
| 运行中 | PlayCircle |
| 告警 | AlertTriangle |
| 失败 | XCircle |
| 等待 | Clock |
| 离线 | CircleOff |
| AI | Bot |
| 工具调用 | Wrench |

## 6. 空状态插画

建议文件：

```text
frontend/src/assets/illustrations/empty-data.svg
frontend/src/assets/illustrations/empty-report.svg
frontend/src/assets/illustrations/empty-task.svg
frontend/src/assets/illustrations/empty-knowledge.svg
frontend/src/assets/illustrations/system-error.svg
```

使用场景：

- 暂无数据
- 暂无报告
- 暂无任务
- 暂无知识库文档
- 系统异常

首版可直接使用 Ant Design `Empty` 组件，不必须准备插画。

## 7. 用户头像

建议文件：

```text
frontend/src/assets/avatars/default-avatar.png
```

要求：

- 圆形显示
- 中性风格
- 不使用真人敏感照片
- 适合后台右上角用户区域

首版可用 Ant Design Avatar 的文字头像。

## 8. 文件类型图标

知识库和报告中心建议支持文件类型图标。

建议图标类型：

```text
PDF
DOCX
XLSX
CSV
JSON
MD
SQL
```

可以使用：

- Ant Design 图标
- lucide-react 图标
- CSS 彩色 Tag

不必须准备独立图片。

## 9. 页面背景素材

可选文件：

```text
frontend/src/assets/backgrounds/page-watermark.svg
frontend/src/assets/backgrounds/card-gradient.svg
```

建议风格：

- 浅绿色波纹
- 低透明度
- 不影响文字阅读
- 只用于首页或空状态区域

不要使用大面积复杂背景，以免降低企业后台可读性。

## 10. 图表数据不是素材图片

以下内容不要做成图片：

- 电价预测曲线
- 模型误差趋势
- 峰谷分析
- 数据质量趋势
- 任务运行统计

这些必须由 ECharts 动态渲染，不能用静态图片代替。

## 11. 报告缩略图

报告中心可以先不用真实缩略图。

首版用：

- 文件图标
- 报告类型 Tag
- 状态 Tag

后续可扩展报告封面图。

## 12. 需要交给 Codex 的素材包

建议组织为：

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
├── codex-ui-task.md
└── assets-list.md
```

如果只有部分图片，也可以先交付：

```text
00_info_architecture.png
01_dashboard.png
03_forecast_center.png
05_ai_assistant.png
theme-spec.md
page-spec.md
codex-ui-task.md
assets-list.md
```

## 13. 素材优先级

### P0 必须

- Logo 占位
- UI 参考图
- 主题规范
- 页面功能说明
- Mock 数据

### P1 建议

- 首页能源 3D 主视觉
- 默认头像
- 空状态插画
- 文件类型图标

### P2 可后补

- 报告封面
- 告警插画
- 背景装饰
- 细分设备插画

## 14. 给 Codex 的素材处理要求

请让 Codex 遵循：

1. 如果素材不存在，使用占位图或图标。
2. 不要因为缺少图片阻塞页面开发。
3. 所有图片引用必须集中在 `assets` 目录。
4. 不要使用外链图片。
5. 不要使用带版权风险的网络图片。
6. 图表必须用 ECharts 动态绘制。
7. 首页 3D 图后续可替换，组件结构要预留。
