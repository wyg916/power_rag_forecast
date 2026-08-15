# 测试报告

| 门禁 | 结果 |
|---|---|
| `git diff --check` | PASS |
| 预测中心/前端契约 pytest | 22 passed / 3 个数据库上下文用例改由真实只读链路核对 |
| 右侧密度专项 pytest | 7 passed / 1 个数据库上下文用例按测试数据库保护规则 deselected，并由真实只读链路核对 |
| TypeScript | PASS（正式 build 内执行） |
| Vite 正式 build | PASS，3674 modules；`tsc && vite build`，3m10s |
| 16 个预测中心依赖 GET API | PASS，Unexpected 4xx/5xx = 0 |
| API / PostgreSQL run、24 行、min/max/avg | PASS |
| GET 写副作用 | PASS，受保护表计数不变 |
| 401 / 403 | PASS |
| 左侧锁定文件 diff | PASS，0 文件 |
| Browser 三页 1672×941 截图 | PASS；DPR=1、无水平/意外纵向滚动 |
| Browser 逐控件 | PASS；刷新、明细抽屉、分页、小时/天/周、近7/30天、3类 CSV、3个跳转与权限禁用态 |
| Loading / Empty / Error / Stale / Unauthorized / Forbidden | PASS / CONTRACT PASS（真实库非空）/ PASS / PASS / 401 PASS / 403 PASS |
| Console Error / Warning | 0 / 0 |
| 干净目标页网络窗口 | 54 请求，HTTP 200=54，Unexpected 4xx/5xx=0 |
| 1920/1600/1440/1366 响应式 | 3 页×4 视口全部无横向溢出 |
| `run_project.bat` 连续两次 | PASS / PASS |

未执行数据库迁移、模型反序列化、模型激活、RAG 发布、生产切换或远程推送。
