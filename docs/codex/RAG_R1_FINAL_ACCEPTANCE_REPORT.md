# RAG-R1 最终集成与发布验收报告

## 1. 最终结论

- **RAG-R1：NOT PASS**。
- **Candidate 发布：NO**。
- **生产切换：NO**。
- **进入原 Day 9 / Day 10：NO**。
- 未执行发布、alias 切换、快照创建、回滚演练或 Candidate→Published 状态变更。

阻断项为 OCR/VLM 人工真值门禁、AI 100 题门禁和端到端检索性能门禁。安全、迁移回放、数据库导入幂等、Qdrant 权限、API/UI、隔离全量回归已经通过，但不能抵消任一硬门禁失败。

## 2. 集成边界与代码基线

| 项目 | 结果 |
|---|---|
| Day 8 基线 | `bc36715d6943c212197d2e3dce5d8f2c6949bd08` |
| Day 8 远端核验 | `origin/beta10d/day8-execution` 精确指向上述提交 |
| 最终集成分支 | `beta10d/rag-r1-final-integration` |
| 验收实现 HEAD | `9082d9acec7247cd3f81569ee3da85466a2b80aa` |
| 文档收口 HEAD | 本报告所在提交 |
| ingestion 参考分支/提交 | `codex/rag-enterprise-ingestion` / `4cce50bf40fe1b50ddbe3bdd62e2c33aaf657227` |
| runtime 参考分支/提交 | `codex/rag-enterprise-runtime` / `c79671c82b2b2cd6deedc0f9cb136349fc3d0b1d` |

两条 RAG 支线没有整分支盲合并；依据 `docs/codex/PARALLEL_INTEGRATION_REGISTER.md` 登记的契约和提交定向接收，并在 Day 8 后以逐包提交处理迁移、运行时、发布治理、UI 与验收器冲突。Day 8 是当前分支 merge-base 且为祖先；验收实现 HEAD 相对 Day 8 包含 48 个提交、212 个文件、22,042 行新增。

## 3. 可回滚检查点

- 代码检查点：Day 8 完整提交 `bc36715d…`；本轮代码可按提交逆序使用 `git revert` 回滚，不使用破坏性 reset。
- 数据库检查点：迁移回放在一次性 Schema/受限角色中完成，public 前后 revision、结构 SHA 和内容保持一致，临时对象残留 0；当前数据库只接受了预期的 `0018_rag_enterprise_r1` 与 RAG-R1 Candidate 数据。
- Qdrant 检查点：当前 alias `rag_chunks_current` 目标仍为 NULL、快照 0；未发生需要恢复的 alias 切换。
- 运行配置检查点：外部 `model-profile.env` 的原值已留存于项目盘检查点；若回退，恢复该文件并重启受限本地运行时。
- 数据恢复前提：如需降级到 `0017_day6_operational`，必须先恢复对应业务备份，并确认 0018 后没有新增 RAG 事实；本轮未执行降级。

## 4. 数据库与 Candidate 状态

| 项目 | 验收结果 |
|---|---|
| Alembic head | `0018_rag_enterprise_r1` |
| 隔离回放 | PASS：head→0017→head，两个 head 结构 SHA 均为 `da429eb82a09c94a9cd8ab6b8e0dc463ac38e6772e132f1346684ec7704830b0` |
| 当前 public 结构 | 73 tables / 8 views / 47 sequences / 37 functions |
| 当前 public 结构 SHA | `15d4fd97a193c57b6b3bc0b6ad484902be2463cce3048fd3cb8fecd7b7e208be` |
| Candidate 导入幂等 | PASS：重复导入未产生重复事实 |
| Release 状态 | `RAG-R1` / `candidate` / `is_current=false`；validated/published/rolled_back/superseded 均为空 |
| 83 个 release items | published 45 / isolated 24 / duplicate 14 / damaged 0，终态 83/83 |
| Candidate 规模 | 45 documents / 8,339 chunks / 0 assets |
| 当前 RAG 总量 | 85 documents / 45 versions / 8,384 chunks / 0 assets / 1 release |
| 非预期数据库变化 | 0 个已知项 |

证据：`docs/codex/evidence/RAG_R1_INTEGRATION_20260802_141900/21_migration_replay/`、`docs/codex/evidence/rag_r1_final_integration/database/post_candidate_snapshot.json/`。

## 5. Qdrant 与模型运行态

| 项目 | 验收结果 |
|---|---|
| Qdrant | v1.18.2，镜像 digest `sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c` |
| Candidate collection | `rag_chunks_RAG-R1`，8,339 points，strict mode，1024 维 |
| 当前 alias | `rag_chunks_current` → NULL |
| 快照 | 0 |
| 网络与权限 | 仅 `127.0.0.1`、TLS；无 key 读拒绝、只读 key 可读但写拒绝、管理 key 临时探针成功 |
| 持久 Candidate 变更 | 权限探针前后 0 |
| Embedding | `sentence_transformers` / `BAAI/bge-large-zh-v1.5` / 1024 维 / 版本 `sha256:a6854…` |
| Reranker | `bge-reranker-v2-m3` / BGE / `sha256:2a581…`；CPU、batch 8、max length 128，无 fallback |

证据：`docs/codex/evidence/rag_r1_final_integration/qdrant_preflight_final.json`、`qdrant_security_probe_final.json`、`runtime_profile_rerank_128.json`。

## 6. 正式门禁矩阵

| 门禁 | 阈值 | 实测 | 结论 |
|---|---|---|---|
| OCR/VLM | 30 页人工标注；CER≤5%；表格 F1≥0.90；定位 100%；编造数字 0 | 人工标注 0/30；其余指标 NOT_MEASURED；4 个 OCR-required 文档、140 源页、Candidate assets 0 | **FAIL** |
| Retrieval 50 | R@3≥90%；R@5≥98%；MRR≥85%；critical 100%；citation 100% | R@3 100%；R@5 100%；MRR 96.67%；critical 15/15；citation 100% | PASS |
| Retrieval 性能 | 端到端 P95≤1.5s | P50 4,261.9ms；P95 6,175.825ms；hybrid core P95 869.666ms，reranker P95 6,026.686ms | **FAIL** |
| AI 100 | ≥97/100；critical 30/30；citation 100%；grounding≥98%；编造数字 0；拒答 100% | 80/100；critical 16/30；citation 100%；grounding 93%；hallucinated digits 0；拒答/不可用 100% | **FAIL** |
| Security | 泄露 0；注入防护 100%；无 key 拒绝；只读 key 写拒绝 | 149 passed；真实 Qdrant 权限探针全部符合 | PASS |
| 可靠性/幂等 | GET/search 无写；import/publish 幂等 | GET/search 无写、Candidate 重复导入幂等、发布服务幂等测试通过 | PASS |
| UI/API | 多分辨率无溢出/裁切/伪按钮/console error | 1024/1366/1440/1672/1920 全部通过；前端构建 3,675 modules PASS | PASS |
| 全量回归 | failed=0、errors=0；skip 分类 | 隔离正式回归 900 passed / 30 skipped / 0 failed / 0 errors；skip 已逐组分类 | PASS |

Retrieval 黄金集的 `human_verified=false`，本报告不将其表述为人工核验。AI 引用离线复核为 446/446 有效，但复核不放宽评分，最终仍为 80/100。公开发布前路径因 alias/current 为空而拒绝 Candidate，符合 fail-closed 设计。

## 7. 回归、跳过与诊断分类

- 正式结果：受限角色、一次性 Schema 的隔离回归为 900 passed / 30 skipped / 0 failed / 0 errors，public 指纹一致，临时 Schema/角色残留 0。
- 30 项 skip：T003 真实批次/专用数据库 19 项；Phase5 C2 旧报告数据库；Phase5 D7 旧策略数据库；旧 AI RAG ranking 2 项已被本轮 Candidate 50 题门禁替代。没有任何 skip 用来豁免当前三个失败门禁。
- 裸环境诊断曾得到 834 passed / 34 failed / 30 skipped / 32 errors，根因是数据库保护器禁用数据库、Phase5 A2 需要隔离 runner、模型/电价资产未挂载；该结果只保留为环境诊断，不作为正式验收结果。

证据：`docs/codex/evidence/rag_r1_final_integration/final_regression/pytest_isolated_junit.xml`、`pytest_isolated_runner.json`、`skip_classification.json`。

## 8. 发布与回滚判定

由于 OCR/VLM、AI 和检索性能存在硬失败：

- 没有调用发布 worker；Release 保持 Candidate。
- 没有创建发布前快照；Qdrant snapshots=0。
- 没有切换 `rag_chunks_current` alias；目标保持 NULL。
- 没有执行回滚演练，因为没有合法发布可以回滚。
- 发布/回滚 RTO、RPO 均为 NOT_MEASURED，不能宣称达标。

若后续所有门禁通过，发布前必须先创建并校验快照，再由受限发布 worker 执行 Candidate→Published 与 alias 原子切换；失败时恢复数据库业务备份、恢复外部运行配置，并根据快照/旧 alias 精确回切。任何 collection 删除均需另行明确确认，本轮未删除。

## 9. 剩余阻断与下一次准入条件

1. 由人工完成至少 30 页 OCR/VLM 真值标注，计算并达到 CER、表格 F1、定位和数字真实性阈值。
2. 在当前 0018 契约的隔离业务夹具上修复 AI 工具链与领域判定，使 100 题≥97、critical 30/30、grounding≥98%，且维持 citation/拒答/数字真实性门禁。
3. 将包含 BGE reranker 的端到端检索 P95 降至≤1.5s；当前 CPU reranker 是主要瓶颈，不能用仅统计 hybrid core 的方式替代正式指标。
4. 三项全部关闭后，重新执行安全、幂等、UI、隔离全量回归及发布前快照验证；在此之前发布继续 NO。

## 10. 证据索引

- OCR/VLM：`docs/codex/evidence/rag_r1_final_integration/ocr_vlm_gate.json`
- Retrieval：`docs/codex/evidence/rag_r1_final_integration/retrieval_candidate_50_rerank128.json`
- AI 100：`docs/codex/evidence/rag_r1_final_integration/ai100_candidate_domainfix/ai_100_report.json`
- 引用复核：`docs/codex/evidence/rag_r1_final_integration/ai100_candidate_final/citation_revalidation.json`
- Security：`docs/codex/evidence/rag_r1_final_integration/security_junit.xml`
- Qdrant：`docs/codex/evidence/rag_r1_final_integration/qdrant_preflight_final.json`、`qdrant_security_probe_final.json`
- UI：`docs/codex/evidence/rag_r1_final_integration/knowledge_ui_browser_acceptance.json`
- Regression：`docs/codex/evidence/rag_r1_final_integration/final_regression/`

