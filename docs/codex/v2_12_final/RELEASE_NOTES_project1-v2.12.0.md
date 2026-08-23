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
- 修复 Settings 只读接口错误要求写权限的问题；所有写入与接口测试动作仍保持更高权限边界。
- 修复 Analyst 无权限时仍进入策略审核模式并请求 review history 的问题。
- 修复 DeepSeek 成本受控复验绕过 `DATA_PLANNER` endpoint model 路由的问题，并补齐脱敏 Adapter 诊断。
- 修复附件回答将 Grounding/Citation 证据耦合的问题；A–F 离线矩阵与一次授权真实 selected-only 附件 QA 均通过，Enterprise KB chunk 为 0。

## 验证状态

历史 Round 1 在代码 SHA `44e048d56ccc8f21ac60bc52881b2b806f97d92f` PASS；阻断修复提交为 `a073f96b67d3d2b387ef51dee905e055dc983c69`。包含本发布文件的提交以 `SELF` 表示新的 `FINAL_PRE_RELEASE_SHA`；提交后不再修改 tracked 文件。只有在该同一 SHA 上完成 Round 2 全量回归后，才能冻结 `FINAL_SHA` 并评估 main/root/tag/remote 归一。

## 已知边界

- 原生 OS drag/drop 未实际自动化执行；handler 由契约测试覆盖。clipboard paste 与 file selector 已实际执行。
- 本版本是 `LOCAL_FINAL_RC`，不是生产发布。
- `PRODUCTION_GO_LIVE=NOT_EXECUTED`
- 生产 TLS、Secret Manager、告警/SLO、容量长稳、DR 与外部审批均 `NOT_EXECUTED`。
- 未激活生产模型，未切 RAG production alias，未执行生产切流。
