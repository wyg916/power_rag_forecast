# Day3 RAG 预生产门禁收口报告

## 1. 结论

**DAY3 RAG PREPRODUCTION = NOT PASS。**

当前 RC 已关闭检索性能门禁和 Expected Chunk / Top-K 评测契约问题，但 AI100 严格复算仅 `64/100`，Critical 仅 `16/30`，Grounding 仅 `79%`，同时 AI100 的 ACL 响应契约仅 `90%`。这些结果均低于硬门槛，故按发布前置条件停止在 AI 门禁；Snapshot、Alias switch、切换后 Smoke、Rollback、Alias recovery 及 RTO/RPO 实测均未执行。未连接外部生产环境，未执行生产发布或切流。

## 2. 唯一事实基线

- RC 分支：`release/beta10d-agent-rc-20260807`
- 起始 SHA：`622fd16fc725eab3394793b54cb96dcb447eded8`
- 最终 SHA：本报告所在收口提交
- PRE checkpoint：`backups/phase3/20260808_191633225_DAY3_RAG_PREPRODUCTION_PRE`
- 证据目录：`docs/codex/evidence/DAY3_RAG_PREPRODUCTION_20260808_191700`
- PostgreSQL：Alembic `0019_memory_identity_safety`
- Release：`RAG-R1`，`status=candidate`，`is_current=false`
- Qdrant：`rag_chunks_RAG-R1`，8,339 points，strict mode/TLS/只读运行；`rag_chunks_current` 当前无目标，snapshot 数量 0
- Embedding：`BAAI/bge-large-zh-v1.5`，1024 维，版本 `sha256:a6854a4b265bc6c7159d02927ece3548e63e7b57cf49deee2a77b94bbb0ec3fa`
- Reranker：`bge-reranker-v2-m3`，版本 `sha256:2a581f058542bd175695f8f92097b7aa4fbdac637ad486739f26e4cbc11ca159`

## 3. 门禁总表

| 门禁 | 要求 | 当前实测 | 结论 |
|---|---:|---:|---|
| warm cache-miss E2E P95 | `<1500ms` | `1451.071ms` | PASS |
| Recall@3 / Recall@5 / MRR | `>=90% / >=98% / >=85%` | `100% / 100% / 95.67%` | PASS |
| Critical retrieval / Citation | `100% / 100%` | `100% / 100%` | PASS |
| Expected Chunk v2 契约 | 合理、可复现、保留旧标注 | 9/9 checks；must-have 100% | PASS |
| AI100 Overall | `>=97/100` | `64/100` | **FAIL** |
| AI Critical | `30/30` | `16/30` | **FAIL** |
| AI Grounding | `>=98%` | `79%` | **FAIL** |
| AI Citation | `100%` | `100%` | PASS |
| 检索 ACL/tenant 隔离回归 | 0 unauthorized | 0 unauthorized；专项测试通过 | PASS |
| AI 响应 ACL 契约 | `100%` | `90%` | **FAIL** |
| 安全回归 | 0 未分类失败/错误 | 通过 | PASS |
| Snapshot/Alias/Smoke/Rollback | 全部 PASS | 前置门禁失败，未执行 | BLOCKED |
| RTO/RPO | 有实际测量 | 未执行发布演练，未测量 | BLOCKED |
| Day2 回归 | 不退化 | 通过 | PASS |
| 一键启动 | PASS 且幂等 | 连续 2 次通过 | PASS |

## 4. 检索性能与冻结配置

当前 RC 的首次 warm cache-miss 50Q 基线为 P50 `5212.100ms`、P95 `10944.765ms`。最终冻结配置连续两次低于 1500ms：先行复验 P95 `1346.035ms`，权威终跑 P50 `1063.043ms`、P95 `1451.071ms`，且两次 R@3、R@5、Critical、Citation 均为 100%，MRR 均为 95.67%。

冻结配置：

- `RAG_PROFILE=enterprise`
- `RAG_TOP_K=5`
- rerank input candidate limit `3`
- Qdrant dense/sparse 各取 `9`
- reranker batch `8`，max length `32`
- CPU torch threads `6`，interop threads `1`
- `torch_fp32`，tokenizer parallelism 关闭
- BGE embedding/reranker 预热；无 fallback

权威终跑阶段 P95：

| 阶段 | P95 |
|---|---:|
| auth/ACL | `0.854ms` |
| query embedding | `525.240ms` |
| sparse retrieval | `116.757ms` |
| dense retrieval | `156.113ms` |
| Qdrant | `165.615ms` |
| RRF | `0.506ms` |
| duplicate merge | `0.119ms` |
| parent expansion | `0.028ms` |
| content security | `17.254ms` |
| reranker | `805.048ms` |
| citation assembly/hash | `0.577ms` |
| serialization | `0.183ms` |
| cache bookkeeping | `0.157ms` |
| E2E total | `1451.071ms` |

查询预处理未作为独立计时段输出，而是包含在请求准备及各检索阶段总耗时内；本报告不为其虚构独立数值。终跑请求写入数为 0，collection 前后均为 8,339 points 且状态哈希一致，alias 前后均为 null，tenant leakage 为 0，ACL negative probe 拒绝率 100%，运行时未加载 admin key。

一键启动现在自动加载受 Git 管理且不含密钥的 `deploy/rag-r1/preproduction-profile.env`，缺失时 fail-closed，不需要人工修改环境变量。

## 5. Expected Chunk / Top-K v2 契约

权威旧标注中有 5 题要求的 exact chunks 超过 Top-K=5：`R1-RET-011`、`012`、`019`、`043`、`045`。新契约未删除题目、未改写问题、未删除旧标注、未降低既有 Recall/MRR/Critical/Citation 阈值，而是将证据区分为：

- `must_have_evidence`：Top-K 内至少存在一个来自预期文档且 Citation 有效的证据块；
- `supporting_evidence`：完整保留旧 exact chunk 标注，用于透明报告辅助证据覆盖，不再要求 Top-5 同时容纳超过 5 个 mandatory chunks。

审计结果为 9/9 checks PASS；50/50 问题哈希一致，R@3/R@5 `100%/100%`，MRR `95.6667%`，Critical `100%`，Citation `100%`，must-have full coverage `100%`。辅助证据按题完整覆盖 `38%`，按 chunk 覆盖 `34.8837%`，未隐藏低覆盖事实。

- 权威来源 SHA-256：`1e526ee2f4c2feda72a27c52fdc08b68888fccd02be2302110e45c1e2674df7e`
- v2 契约 SHA-256：`0020dabe4a2f6ab59a8e72b9f106fb00de2a4d81659dfdf223500abbe773c613`

## 6. AI100 / Critical30 严格复算

完整 100Q 在隔离夹具数据库及只读 RAG Candidate 上执行。报告声明结果为 79/100，但逐题严格复算发现 15 个 declared-pass mismatch，因此本报告只采用严格复算：

- Overall：`64/100`，失败 36
- Critical：`16/30`
- Grounding：`79%`
- Citation integrity：`100%`
- refusal accuracy / unavailable precision：`100% / 100%`
- tool success：`0%`，tool fact mismatch `19`
- ACL accuracy：`90%`
- hallucinated digits：4，hallucination rate `4%`

Failure Taxonomy（分类可重叠）：

| 类别 | 题数 |
|---|---:|
| answer reasoning / claim grounding | 21 |
| metric/time mismatch | 10 |
| tool routing | 10 |
| source metadata mismatch | 10 |
| AI 响应 ACL 契约 | 10 |
| domain routing | 8 |
| hallucination | 4 |
| evaluation consistency | 36 |

当前证据没有证明 retrieval miss、rerank error、wrong chunk、context truncation、context ordering 或 citation mismatch，故这些类别登记为“当前证据未归因”，不等价于证明其绝不存在。

主要阻塞根因：

1. AI 技术门槛本身未达到；
2. 10 个 tool+RAG 项的业务工具/来源契约返回失败或 unavailable，并伴随 run_id/source_type/ACL 契约不一致；该证据不证明数据库发生写入，也不授权用 seed/fallback 伪造成功态；
3. Golden governance 尚未完成：100 题待人工批准，90 题映射待定，approved=0，human_verified=0；
4. 声明汇总与逐题严格复算存在 15 题漂移。

Reviewer A、Reviewer B、Arbitrator 的确定性代理共识仅验证了测量一致性，不能把失败结果变成准入通过。`automated_consensus_verified=true`，但 `human_verified=false`、`production_human_signoff=false`、`production_cutover=false`。

## 7. Citation、ACL 与安全

- 50Q Citation integrity 100%，AI100 Citation integrity 100%。
- 最终 50Q 中 document/chunk/quote hash 校验通过，无 cross-tenant retrieval/citation；ACL negative probe 被拒绝。
- 后端相关回归 176/176 通过，覆盖检索、Citation、内容注入、Qdrant 安全、AI acceptance、OCR、认证、Day2 Identity/Memory、API permission matrix 与启动器。
- Day2 Identity/Security 定向复验 64/64 通过。
- API 权限矩阵已与生成器同步：204 method-path、189 path；`--check` 通过。
- AI100 的 10 个 ACL 项仍失败，因此这里只确认检索/平台隔离回归通过，不把 AI 响应 ACL 误报为通过。

## 8. OCR / 人工代理边界

30 页 OCR 代理共识状态为 `AI_CONSENSUS_VERIFIED`，consensus SHA-256 为 `852aa02683285854615447f62506adcb1ceac82bb4c35467a72fd168bcf490eb`。这是 AI consensus proxy，不是 human gold CER/F1；`human_verified=false`、`production_human_signoff=false`，继续登记为外部生产门禁。

## 9. Snapshot、Alias、Rollback 与 RTO/RPO

AI、Critical、Grounding 和 AI 响应 ACL 前置门禁未满足，因此严格跳过：

- snapshot 创建/校验；
- Candidate 发布与 alias switch；
- switch 后 health/retrieval/AI/ACL smoke；
- rollback、alias recovery 与回滚后 smoke；
- alias switch duration、rollback duration、snapshot restore duration 测量。

所以不存在可报告的 PREPRODUCTION_EQUIVALENT_RTO/RPO 数值，也不虚构生产 SLA。最终稳定边界保持：release candidate/is_current=false，alias target=null，snapshots=0。

## 10. 回归与运行验收

- Python 相关回归：176 passed，0 failed/error；Day2 Identity/Security 复验 64 passed。
- 最终收口定向复验：77 passed；v2 契约和 AI 代理共识再次生成后均与权威证据逐字节 SHA-256 一致。
- Frontend：TypeScript + Vite build PASS，3675 modules transformed。
- Browser：本地登录页渲染 PASS，2 个输入框、密码框和提交按钮可见，warning/error console 记录为 0；未使用或读取任何密码，未把未登录页面冒充成业务全流程。
- `run_project.bat`：`NO_BROWSER=1` 连续运行 2 次 PASS；PostgreSQL、Redis、Qdrant、Backend、Celery、Frontend/combined health 正常，重复启动幂等。
- 一键启动中的 Qdrant probe 可清理，持久 Candidate 写入数 0；未创建 snapshot、未切 alias。
- 初次相关回归出现 1 个已分类的 Day2 API permission matrix 计数漂移（期望 202、实际 204），同步生成物和断言后最终 176/176 通过，无未分类失败或错误。

## 11. 数据库、迁移与外部影响

- 未新增 0020；Alembic 保持 0019。
- 未执行数据库迁移、全表更新/删除或正式业务写入。
- AI100 使用隔离夹具数据库；RAG/Qdrant 正式验收均为只读。
- 未连接外部生产环境、未调用外部生产 Provider、未激活模型、未创建正式生产 release。

## 12. 回滚方法

1. 代码与配置：对本报告所在 Day3 提交执行 `git revert <DAY3_COMMIT_SHA>`；不使用破坏性 reset。
2. 启动配置：上述 revert 会同时移除一键启动对 `deploy/rag-r1/preproduction-profile.env` 的接线，恢复 Day2 启动行为。
3. 数据库：本任务无迁移和业务写入，无数据库回滚动作。
4. Qdrant：本任务未创建 snapshot、未切 alias、未改变 collection；无需数据面回滚。
5. 审计恢复点：`backups/phase3/20260808_191633225_DAY3_RAG_PREPRODUCTION_PRE` 保存起始状态、diff、未跟踪清单、关键哈希与数据库影响说明。

## 13. 下一步建议

继续停留在 Day3，不进入生产。下一轮只处理当前阻塞根因：

1. 完成不可变 AI100 映射和人工/等价治理批准，消除 declared/strict 汇总漂移；
2. 修复真实业务工具与来源契约的可用性、run_id/source_type/ACL 传播，禁止 seed、fallback 或前端成功态补齐；
3. 针对共享的 grounding、domain/source metadata、数字幻觉根因做通用修复，不做逐题 hardcode；
4. 重新完整运行 AI100/Critical30；只有 Overall、Critical、Grounding、Citation、ACL、安全和 Golden 契约全部达标后，才允许执行 Snapshot/Alias/Smoke/Rollback 演练并实测 RTO/RPO。

## 14. 核心证据

- 起点审计：`audit/start_audit.json`
- 权威性能终跑：`performance/frozen_consensus50_final_20of20.json`
- 连续性能复验：`performance/frozen_consensus50_c3_l32_t6_qdrant9_final.json`
- v2 契约审计：`quality/evidence_contract_v2_final_audit.json`
- AI100 严格报告：`quality/ai100_run/rag_r1_candidate_ai_100_formal.json`
- AI 代理共识/阻塞分类：`quality/ai100_proxy_consensus.json`
- OCR 代理边界：`audit/ocr_consensus_validation.json`
- 后端最终回归：`regression/backend_relevant_final_junit.xml`
- Day2 回归：`regression/day2_identity_security_rerun_junit.xml`
