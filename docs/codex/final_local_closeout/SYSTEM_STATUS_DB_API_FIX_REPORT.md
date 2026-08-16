# 系统状态数据库/API 修复报告

结论：`SYSTEM_STATUS_DB_API_FIX=PASS`。

根因是系统健康快照读路径误用了安全身份连接缝；该身份承担认证/安全域职责，不拥有 `system_health_snapshots` 业务读权限，导致合法 GET 返回 500。修复将健康快照 Repository 切回应用最小权限读取连接缝，保留数据库不可用/无权读取时的受控不可用语义，GET 不产生 seed、同步或其他写副作用。

验证结果：

- 专项测试 6/6；
- `/api/settings/status/summary`、`/api/settings/status/health-details`、`/api/settings/status/overview` 均为 200；
- 最小权限应用身份保持非超级管理员；
- 页面卡片可加载，Console Error=0；
- 数据库连接信息未进入响应、日志或报告。

提交：`17e6d93 fix(settings): use runtime ACL for health snapshots`。截图：`system-status-after-fix-1672x941.png`。
