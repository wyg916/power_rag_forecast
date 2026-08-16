# 项目一本地最终收口报告

当前结论：`PROJECT1_LOCAL_FINAL_CLOSEOUT=PASS`。

| 项目 | 结果 |
|---|---|
| 起始分支/SHA | `release/beta10d-agent-rc-20260807` / `adac8eca4eae70548a648c14b7f3c61242d1a1f3` |
| 最终分支/SHA | 同一 Release / 由最终 annotated tag 解引用 |
| 最终标签 | `project1-v2.11.2-local-final-rc-20260816` |
| 首页 | INTEGRATED / PASS |
| 系统状态接口 | PASS |
| 预测任务终态 | PASS |
| Migration | PASS / 唯一 `0022_chatbi_semantic_v1` |
| 后端 | 1119/1153 passed，34 skipped，0 failed/errors |
| 前端 | 230/230；TypeScript PASS；Vite PASS |
| 浏览器 | 32/32；最终 5xx/Console/Page/Request failed 均 0 |
| 启动 | 冷启动 PASS；运行态幂等 PASS |
| 敏感扫描 | PASS；65 文件，高置信真实凭据 0，大文件 0 |
| GitHub | 分支 PASS；annotated tag PASS；ahead/behind `0 0` |
| 最终运行态 | STOPPED_CLEANLY |

## 关键变更

1. 集成已获确认的首页候选并完成视觉/功能验收。
2. 修正系统健康快照的数据库连接缝，合法 GET 不再 500。
3. 增加专用预测 worker 与队列/终态/离线门禁，永久 PENDING 问题关闭。
4. 恢复复合业务问题的工具 + RAG grounding fail-closed。
5. 将 Qdrant 冷恢复等待窗口调整为可覆盖的约 4 分钟上限。
6. 修复本机数据库 ACL 漂移并验证知识库只读路由。

## 已知剩余问题

- 浏览器真实预测任务进入 FAILED 的业务原因仍是遗留预测流水线缺少可用的 PostgreSQL 模型事实；任务生命周期和失败回传已闭合，生产预测成功率仍需后续专项。
- lint 与前端 JS 单元测试脚本尚未配置；本轮以 TypeScript、Vite、230 项契约和 32 路由浏览器验收替代，不伪报不存在的脚本。
- 生产外部门禁全部未执行：生产部署、正式密钥轮换、监控告警、容量/灾备、外部审批、模型 Active 晋升和 RAG production alias 切换。

回滚：代码可回退到起始 SHA；数据库本轮仅执行幂等 ACL/Head 检查和测试隔离 Schema，测试对象已清理；恢复标签 `project1-pre-local-closeout-20260816-adac8ec` 保留。
