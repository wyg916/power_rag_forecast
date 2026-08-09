# Day3A2 RAG 性能回归与 Qdrant 运行时卫生闭环报告

## 1. 结论

DAY3A2 在本报告所在提交登记为 **PASS（开发/预发布等效）**。RAG-R1 仍保持 Candidate、`is_current=false`、alias 空、snapshot 0；本阶段未执行 Day3B 的 Snapshot、Alias 切换、Release current、Production publish 或模型激活。

Golden 100 的自动化多角色复核只批准 DEVELOPMENT/PREPRODUCTION：`human_verified=false`、`production_human_signoff=false`、`production_cutover=false`。真人生产审批继续登记为 `EXTERNAL_PRODUCTION_GATE=PENDING`，不伪造真人签署，也不阻塞后续 Day3B 开发验证。

## 2. 检查点与范围

- 起始提交：`fd4d4fe81f37b5efcef88997ac0074828cb24024`
- PRE 检查点：`backups/phase3/20260809_132913421_DAY3A2_RAG_PERFORMANCE_PRE`
- 证据目录：`docs/codex/evidence/DAY3A2_RAG_PERFORMANCE_20260809_132913`
- 修改范围：正式验收参数传递、只读健康探针、Golden 多角色开发/预发布判定及对应测试；未改 Answer Prompt、Answer Contract、IdentityContext Answer Pipeline、Claim/Citation Validator、ACL 或 Grounding 规则。

## 3. 1451ms 与 2408ms 对账结论

本次回归不是单一因素，证据支持以下分类：

1. **CONFIG REGRESSION（主代码缺陷）**：formal50 命令行虽传入 `max_length=32`，旧分支却未把 CLI 值写入运行环境，实际继承模型 profile 的 `max_length=128`。失败报告中 reranker P95 为 2172.448ms，是总 P95 2408.614ms 的主要贡献项。修复后实际配置为 max_length 32、candidate 3。
2. **BENCHMARK CONTRACT CHANGE（独立差异）**：1451ms 基线问题资产 SHA 为 `1e526...`，当前正式问题资产 SHA 为 `422ece...`，50 题中 21 题文本不同。因此 1451 与 2408 不能视为完全相同数据集的纯时间序列。
3. **QDRANT/RUNTIME DEGRADATION（环境放大项）**：磁盘饱和、可用内存约 523MB 与分页活动下的首次试跑 P95 为 4299.523ms，Qdrant P95 1339.593ms；环境稳定且模型预热后，同一实现的 Qdrant P95 降至 117.543–194.655ms。
4. **CACHE/IDENTITY SCOPE COST（未发现新增代码回归）**：检索生产代码与 Identity/ACL 锁定实现哈希未变；50Q 质量、跨身份安全回归和只读集合状态均保持通过。没有证据支持通过削弱 ACL 或修改 cache scope 来换取性能。

## 4. 性能验收

在当前正式 50Q、同一 Collection、max_length 32、candidate 3、一次 warmup 后完成三次独立正式运行：

| Run | P95 | Recall@5 | Critical Recall@5 | MRR | Citation | Qdrant P95 | Rerank P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 897.730ms | 100% | 100% | 94.67% | 100% | 194.655ms | 798.856ms |
| 2 | 967.157ms | 100% | 100% | 94.67% | 100% | 117.543ms | 820.621ms |
| 3 | 1021.528ms | 100% | 100% | 94.67% | 100% | 144.796ms | 942.389ms |

三轮均低于 1500ms，不选择性取最快值；全部 `write_count=0`，前后均为 8,339 points，集合状态 SHA 不变。

## 5. Golden 100 开发/预发布审批

- Reviewer A：100/100、Critical 30/30、Grounding/Citation/ACL 100%、幻觉数字 0。
- Reviewer B：独立逐题重计数，与 Reviewer A 指标一致。
- Arbitrator：一致性与题目身份精确性 PASS。
- DEVELOPMENT/PREPRODUCTION：PASS。
- EXTERNAL_PRODUCTION_GATE：PENDING。
- `human_verified=false`，`production_human_signoff=false`。

## 6. Qdrant 临时资产清理

删除前对限定授权的 11 个名称逐项核验：名称符合 probe 正则；Qdrant 服务日志存在本轮创建记录；均为 0 points、0 snapshots；PostgreSQL Release/Candidate 仅引用 `rag_chunks_RAG-R1`；alias 列表为空；正式 Candidate 配置只指向 `rag_chunks_RAG-R1`。清单全部 `safe_to_delete=true` 后才按精确名称逐个删除，11 次 HTTP 200/result true，随后逐项 HTTP 404。

删除后正式集合为 green、8,339 points、1024 维 Cosine、strict mode enabled、snapshot 0、alias 空。另有 6 个更早的 probe 集合不在本次授权范围，来源未纳入本次证明，因此原样保留；未知资产、alias、snapshot 删除数均为 0。

健康模式只执行 TLS、鉴权、集合元数据、向量维度、strict mode 与 alias 的只读检查，`write_operations=0`、`persistent_candidate_mutations=0`。需要创建/删除临时集合的安全探针保留为显式 `--mode security`，不再由一键启动调用。

## 7. 验证与回滚

- 相关 Backend、Day2 Memory、RAG、安全与启动契约矩阵：187 passed，0 failed，0 error。
- 前端：TypeScript 与 Vite 生产构建 PASS（3675 modules）。
- 浏览器：登录页路由、账号/密码/登录按钮可见，console warning/error 0；后端 `/api/health` HTTP 200。
- 一键启动：健康模式不创建 Collection，统一 RC 服务闭环 PASS；最终提交的连续两次结果见同目录运行证据。

代码回滚可恢复至起始提交或 PRE 检查点。11 个被删集合均为空且 snapshot 为 0，不包含业务数据；若需复现实验，只能通过显式 security probe 新建独立临时集合，不从正式 Candidate 恢复，也不得触碰正式 Collection/Alias/Release。

## 8. 准入边界

Day3B **开发验证准入 YES**；生产准入 NO。Day3B 必须作为独立任务执行其 Snapshot/Alias/Smoke/Rollback/RTO/RPO 门禁，并在生产发布前完成外部真人生产签署。
