# 预测中心三页面最终 Release 验收

## 结论

状态：`PASS`。用户确认的候选 `7090de4f76a4df228f7b98e9203b205c5aeba0fd` 已集成到真正最终分支与原最终路径；REJECTED 候选没有进入历史。未推送远端，未修改生产 alias、正式环境、模型激活状态或数据库结构。

## 最终来源

- 路径：`E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807`
- 分支：`release/beta10d-agent-rc-20260807`
- 集成内容提交：`a3135a67ac3555af5c1979168d8bb210cab7d34b`
- 本文件所在提交：最终验收证据提交
- 前端：`http://127.0.0.1:5190`，PID 23780，工作目录为最终路径 `frontend`
- 后端：`http://127.0.0.1:8030`，PID 19288，由最终路径运行 uvicorn

## 自动与浏览器门禁

| 门禁 | 结果 |
|---|---|
| 三页 1672×941、DPR=1、100% 缩放 | PASS |
| 三页 scrollWidth/clientWidth | 1672/1672 |
| 三页 scrollHeight/clientHeight | 941/941 |
| 禁止展示的过期/审计技术字段 | 0 命中 |
| 逐 Card Typography、Alignment、Spacing、Icon、Data、Status、Table、Chart | PASS |
| 24h 刷新、导出、分页、小时解释、策略/数据健康跳转 | PASS |
| 历史对比刷新、区间、粒度、分页、导出 | PASS |
| 模型页刷新、导出、详情/日志/回测跳转 | PASS |
| 更新预测共享真实 POST | HTTP 200，任务已受理；后台完成态未被任务中心证明，不作完成宣称 |
| 干净三页 Console Error/Warning | 0 / 0 |
| 干净三页目标请求 | 19/19 HTTP 200，Unexpected 4xx/5xx=0 |
| 16 个预测相关 GET API | 16/16 HTTP 200 |
| Unauthorized / Forbidden | 401 / 403，符合预期 |
| API / PostgreSQL 24 点 min/max/avg | 一致 |
| TypeScript / 正式 build | PASS / PASS（3675 modules） |
| 相关非数据库回归 | 27 passed；7 个 DB 用例由项目 guard 要求隔离 runner，未降低门禁 |

## 回滚

Release 集成前回滚点为 `a6c3bfdca8a181c7f5051b8d0933579eb5d58f2f`；首页候选继续保留在 `e98010f664921b033eb91cb53d9b8dcd236e7f19`。回滚涉及分支指针变更，执行前必须再次获得用户确认。
