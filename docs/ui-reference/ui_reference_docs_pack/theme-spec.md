# theme-spec.md

# AI售电交易决策平台 UI 主题规范

## 1. 设计定位

本项目 UI 采用“浅绿色新能源企业后台”风格，适用于电价预测、售电交易辅助、AI 决策分析、模型监控、知识库和任务调度等 B 端业务场景。

整体目标不是做成炫酷展示大屏，而是做成一个可长期办公使用、信息密度较高、交互清晰、便于维护的企业级 Web 后台。

核心关键词：

- 新能源
- 绿色电力
- 智能决策
- 数据运营
- AI 助手
- 企业后台
- 清爽、克制、专业

## 2. 技术适配

前端技术栈：

- React
- TypeScript
- Vite
- Ant Design
- ECharts
- lucide-react 或 @ant-design/icons

主题应优先通过 Ant Design `ConfigProvider` 和全局 CSS 变量实现，避免在页面内大量写死颜色。

建议创建：

```text
frontend/src/theme/themeConfig.ts
frontend/src/theme/variables.css
```

## 3. 品牌主色

| 用途 | 颜色值 |
|---|---|
| 主绿色 | #00B894 |
| 主绿色深色 | #008F72 |
| 主绿色浅色 | #E6F7F1 |
| 青绿色辅助 | #12C99B |
| 墨绿色 | #063A3A |

主绿色用于：

- 主按钮
- 当前菜单高亮
- 关键正向指标
- 成功状态
- 低价机会窗口
- 新能源主题强调

墨绿色用于：

- Logo 文字
- 强标题
- 左侧深色模式扩展
- 部分图标强调

## 4. 页面背景与卡片

| 用途 | 颜色值 |
|---|---|
| 页面背景 | #F7F9FC |
| 一级卡片背景 | #FFFFFF |
| 二级浅绿背景 | #F0FFFA |
| 浅灰蓝背景 | #F3F7FB |
| 分割线/边框 | #E5EAF0 |
| 弱边框 | #EEF2F6 |

页面使用浅灰背景，所有模块尽量放入白色卡片中。

页面背景不建议使用纯白，否则层次感不够。卡片背景使用白色，配合轻阴影和圆角。

## 5. 文字颜色

| 层级 | 颜色值 |
|---|---|
| 一级标题 | #111827 |
| 二级标题 | #1F2937 |
| 正文 | #374151 |
| 辅助文字 | #6B7280 |
| 弱提示 | #9CA3AF |
| 反白文字 | #FFFFFF |

建议字号：

| 场景 | 字号 |
|---|---:|
| 页面标题 | 24px |
| 区块标题 | 18px |
| 卡片标题 | 16px |
| 正文 | 14px |
| 辅助说明 | 12px |
| 大数字指标 | 28px - 36px |

## 6. 状态色

| 状态 | 颜色值 | 用途 |
|---|---|---|
| 成功/正常 | #00B894 | 成功、在线、健康 |
| 信息 | #1677FF | 信息提示、普通状态 |
| 告警 | #FAAD14 | 中风险、待处理 |
| 风险/失败 | #FF4D4F | 高风险、失败、故障 |
| 离线/禁用 | #94A3B8 | 离线、无效、禁用 |
| 紫色强调 | #7C3AED | 模型、AI、特殊指标 |

业务映射：

- 低价窗口：绿色
- 高价风险：红色或浅红背景
- 人工复核：橙色
- 模型正常：绿色
- 模型退化：橙色
- 任务失败：红色
- 系统通知：蓝色
- AI/模型能力：紫色或青绿色

## 7. 图表颜色

| 图表元素 | 颜色值 |
|---|---|
| 预测电价线 | #00B894 |
| 实际电价线 | #3B82F6 |
| 均价线 | #94A3B8 |
| 高价风险区背景 | rgba(255, 77, 79, 0.12) |
| 低价窗口背景 | rgba(0, 184, 148, 0.12) |
| 储能充电 | #10B981 |
| 储能放电 | #F97316 |
| 置信区间 | rgba(59, 130, 246, 0.12) |
| 预测误差柱 | rgba(0, 184, 148, 0.35) |

图表原则：

- 电价预测曲线使用绿色主线。
- 实际值或对比线使用蓝色或灰色虚线。
- 高价风险区域用浅红色背景，不要用大面积纯红。
- 低价机会区域用浅绿色背景。
- 置信区间使用浅蓝或浅绿色透明区域。

## 8. 圆角、阴影、间距

| 属性 | 建议值 |
|---|---:|
| 卡片圆角 | 16px |
| 按钮圆角 | 8px |
| 输入框圆角 | 8px |
| Modal 圆角 | 16px |
| 页面 Padding | 24px |
| 卡片 Padding | 20px - 24px |
| 栅格间距 | 16px - 24px |
| 表格行高 | 48px |

推荐卡片阴影：

```css
box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
border: 1px solid rgba(15, 23, 42, 0.04);
```

## 9. Ant Design 主题配置示例

```ts
// frontend/src/theme/themeConfig.ts
import type { ThemeConfig } from 'antd';

export const themeConfig: ThemeConfig = {
  token: {
    colorPrimary: '#00B894',
    colorSuccess: '#00B894',
    colorWarning: '#FAAD14',
    colorError: '#FF4D4F',
    colorInfo: '#1677FF',
    colorText: '#1F2937',
    colorTextSecondary: '#6B7280',
    colorBorder: '#E5EAF0',
    colorBgLayout: '#F7F9FC',
    colorBgContainer: '#FFFFFF',
    borderRadius: 12,
    borderRadiusLG: 16,
    fontSize: 14,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
  },
  components: {
    Layout: {
      bodyBg: '#F7F9FC',
      headerBg: '#FFFFFF',
      siderBg: '#FFFFFF',
    },
    Menu: {
      itemSelectedBg: '#E6F7F1',
      itemSelectedColor: '#008F72',
      itemHoverColor: '#008F72',
      itemBorderRadius: 10,
    },
    Card: {
      borderRadiusLG: 16,
      paddingLG: 24,
    },
    Button: {
      borderRadius: 8,
      controlHeight: 36,
    },
    Table: {
      headerBg: '#F8FAFC',
      rowHoverBg: '#F0FFFA',
      borderColor: '#E5EAF0',
    },
    Tag: {
      borderRadiusSM: 8,
    },
  },
};
```

## 10. 全局 CSS 变量建议

```css
:root {
  --color-primary: #00B894;
  --color-primary-dark: #008F72;
  --color-primary-light: #E6F7F1;
  --color-bg-page: #F7F9FC;
  --color-bg-card: #FFFFFF;
  --color-border: #E5EAF0;
  --color-text-title: #111827;
  --color-text-main: #374151;
  --color-text-secondary: #6B7280;
  --color-success: #00B894;
  --color-warning: #FAAD14;
  --color-danger: #FF4D4F;
  --color-info: #1677FF;
  --radius-card: 16px;
  --radius-button: 8px;
  --shadow-card: 0 8px 24px rgba(15, 23, 42, 0.06);
}
```

## 11. 页面布局规范

| 区域 | 建议尺寸 |
|---|---:|
| 左侧菜单展开宽度 | 220px |
| 左侧菜单收起宽度 | 72px |
| 顶部栏高度 | 64px |
| 内容区 Padding | 24px |
| 页面最小适配宽度 | 1366px |
| 推荐设计宽度 | 1440px / 1920px |

所有页面均采用统一布局：

```text
BasicLayout
├── Sidebar
├── HeaderBar
└── PageContainer
```

## 12. 组件视觉规范

### 指标卡 MetricCard

- 左侧图标圆角背景
- 中间展示指标名称和数值
- 下方展示环比、同比或补充说明
- 正向变化用绿色
- 风险变化用红色

### 图表卡 ChartCard

- 卡片标题左上角
- 右上角放筛选或操作按钮
- 图表区域留白充足
- Tooltip 使用白底卡片风格

### 风险卡 RiskAlertCard

- 高风险：红色图标 + 浅红背景
- 中风险：橙色图标 + 浅橙背景
- 低风险：绿色图标 + 浅绿背景

### AI 回答卡 AnswerCard

固定结构：

1. 结论
2. 数据依据
3. 原因解释
4. 业务建议
5. 风险提示

## 13. 不建议做法

- 不要全屏大面积深绿色。
- 不要做过度炫酷的大屏动画。
- 不要把高风险全部用大面积纯红展示。
- 不要每个页面使用不同视觉体系。
- 不要大量使用图片替代表格和图表。
- 不要在页面内写死颜色，应尽量使用主题变量。
