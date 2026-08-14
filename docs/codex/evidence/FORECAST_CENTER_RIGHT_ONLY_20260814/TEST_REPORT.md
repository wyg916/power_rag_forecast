# 测试报告

| 门禁 | 结果 |
|---|---|
| `git diff --check` | PASS |
| 预测中心/前端契约 pytest | 22 passed / 3 个数据库上下文用例改由真实只读链路核对 |
| 右侧密度专项 pytest | 7 passed / 1 个数据库上下文用例改由真实只读链路核对 |
| TypeScript | PASS（正式 build 内执行） |
| Vite 正式 build | PASS，3674 modules；受本机并发 Node 进程影响耗时 7m26s |
| 16 个预测中心依赖 GET API | PASS，Unexpected 4xx/5xx = 0 |
| API / PostgreSQL run、24 行、min/max/avg | PASS |
| GET 写副作用 | PASS，受保护表计数不变 |
| 401 / 403 | PASS |
| 左侧锁定文件 diff | PASS，0 文件 |
| Browser 三页截图、Console、逐控件 | BLOCKED：Browser URL policy 拒绝 localhost |

未执行数据库迁移、模型反序列化、模型激活、RAG 发布、生产切换或远程推送。
