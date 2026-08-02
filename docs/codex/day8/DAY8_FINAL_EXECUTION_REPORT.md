# Day 8 正式知识库与 AI 助手证据链收口报告

## 1. 最终结论

- **Day 8 本地开发验收：PASS。**
- 正式知识语料已完成受控导入、BGE 1024 维向量化、严格检索和引用闭环；严格模式下 Embedding、重排或引用链异常均 fail-closed。
- 知识库 20 题与 AI 助手 30 题最终全部通过；拒答、安全拦截和来源展示门禁均达到 100%。
- 本结论仅代表当前本地开发基线可继续后续工作，**不代表生产准入**；本轮未执行 Candidate 激活、Active 切换、生产切流或企业 RAG 分支合并。
- Day 7 原始 FAIL 历史保留不变；Day 7A 的脱敏修复记录亦未被本报告覆盖或改写。

## 2. 执行边界

| 项目 | 结果 |
|---|---|
| 权威工作树 | `E:\智能运营分析项目_worktrees\beta10d_day8_execution` |
| 分支 | `beta10d/day8-execution` |
| 起点提交 | `7e8284f3b3ed7c748482066552da33857e2915b8` |
| 开始检查点 | `E:\智能运营分析项目_备份\beta10d\20260802_140841222_DAY8_PRE` |
| 正式外网调用 | 0；Embedding 与 reranker 使用 E 盘既有本地模型并启用离线模式 |
| 数据库迁移 | 0；未新增或执行 Alembic 迁移 |
| 模型状态变更 | 0；Active 与 Day 6 Candidate 状态均未改变 |
| RAG 支线集成 | 0；未 merge、cherry-pick 或复制支线成果 |
| 文件删除 | 0 |

## 3. 实施结果

### 3.1 正式语料与元数据准入

- 正式语料入口收敛为 `knowledge_base`，不再把 Seed、Demo、fallback 或历史测试内容纳入正式检索。
- 正式文档必须具备 domain、source、version、generated/source update time、applicability、`data_origin=official` 等完整元数据。
- 导入批次和语料版本固定为 `day8-official-v1`，文档 ID 使用稳定的 `project://knowledge_base/...` 标识。
- 首次导入中 14 个缺 domain 的根文档被准入规则拒绝，门禁按预期 fail-closed；补齐显式领域映射后重试成功。
- 最终正式语料为 **34 个文档、39 个 active Chunk**；元数据完整文档 34/34。
- 重复执行结果为新增 0、未变化 34，文档数、Chunk 数和索引 digest 均保持不变，证明导入幂等。
- 本地库原有 6 个 Seed 文档/6 个 Chunk 保留用于追溯，但已从正式列表、统计、健康检查、向量刷新和检索链路隔离。

### 3.2 Embedding、索引与检索

- 正式 Chunk 39/39 使用 `bge-large-zh-v1.5` 生成有限、非 fallback 的 **1024 维**向量。
- 重建的 NumPy 向量索引内容 digest 为 `b45ceb80474e3435cee258b8702108a3d2e0530cec651e86bc477f0195d5231e`。
- 健康检查最终状态为 `normal`：正式文档 34、Chunk 39、已向量化 39、1024 维 39、fallback 0。
- 严格正式模式下，向量不可用、维度不为 1024、Embedding fallback/error、provider 非 BGE、reranker fallback/error、文件 fallback 开启或引用不完整时均返回不可用，不伪造成功答案。
- 关键词单路检索不再被严格模式接受为成功降级路径。

### 3.3 AI 助手与安全拒答

- AI 助手把完整 citation 作为证据可用性的必要条件，不再仅凭候选 items 判断成功。
- 对访问令牌、Bearer、系统提示词、测试哨兵、原样回显、内部密钥、数据库连接串和提示注入增加明确拒答。
- 模型调用错误且缺少证据时返回显式不可用，不使用成功态 fallback 补齐答案。
- 前端只补齐回答复制按钮的可访问名称，未新增假数据、未改变真实 API 边界。

## 4. 最终量化验收

最终验收文件：`docs/codex/evidence/DAY8_20260802/11_day8_rag_ai_acceptance_pass.json`。

| 门禁 | 结果 |
|---|---:|
| 知识库准确率 | 20/20，100% |
| 知识库来源展示率 | 100% |
| 知识库拒答率 | 100% |
| 知识库 P50 / P95 | 10010.802 / 16008.003 ms |
| AI 助手准确率 | 30/30，100% |
| AI 助手来源展示率 | 100% |
| AI 工具成功率 | 22/23，95.65% |
| AI 助手拒答率 | 100% |
| 未授权请求拦截率 | 100% |
| AI 助手 P50 / P95 | 9559.160 / 15157.467 ms |
| 最终失败案例 | 0 |

验收程序以 `persist=false` 运行，未把问答评测写入正式 QA 表；评测前后该表均为 0 行。

## 5. 测试与构建证据

- Day 8 后端干净矩阵：**96 passed**，覆盖正式语料准入、RAG、Phase 5 契约与恢复、知识 API、AI 端点、无证据拒答、秘密脱敏及 Day 6 安全回归。
- 前端相关契约复验：**14 passed**。
- TypeScript：PASS。
- Vite 生产构建：PASS，3675 modules transformed。
- 宽范围历史回归：138 passed、2 skipped、7 failed、24 errors。其异常未被伪装为通过：24 个 T002 error 来自本独立工作树没有历史未跟踪模型二进制；5 个旧 AI 用例在未加载本地数据库运行配置时失败；2 个 T004 旧断言分别与现行双 DSN 强制校验及仓库已有第 17 个迁移不一致。Day 8 相关干净矩阵已独立全绿。

关键证据：

- `docs/codex/evidence/DAY8_20260802/06_official_corpus_import_retry.json`
- `docs/codex/evidence/DAY8_20260802/07_official_corpus_idempotency.json`
- `docs/codex/evidence/DAY8_20260802/11_day8_rag_ai_acceptance_pass.json`
- `docs/codex/evidence/DAY8_20260802/13_day8_backend_clean.xml`
- `docs/codex/evidence/DAY8_20260802/15_final_readonly_audit.json`
- `docs/codex/evidence/DAY8_20260802/17_frontend_contract_tests_after.xml`
- `docs/codex/evidence/DAY8_20260802/18_frontend_tsc.txt`
- `docs/codex/evidence/DAY8_20260802/19_frontend_build.txt`
- `docs/codex/evidence/DAY8_20260802/20_day8_backend_final.xml`

## 6. 数据库与模型不变量

- 应用受限身份可见的最终 schema hash 为 `571060e080efc0e4406786f6f1f228ecd0ddc09c585ba1aecc46e372e9ed7f71`，可见列数 828；本轮迁移文件变更为 0。
- 既有完整指纹工具在 forecast/app 受限身份下不能读取 `alembic_version`，因此其前后两次证据都如实标记失败；本报告没有把该限制误报为完整数据库指纹 PASS，而是以受限身份可见结构审计、迁移零变更和模型注册表只读审计补充证明边界。
- Active 保持 `model_20260620_063015` / `features_140db8af25f9`，`is_active=true`。
- Day 6 Candidate 保持 `model_day6_operational_20260801_143802` / `features_day6_operational_589ede956c04`，状态 `validated`，`is_active=false`。

## 7. 敏感信息与分支隔离

- Day 8 证据中测试哨兵命中 0、长 Bearer 值命中 0。
- 三份后端 JUnit XML 各有 1 个 URI 模式命中，来源是秘密脱敏测试自身的 localhost 占位/脱敏字面量，不是真实凭据；对应 Day 6A redaction 测试已通过。
- 测试源和黄金题中保留安全攻击夹具属于预期，运行答案、报告和验收 JSON 均未回显其值。
- `rag_enterprise_ingestion` 保持 `4cce50bf40fe1b50ddbe3bdd62e2c33aaf657227` 且 clean。
- `rag_enterprise_runtime` 保持 `c79671c82b2b2cd6deedc0f9cb136349fc3d0b1d` 且 clean。
- `beta10d_day4_data_security` 保持 `7eaf8d3152f8ffe5bd983068a99145c9693b4925` 且 clean。

## 8. 回滚方案

### 8.1 代码回滚

在 Day 8 提交完成后，使用 `git revert <Day8提交>` 形成反向提交；不使用 reset、clean 或批量删除。

### 8.2 正式语料回滚

仅在人工确认后执行事务化回滚：先按 `metadata_json->>'import_batch'='day8-official-v1'` 只读核对文档 ID 和计数，再删除该精确批次文档；关联 Chunk 由既有外键策略处理。执行前必须再次保存计数、ID 清单和索引 digest，异常时 ROLLBACK，不做全表删除。精确导入文档清单保存在 `06_official_corpus_import_retry.json`。

### 8.3 向量索引回滚

索引目标仅为 `knowledge_pipeline/output/rag_vector_index.npz` 和 `knowledge_pipeline/output/rag_vector_index.json`。需要回滚时，先人工确认后从 Day 8 前检查点恢复这两个精确路径，或在语料事务回滚后按严格正式规则重建；不得递归清理目录。

## 9. 剩余风险与后续边界

- 本次 P50/P95 是 CPU 本地模型在并行负载下的功能验收结果，不作为生产性能基线；生产容量、SLA 和并发压测仍未完成。
- 企业 RAG ingestion/runtime 支线保持隔离，未评估为可直接整支合并；后续只能按独立任务包审查和集成。
- 未建设或声明 Qdrant、多租户生产隔离、正式调度、生产密钥或生产切流能力。
- Day 8 通过不改变预测主线的模型准入结论，也不授权 Candidate 晋升或 Active 切换。
