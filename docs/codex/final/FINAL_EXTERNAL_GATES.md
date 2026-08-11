# FINAL EXTERNAL PRODUCTION GATES

以下事项不能由当前个人本地工程验收替代，统一登记为 `EXTERNAL_PRODUCTION_GATE = PENDING`。

| 门禁 | 当前状态 | 生产前责任与证据 |
|---|---|---|
| 真人业务审批 | PENDING | 业务 Owner 对指标、口径、报表和决策用途签字 |
| `production_human_signoff` | PENDING | 获授权审批人在受控变更单中确认 |
| 正式企业身份 / IdP | PENDING | 企业 IdP、组织/租户映射、离职与紧急账号演练 |
| 正式 Secret Manager | PENDING | 生产 Secret 注入、轮换、审计与泄漏响应演练 |
| 正式监控 / 告警 | PENDING | 指标、日志、Trace、告警路由、值班升级链路验收 |
| 正式容量测试 | PENDING | 生产等效数据量、并发、长稳、限流和成本报告 |
| 正式灾备环境 | PENDING | 备份恢复、跨故障域、RTO/RPO 与演练记录 |
| 生产变更窗口 | PENDING | CAB/变更单、冻结窗口、依赖方通知 |
| 正式生产切流 | NOT_EXECUTED | 明确流量计划、观察窗口和停止条件后执行 |
| 生产回退责任人 | PENDING | 指定主责/替补、通讯录、回退授权和演练 |
| 生产 SLA 长周期证明 | PENDING | 在正式环境持续采样可用性、延迟、错误率与数据正确性 |

当前明确禁止：远端推送、生产部署、模型激活、RAG production alias 切换与生产流量切入。

这些门禁不属于本地工程缺陷，因此不计入 `RELEASE_BLOCKING`，也不否决 `PROJECT_ENGINEERING_COMPLETE` 或 `LOCAL_PREPRODUCTION_RC`；生产上线仍必须逐项关闭后另行审批。
