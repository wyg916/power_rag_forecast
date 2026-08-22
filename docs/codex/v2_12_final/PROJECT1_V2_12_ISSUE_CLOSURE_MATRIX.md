# PROJECT1 v2.12.0 Issue Closure Matrix

| ID | 发布阻断/问题 | 根因 | 修复提交 | 验收证据 | Round 1 |
|---|---|---|---|---|---|
| V212-FE-RBAC | 冻结 capability 与部分页面展示判断不一致 | 页面仍有本地条件判断，未统一到权限口径 | `9bcd7f3` | UI contracts、4 角色真实 manifest、32 路由浏览器矩阵 | CLOSED |
| V212-CHATBI-MT | 多轮问题省略字段时丢失上轮 AnalysisPlan 语义 | planner 对 omitted 与显式空值未区分 | `48087e8` | ChatBI contracts 50/50、Golden 50/50、raw SQL execution=0 | CLOSED |
| V212-ACL-AUDIT-SEQ | runtime 对 `audit_logs` 有 INSERT 但无序列权限 | `audit_logs.id` 默认值引用 `audit_logs_id_seq`；表权限不会隐含序列权限 | `ae8d607` | 合法 runtime INSERT PASS；非法写入拒绝；危险 role attributes=0；脚本幂等 | CLOSED |
| V212-ACL-FORECAST | runtime 读取冻结预测输入事实表被 ACL 拒绝 | 安全脚本未给运行身份最小只读权限 | `4a108ce` | 指定事实表只读 PASS；写入仍拒绝；脚本幂等；schema signature 无非预期变化 | CLOSED |
| V212-RUNTIME-OWNERSHIP | 第二次 start 将同一控制器拥有的进程降为 unmanaged | 幂等发现逻辑覆盖了既有受控归属 | `44e048d` | 15 targeted tests；cold/second start PID 与 creation identity 不变且 managed=true；restart/stop PASS | CLOSED |
| V212-RAG-LATENCY | 首次 Formal 50 的 P95 超门槛 | 16GB 本机上并发/批次组合不适合固定模型资源 | 无代码修改；固定并发 4、batch 4、候选 3 的受控验收配置 | 50 问、20/20 gates，P95=803.891ms，Recall@3/5=1，MRR=.9467，写计数 0 | CLOSED |

## ACL 最小权限闭环

- 已确认 `audit_logs.id` 实际使用 `nextval('audit_logs_id_seq'::regclass)`。
- 仅为运行身份补齐生成该默认值所需的最小序列权限；未使用 `GRANT ALL`。
- runtime role 未获得 owner、superuser、CREATEDB、CREATEROLE 或 BYPASSRLS。
- 非法/越权写入继续 fail-closed。
- ACL 脚本连续执行两次结果一致，数据库 schema 签名无非预期变化。

## 未执行但不属于本地 RC 阻断

Production Go-Live、生产 TLS、Secret Manager、生产 SLO/告警、容量长稳、DR 与外部审批均为 `NOT_EXECUTED`，不得解释为已关闭的生产门禁。
