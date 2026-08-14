# 预测中心三页面底部空间与字号返工

状态：`READY_FOR_USER_VISUAL_CONFIRMATION`。这是独立候选版本，不是最终项目 PASS，未合入冻结 Release。

- 候选分支：`codex/ui-forecast-center-fidelity-20260814`
- 功能基线：`release/beta10d-agent-rc-20260807` / `1f4f7e50e3177aec21594b52ce74cd03dd77ea7d`
- 本轮源代码提交：`91644ca`（本目录所在最终证据提交将在交付报告中给出完整 SHA）
- 候选地址：`http://127.0.0.1:5188/#/forecast/24h`
- 目标：消除 24 小时预测、历史对比底部大块无意义空白；三页 Card 内字号尽可能增大，同时保持内容完整、无裁切。
- 边界：左侧 Sidebar、全局 Header、页面外部模块顺序和横向布局保持不变；无后端、数据库、模型、RAG、权限或生产配置修改。

核心结果：

- 24 小时预测底部区域由约 224px 扩展为 353px，完整显示 8 行明细、分页和三张状态卡。
- 历史对比底部区域由约 236px 扩展为 320px，完整显示 7 行明细、分页和三张结论卡。
- 三页 Page/Card/KPI/洞察/表格/图表字体分别提升至 22/17/24–26/12–13/12px 主尺度。
- 1672×941 下三页 document 与 viewport 同尺寸，无水平溢出、Card 裁切、Card 内滚动条或底部大片空白。
- 1440×900、1366×768 下采用页面级纵向滚动，Card 不裁切且无水平溢出。

证据索引：

- `browser/target_*_1672x941.png`：目标参考图。
- `browser/implementation_*_1672x941_final.png`：最终候选实现图。
- `browser/comparison_*_workspace.png`：仅右侧工作区的并排对比。
- `browser/overlay_*_workspace.png`、`browser/diff_*_workspace.png`：叠加与差分辅助图。
- `VISUAL_ACCEPTANCE.md`：逐 Card 视觉矩阵。
- `FUNCTIONAL_ACCEPTANCE.md`：可见控件与状态矩阵。
- `RUNTIME_AND_DATA.md`：运行实例与 API/PostgreSQL 对账。
- `TEST_REPORT.md`：构建、测试、Console/Network 与响应式结果。
- `USER_CONFIRMATION.md`、`INTEGRATION_RECEIPT.md`：确认和集成门禁。
