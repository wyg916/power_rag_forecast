# 测试摘要

- `git diff --check`：PASS。
- TypeScript `tsc --noEmit`：PASS。
- 最终 `npm run build`：PASS，Vite 5.4.21，3689 modules transformed。
- `viewState.test.mjs`：7/7 PASS。
- `uiShellContracts.test.mjs`：12/12 PASS。
- 数据库无关预测中心布局/事实契约：12/12 PASS。
- `tests.test_formal_forecast`：1/1 PASS。
- Chrome 登录态 1920×919：三页几何、可见内容、无页面级溢出、Global AI 局部安全区 PASS。
- Chrome 登录态 1440×900：24h 页面与明细表完整可见、无页面级溢出 PASS。

说明：3 个依赖当前本地数据库状态的读取测试未作为本次纯前端 UI 合入完成条件；未修改对应后端、接口或数据库。
