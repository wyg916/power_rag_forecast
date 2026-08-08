# Day3A RAG AI 质量与 ACL 闭环报告

## 结论

**Day3A AI 自动化技术门槛 PASS；Day3B Release Drill 不具备准入资格。**

current strict evaluator 最终重算为 AI100 `100/100`、Critical `30/30`、Grounding `100%`、AI ACL `100%`、Citation integrity `100%`、数值幻觉 `0`。但本次锁定配置 warm Retrieval 50 题复测 P95 为 `2408.614ms`，未复现 `<1500ms`；此外 Golden 100 项仍为 `pending human approval`。因此不执行 Snapshot、Alias、Release 或生产发布。

## 基线与边界

- 分支：`release/beta10d-agent-rc-20260807`
- Starting SHA：`a954b8800f76d648ec3914b26b32b775db0a469b`
- Final SHA：本报告所在闭环提交，实际值另存于证据目录 `FINAL_SHA.txt`
- 检查点：`backups/phase3/20260808_220638227_DAY3A_RAG_AI_QUALITY_PRE`
- Alembic：`0019_memory_identity_safety`
- 只读预测 fixture：`run_20260801T140000000000Z_b2a2935315`，24 行 success，结果 hash `072140d385b3cf4d1410f8a64aedba537fdee83d705d3257368f6a7180c4c05b`
- 未执行：Memory 新功能、ChatBI、Snapshot、Alias、正式 Release、模型激活、生产发布。

## 实施内容

1. 统一 `IdentityContext` 在检索、上下文组装、工具、会话状态和 Citation 前置校验中的传播；身份不匹配或授权证据为空时，在业务工具执行前 fail-closed。
2. 固定 Answer Context 顺序：System Policy → Identity Scope → Question → Authorized Context → Tool Facts → Memory Context → Constraints → Citation Requirements → Output Schema；当前授权事实优先于历史记忆。
3. 将离线 RAG 回答限制为授权 Citation quote 与问题范围，补齐 historical、unavailable、fail-closed 等状态语义和通用领域路由规则。
4. 正式工具题显式使用已存在、不可变、成功的 PostgreSQL 24 行 run；只有通过数据库一致性验证的工具输出才进入数值证据，允许其常规 1/2 位小数展示，未经验证数字继续失败。
5. 新增 legacy/current strict 差异审计、100 题 Failure Matrix、Critical Matrix、ACL failures 与 claim-level grounding 证据。

## 三轮结果

| 轮次 | strict AI100 | Critical | Grounding | ACL | 数值问题 | 说明 |
|---|---:|---:|---:|---:|---:|---|
| 1 | 18/100 | 10/30 | 57% | 100% | 216 | ACL/工具一致性修复完成，但长证据摘录与严格数值口径不兼容 |
| 2 | 83/100 | 20/30 | 98% | 100% | 33 | 回答证据化后 Grounding 达标；剩余领域路由、术语覆盖、列表序号与舍入展示问题 |
| 3 | 100/100 | 30/30 | 100% | 100% | 0 | 所有自动化 AI 技术指标达标，0 未分类失败 |

历史 `80/100` 与 Day3 strict `64/100` 的下降不等同于单纯模型退化：审计确认严格 evaluator 新增 claim coverage、数值证据、ACL 和声明一致性要求；最终同一 strict evaluator 已达到 100/100。详细矩阵见证据目录。

## Retrieval Lock 复验

- 锁定文件 hash 与 Day3 基线完全一致：profile `15fc482e...ace2d`、hybrid `d76d74f9...e559a`、rag service `47948d64...0cd3`。
- Day3 权威基线：P95 `1451.071ms`、Recall@3/5 `100%/100%`、MRR `95.67%`。
- 本次正式 warm 复测：P50 `1802.260ms`、P95 `2408.614ms`、reranker P95 `2172.448ms`、hybrid P95 `202.995ms`；Recall@3/5 `100%/100%`、MRR `97.67%`、Critical Recall/Citation `100%/100%`、tenant leakage `0`。
- 结论：检索质量未退化，但当前性能门槛 FAIL。按 Retrieval Lock 规则未修改 embedding、dense、sparse、RRF、reranker、候选数或线程配置。

## 回归结果

- AI100 / Critical / Grounding / ACL / Citation / Prompt Injection / Cross-tenant / Cross-user：PASS。
- Backend + Day2 identity/security：`186 passed`。
- Python compileall：PASS。
- Frontend TypeScript + Vite：`3675 modules`，PASS。
- `run_project.bat`：提交前一次综合健康 PASS；最终 SHA 幂等复验在 PostgreSQL、Alembic 0019 与 Redis 通过后，Qdrant 安全探针连续 12 次读取/握手超时，最终 FAIL。容器只读审计显示 running、未 OOM、未重启，但本轮留下 11 个 `rag_r1_security_probe_20260808_1624*` 至 `..._162736_*` 临时集合。
- Browser smoke：登录页标题与路由正确，控制台 warning/error `0`；浏览器直接打开健康 JSON 被客户端拦截，Backend health 已由启动器独立验证。
- 未分类失败/错误：`0`。已分类失败：Retrieval P95、最终 SHA 一键启动 Qdrant probe 超时；治理待办：Golden human approval；运行残留：11 个本轮临时 probe 集合待人工确认后清理。

## 最大三个根因

1. 历史 evaluator 与 current strict evaluator 的契约差异未被显式审计，导致旧分数无法代表 claim-level、数值证据与 ACL 的正式 Gate。
2. Answer Pipeline 的身份边界与上下文优先级不完整，授权证据缺失时仍可能继续工具链，历史/工具/检索上下文缺少统一 fail-closed 顺序。
3. 回答未严格锚定授权 Citation 与经数据库验证的工具事实，领域/状态术语和展示舍入造成 strict grounding、Critical 与数值证据失败。

## Day3B 准入与剩余风险

当前 **不满足**进入 Day3B Release Drill：一是本次 Retrieval P95 `2408.614ms` 超过 `1500ms`；二是 Golden 100 项尚未完成人工审批；三是最终 SHA 一键启动被 Qdrant 安全探针超时阻断，并新增 11 个临时 probe 集合。按删除确认规则未自动删除这些集合，需用户人工确认后逐个精确清理。端到端 AI P95 为 `4147.546ms`，本阶段仅记录、未设独立 Gate。迭代 1/2 的中间 Prompt hash 未在当轮独立快照，最终 Prompt/Context/Service hash 已保存；这是证据完备性风险，不影响最终 strict 指标，但后续复盘应补强自动留痕。

## 回滚

代码回滚使用对本次闭环提交的常规 `git revert`，不得强制 reset。数据库无迁移、无写入；fixture 仅只读。运行态保持 candidate、alias `null`，无需 Alias 或 Snapshot 回滚。任务前恢复依据为项目盘检查点 `backups/phase3/20260808_220638227_DAY3A_RAG_AI_QUALITY_PRE`。

统一证据目录：`docs/codex/evidence/DAY3A_RAG_AI_QUALITY_20260808_220845/`。
