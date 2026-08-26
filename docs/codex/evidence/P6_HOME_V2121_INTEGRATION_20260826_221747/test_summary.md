# 测试摘要

| 门禁 | 结果 |
|---|---|
| `npm.cmd run typecheck` | PASS |
| `npm.cmd run lint` | PASS；12/12 |
| `npm.cmd run unit` | PASS；53/53 |
| `npm.cmd run build` | PASS；3686 modules transformed |
| `git diff --check` | PASS；仅存在仓库既有 LF→CRLF 提示 |
| 1919×928 | PASS；页面滚动 0、横向溢出 0 |
| 1440×900 | PASS；页面滚动 0、横向溢出 0 |
| 1366×768 | PASS；页面滚动 0、横向溢出 0，紧凑态三主操作可见 |
| 1919×260 / scrollTop=600 | PASS；标题区固定 y=60，背景不透明，z-index=300 |
| 页头“更多”→24 小时预测 | PASS；路由进入 `#/forecast/forecast-24h` |
| 刷新总览 | PASS；刷新后 KPI 与图表继续呈现，无错误态 |
| 全局 AI | PASS；抽屉可打开、关闭，完整 AI 页面入口存在 |
| 图表 Tooltip | PASS；价格/区间 3 位、负荷 2 位、风险 1 位；空值显示 `--` |
| 浏览器控制台 | PASS；error 0，warning 0 |

说明：浏览器使用本地开发只读身份验证功能闭环，未修改权限；隐藏/展示仍由既有 RBAC 决定。
