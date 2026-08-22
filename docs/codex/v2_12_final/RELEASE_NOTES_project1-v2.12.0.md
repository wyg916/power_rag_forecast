# PROJECT1 v2.12.0 Local Final RC Release Notes

## 本地 RC 概要

v2.12.0 汇总 A 的预测与模型事实闭环、B 的前端/RBAC/全局 AI shell，以及 C 的 AI runtime、ChatBI、附件、能力 manifest、启动控制与 CI 能力。所有接口继续受 `INTERFACE_CONTRACT.md` 与 `FILE_OWNERSHIP.md` 约束。

## 关键闭环

- 正式预测链完成 PostgreSQL 模型事实、冻结输入、24 小时结果、幂等/回滚/重启回读和下游 run_id 血缘验证。
- UI 通过 32 路由、4 viewport 与 4 类真实角色验收；权限判断统一到 capability manifest。
- ChatBI Golden 50/50；LLM 只生成受控 AnalysisPlan，不直接生成并执行任意 SQL。
- MiMo/DeepSeek/Kimi 的逻辑模型路由、显式 Premium 边界与 trace 字段通过最小真实调用。
- AI 悬浮助手、附件解析/引用/删除、跨用户隔离、prompt injection 防护与 Memory 生命周期通过。
- RAG 在 enterprise 本地 RC 配置下通过 50 问质量/ACL/隔离/只读门禁，未切换 production alias。
- 运行控制通过 cold start、第二次幂等 start、doctor/logs/restart/stop 与来源证明。

## 发布阻断修复

- 修复 ChatBI 多轮省略字段语义保持。
- 修复前端冻结 capability gate 一致性。
- 按最小权限补齐 runtime 合法写入 `audit_logs` 所需的 `audit_logs_id_seq` 权限，并新增回归测试。
- 按最小权限补齐预测冻结输入事实表只读权限；写路径仍拒绝。
- 修复运行控制第二次 start 丢失进程 ownership 的问题，未知进程仍不会被接管。

## 验证状态

Round 1 在代码 SHA `44e048d56ccc8f21ac60bc52881b2b806f97d92f` PASS。包含本发布文件的提交将形成 `FINAL_PRE_RELEASE_SHA`；只有在该同一 SHA 上完成 Round 2 全量回归后，才能冻结 `FINAL_SHA` 并进行 main/root/tag/remote 归一。

## 已知边界

- 原生 OS drag/drop 未实际自动化执行；handler 由契约测试覆盖。clipboard paste 与 file selector 已实际执行。
- 本版本是 `LOCAL_FINAL_RC`，不是生产发布。
- `PRODUCTION_GO_LIVE=NOT_EXECUTED`
- 生产 TLS、Secret Manager、告警/SLO、容量长稳、DR 与外部审批均 `NOT_EXECUTED`。
- 未激活生产模型，未切 RAG production alias，未执行生产切流。
