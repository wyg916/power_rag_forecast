# 更新预测任务完成态闭环报告

结论：`PREDICTION_TASK_STATUS_CLOSURE=PASS`。

根因是启动器只启动健康队列 worker，真实预测任务被投递后没有消费者，任务长期停留在 PENDING。修复新增专用 `forecast_final_rc` worker、队列感知派发、业务任务/Celery Task 映射、worker 不可用 503 快速失败，以及成功/失败终态持久化与回读。

验证结果：

- 专项回归 92/92；
- 成功、失败、重复提交、worker 不可用、状态轮询、任务中心回读、刷新后回读和重启后持久化均由测试覆盖；
- worker 离线时真实按钮返回受控 503，未留下新的永久 PENDING 任务；
- 浏览器真实任务 `task_a087a267af89` 经 `ACCEPTED → RUNNING → FAILED`，631.16 秒后形成可读终态，刷新后仍可见；
- 真实失败原因是遗留预测流水线在禁用 MySQL/文件 fallback 后缺少可用的 PostgreSQL 模型事实，不是状态回传丢失；错误摘要未泄露 DSN 或密钥。

提交：`ca6a1bc fix(tasks): close forecast worker lifecycle`。证据截图：`task-center-forecast-terminal-failed-1672x941.png` 与 `forecast-worker-offline-fast-fail-503-1672x941.png`。
