# 视觉验收

视口：1672×941，DPR=1，浏览器缩放 100%，字体加载完成。

## 参考与差分

- 目标图、候选图、并排图、叠加图和差分图：`../FORECAST_CENTER_BOTTOM_SPACE_FONT_REWORK_20260815/browser/`。
- 最新 Release 再收敛后的实现截图：
  - `screenshots/implementation_24h_1672x941.png`
  - `screenshots/implementation_history_1672x941.png`
  - `screenshots/implementation_peak_model_1672x941.png`
- 真正最终路径重新登录后的实现截图：
  - `screenshots/final_path_24h_1672x941.png`
  - `screenshots/final_path_history_1672x941.png`
  - `screenshots/final_path_peak_model_1672x941.png`
- 最终路径并排图：`screenshots/final_path_compare_24h.png`、`final_path_compare_history.png`、`final_path_compare_peak_model.png`。
- 最终路径差分图：`screenshots/final_path_diff_24h.png`、`final_path_diff_history.png`、`final_path_diff_peak_model.png`。
- 全图辅助指标（不是独立 PASS 依据）：RGB MAE 依次为 14.810 / 14.443 / 14.891；阈值 12 以上像素占比为 23.552% / 19.901% / 19.451%。差异包含用户要求保持不变的左侧既有导航与真实数据差异。

## 逐页/逐 Card 矩阵

| 页面 | 外部布局 | Typography / Icon | Alignment / Spacing | Data / Status | Table / Chart | 内容完整度 | 结果 |
|---|---|---|---|---|---|---|---|
| 24 小时预测 | 左侧导航和外部 Card 未重排 | 字号、行高、图标尺寸统一并放大 | 标题、指标、按钮、图例与表格对齐 | 技术审计字段不再前端展示；业务状态保留 | 24 点图表、预测明细列宽与分页完整 | 底部 Card 充分利用高度，无大片无意义空白 | PASS |
| 历史对比 | 左侧导航和外部 Card 未重排 | 指标、洞察、表格文字可读性提升 | 右侧洞察与底部信息卡间距统一 | 对比结论、解释性和健康状态如实呈现 | 趋势图、三口径对比列和分页完整 | 底部区域填充，信息密度饱满 | PASS |
| 峰谷分析与模型评估 | 左侧导航和外部 Card 未重排 | 仪表盘、摘要、评估单元字号统一 | 解释卡、七项评估卡和底表对齐 | 评估状态、门禁、训练/回测状态完整 | 仪表、评估矩阵、Baseline 表完整 | 无明显空白、裁切或内部滚动条 | PASS |

## 视口结果

- 1672×941 三页均 `scrollWidth=1672`、`scrollHeight=941`，无水平或意外纵向溢出。
- 1440×900、1366×768 候选复验无水平溢出；小视口使用页面级纵向滚动，不用 Card 内滚动条掩盖布局问题。
- 无遮挡、错位、不可点击区域、文字截断或 Card 裁切。
- 用户于 2026-08-15 明确确认候选 SHA 与三页视觉通过。
- 最终路径重新截图后逐 Card 复核与获批候选一致，三页均无横向或意外纵向溢出、无大块无意义空白。
