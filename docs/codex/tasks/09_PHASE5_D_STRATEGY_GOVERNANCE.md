# PHASE5-D 智能运营策略生成、人工审核与审计闭环

## 目标

在 PHASE5-C 已冻结的正式预测与报告事实之上，构建只提供决策支持、可人工审核、可审计、可回滚的策略治理闭环。策略不得自动执行交易、投标、设备控制或资金操作。

## 子阶段

1. D1：策略数据模型、状态机、迁移与回滚。
2. D2：确定性规则引擎、规则版本和冲突消解。
3. D3：受控 AI 解释、引用真实性和 fail-closed 校验。
4. D4：人工审核、RBAC、不可变审核记录、同事务审计和前端闭环。
5. D5：20 场景、故障注入、读取无副作用、全回归、运行时和三视口浏览器验收。

各子阶段必须有独立检查点、结果证据和 PASS 门禁；任一阶段不通过不得进入下一阶段。

## 策略事实契约

- 必须绑定存在的 success forecast run、对应 report、24 条预测事实、模型/特征/结果哈希和可验证知识引用。
- 规则结果、风险、优先级、策略类型、禁止动作和内容哈希必须由程序确定；AI 仅解释。
- historical、stale、unavailable、行数不足、报告/证据不足时必须 fail-closed。
- 历史或过期输入只能生成 `audit_only` 草稿，禁止发布为当前策略。
- 所有读取端点无 seed、生成、提交、审核、发布或其他写副作用。

## 状态与权限

- 状态：draft、pending_review、approved、rejected、published、superseded、expired、cancelled。
- analyst/operator 可生成和提交；reviewer/admin 可审核；仅 admin 可发布和执行终止类治理动作。
- 创建者不能批准自己的策略；reject/return 必须有意见。
- request_id 必须幂等；状态、review 和 audit_log 必须在同一事务内完成。

## PASS 门禁

1. 隔离库完成 0014 -> 0015 -> 0014 -> 0015 且 schema hash 一致。
2. 正式迁移只增加策略治理 schema，不修改预测、报告或模型事实。
3. 十条规则清单、版本、确定性、输入乱序和冲突消解通过。
4. AI 不得虚构事实/引用、改写风险或删除禁止动作；超时和篡改 fail-closed。
5. RBAC、自批拦截、历史/过期发布拦截、幂等和并发审批通过。
6. 20 个业务场景和 20 个故障注入全部通过，所有 critical 通过。
7. 六类读取各 100 次无副作用。
8. D/C/A/B、T001–T005、Phase4、FastAPI/PostgreSQL/Redis/Celery、TypeScript/Vite 和浏览器完成验收。
9. 正式预测、报告和 Active artifact 哈希不变；无新预测、训练、外部交易或设备写入。
10. 最终证据 32 项，Manifest 错误为 0；Git 状态完成审计。

## 回滚

- 使用 PHASE5-D 主检查点 custom dump 和 restore list，在新恢复库先验证。
- 经确认后精确回滚唯一策略记录和 generation audit，再执行 Alembic 0015 -> 0014。
- 代码使用检查点 Git diff 与关键哈希恢复；禁止 `git reset --hard`、批量删除或直接覆盖正式库。
