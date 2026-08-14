# 测试与自动门禁

| 门禁 | 结果 |
|---|---|
| `git diff --check` | PASS |
| TypeScript `tsc --noEmit` | PASS |
| 正式 `npm run build` | PASS，3674 modules transformed |
| 预测中心/七态定向 pytest | 22 passed，3 个 DB 上下文用例按项目 guard deselected，并由真实只读 API/DB 对账替代 |
| 16 个预测中心 GET API | 16/16 HTTP 200 |
| 真实 API / PostgreSQL | run_id、24 行、min/max/avg 一致；保护表前后不变 |
| 1672×941 视觉 | 三页无水平或意外纵向溢出、Card 裁切、遮挡、错位或大片底部空白 |
| 1920 / 1440 / 1366 响应式 | 无水平溢出；1440/1366 采用页面级纵向滚动且 Card 不裁切 |
| Console | Error=0，Warning=0；仅 Vite debug 与 React DevTools info |
| 干净网络窗口 | 54 请求，HTTP 200=54，Unexpected 4xx/5xx=0，Traceback=0 |
| Unauthorized / Forbidden | 401 / 403 按契约返回 |
| `run_project.bat` 连续两次 | 在最终证据提交后执行并在最终交付报告给出结果 |

初次直接运行测试组时，项目普通 pytest 按 DB guard 移除本地 `DATABASE_URL`，3 个需要数据库上下文的用例因此不绕过保护规则；其核心断言已由同一候选代码、真实 8016 后端和显式只读 PostgreSQL 查询逐项闭环。
