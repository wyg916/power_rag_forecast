# 测试摘要

- `git diff --check`：PASS。
- TypeScript `tsc --noEmit`：PASS。
- `npm run build`：PASS，Vite 5.4.21，3689 modules transformed。
- `viewState.test.mjs` 与 `uiShellContracts.test.mjs`：19/19 PASS。
- `pageLayoutConvergenceContracts.test.mjs`：7/8 PASS；唯一失败为既有的 10px 图表标签门槛，未修改主项目同样复现，非本次回归。
- `tests.test_formal_forecast`：1/1 PASS。
- Chrome 登录态：1920×919、1440×900、1366×768 均无页面级横向或纵向溢出；目标边线误差均为 0px。
- 小时解释抽屉打开/关闭、历史对比页签、模型评估页签、返回 24 小时预测均 PASS；控制台 warning/error 为 0。
- 主项目前端服务恢复到 `E:/智能运营分析项目/frontend` 的 5173 端口，HTTP 200。
