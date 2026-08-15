# 逐 Card 视觉门禁矩阵

主基准为实际读取的 Figma 文件 `SCO0czpBdYglv3NAuwo22L` 节点 `2:2`、`3:2`、`4:2`。用户最新要求锁定左侧和外部 Card 几何，因此全画布像素差异只作辅助观察，不以目标图的无 Sidebar 外壳反向覆盖锁定边界；生产候选始终使用真实数据。

| 页面 | Card / 区域 | 代码完成 | 1672×941 截图与目标差分 | 结论 |
|---|---|---:|---:|---|
| 全部 | 左侧 Sidebar、全局 Header、BasicLayout | 未修改 | 候选与旧实现左侧一致 | 锁定 PASS |
| 24 小时 | 右侧业务摘要工具栏与操作区 | 是 | 字级、对齐、间距与按钮态完整 | PASS |
| 24 小时 | 5 个 KPI Card | 是 | 数值、单位、图标、状态层级清晰 | PASS |
| 24 小时 | 预测曲线、区间、峰谷窗口与峰值点 | 是 | 真实区间缺失时明确“待接入”，未伪造带状区间 | PASS（真实性优先） |
| 24 小时 | 策略洞察白底分隔内容 | 是 | 4 段图标/标题/正文/分隔完整 | PASS |
| 24 小时 | 8 行明细与 3 张紧凑摘要 Card | 是 | 首屏信息密度饱满、无内部滚动条 | PASS |
| 峰谷/模型 | 6 个 KPI Card | 是 | Typography/Icon/Status 与目标层级一致 | PASS |
| 峰谷/模型 | 多色分段仪表与业务解释 | 是 | Gauge、5 行指标、3 段解释完整 | PASS |
| 峰谷/模型 | 7 张评估卡、Baseline 表、训练回测 | 是 | 行高和纵向分布已二次收敛，无大块无意义空白 | PASS |
| 历史对比 | 6 个 KPI Card | 是 | 数据、单位、趋势和卡内对齐完整 | PASS |
| 历史对比 | 近 7/30 天、小时/天/周、三序列与标注 | 是 | 控件、图例、标注完整；无真实历史均值时不伪造曲线 | PASS（真实性优先） |
| 历史对比 | 洞察白底分隔、7 行表与 3 张侧卡 | 是 | 内容完整；“数据状态/已过期”已移除 | PASS |

## 图像证据

- 实现图：`browser/implementation_24h_1672x941_final.png`、`implementation_history_1672x941_final.png`、`implementation_peak_model_1672x941_final.png`。
- 并排图：`browser/compare_24h_target_vs_candidate.png`、`compare_history_target_vs_candidate.png`、`compare_peak_model_target_vs_candidate.png`。
- 叠加图：`browser/overlay_*_target_vs_candidate.png`；差分图：`browser/diff_*_target_vs_candidate.png`。
- 全画布辅助像素比（阈值 16）：24h 22.42%、历史 18.54%、峰谷模型 17.82%。差异主要来自用户锁定保留的 Sidebar/全局外壳、真实数据和目标数据不同，不能用该指标宣称 1:1，也不能据此破坏锁定边界。

视觉/功能自动门禁已完成，候选状态为 `READY_FOR_USER_VISUAL_CONFIRMATION`。未经用户针对候选 SHA 和本组截图明确确认，禁止最终集成。
