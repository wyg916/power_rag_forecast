# P6 首页驾驶舱修复合入 v2.12.1 main

- 状态：PASS
- 目标基线：`main@cfd40e07176988ae1ea46281449746cdb2835b3a`
- 来源修复：`68429da07b43ed05c3c952d6a86cbe762a70663d`
- 合入方式：语义移植，不直接 cherry-pick。来源分支落后于 main 30 个提交且领先 3 个提交，直接覆盖会回退 v2.12.1 的全局 AI、RBAC、图表 `autoResize` 和安全区能力。
- 结果：仅移植首页布局/Sticky/Tooltip 必要改动，现有真实 API、权限、全局 AI 和业务状态机保持不变。
- 数据库影响：无。
- 外部调用：无。
- 推送/生产发布：未执行。

主要验收证据：

- `home_1919x928.png`
- `home_1440x900.png`
- `home_1366x768.png`
- `home_sticky_scroll_600.png`
- `browser_metrics.json`
- `test_summary.md`
