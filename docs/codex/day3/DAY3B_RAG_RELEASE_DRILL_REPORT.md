# Day3B RAG Release Drill 与回滚恢复闭环报告

## 1. 结论

DAY3B 在本报告所在闭环提交登记为 **PASS（本地开发/预发布等效）**。本轮完成正式 Snapshot 验证、故障注入补偿、Alias 切换、真实发布烟测、正常回滚、幂等回滚、replay 和最终回滚；最终状态刻意恢复为 `rolled_back/is_current=false/current_release_id=null/alias_target=null`，不代表生产发布或生产切流。

生产边界保持不变：`human_verified=false`、`production_human_signoff=false`、`production_cutover=false`，`EXTERNAL_PRODUCTION_GATE=PENDING`。本轮未进入 Day4。

## 2. 基线、检查点与证据

- RC 工作树：`E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807`
- 分支：`release/beta10d-agent-rc-20260807`
- 起始 SHA：`fd80d2a4393976aa893b4e63880c2be78c39fae9`
- PRE 检查点：`backups/phase3/20260809_174650317_DAY3B_RAG_RELEASE_DRILL_PRE`
- 证据目录：`docs/codex/evidence/DAY3B_RAG_RELEASE_DRILL_20260809_174650`
- 权威完整结果：`release/day3b_live_drill_attempt5.json`

检查点保存了 Git 状态、diff、未跟踪清单、关键哈希、数据库只读快照、Qdrant 初始状态与恢复说明。代码可回滚到起始 SHA 或 PRE 检查点；数据库/Qdrant 运行态已由演练本身回滚到安全终态。

## 3. Snapshot 与资产边界

- 正式 Collection：`rag_chunks_RAG-R1`
- 正式 Snapshot：`rag_chunks_RAG-R1-8606232973505508-2026-08-09-11-53-03.snapshot`
- Snapshot 验证：API listed=true，下载前缀可读=true；正式文件保留，未删除。
- 正式集合终态：green、8,339 points、1024 维、strict mode enabled、update queue 0。
- 6 个历史 probe 全部保留且未被引用、未被修改；本轮未创建或删除 Collection。

Snapshot 创建请求曾因 2.27GB 文件落盘超过客户端等待时间而超时；控制器只在“创建前不存在、创建后唯一新增、listed/readable 均成立”时接收该 Snapshot，未重复生成第二份正式文件。

## 4. 发布、故障注入与 Smoke

9/9 Release Gates 通过后，Candidate 完成 validated。首次 publish 使用受控 `_FailOnceSmokeQdrant` 注入 post-switch smoke 失败：操作按预期返回失败，`consistency_restored=true`，Alias 与 PostgreSQL current 均自动恢复为 null，补偿耗时 3,266ms。

随后真实 publish 成功，耗时 1,297ms，Alias 指向 `rag_chunks_RAG-R1` 且 PostgreSQL current 一致。Alias 路径完成固定 10 题预热后执行计时 smoke：

- 10/10 available、Expected Document hit、Citation integrity、Critical 全部 PASS；
- release identity 全部为 `RAG-R1`；
- P95 `907.883ms`，低于 1,500ms；
- AI RAG Critical 3/3、Unavailable 1/1、Security Refuse 1/1 PASS；
- 跨租户 hits=0、citations=0、明确拒绝；
- 无 fallback、无 ACL 放宽、无阈值下调。

## 5. 回滚、恢复与 Replay

- 正常 rollback：成功，7,922ms，Alias/current 恢复为 null；
- 第二次 rollback：成功且 `idempotent=true`，31ms；
- 回滚后 smoke：Qdrant green、Alias/current 均 null；runtime 以 `published_release_fact_mismatch` 拒绝，RAG API 返回 HTTP 503 `enterprise_rag_runtime_unavailable`，无 stale citation；
- replay validate/publish：成功；重复 publish `idempotent=true`；
- replay 最终 rollback：成功，765ms；
- 最终状态：`rolled_back/is_current=false/current_release_id=null/alias_target=null`。

## 6. RTO/RPO

- RTO 目标：300 秒；
- 故障注入补偿：3.266 秒；
- 正常 rollback：7.922 秒；
- replay 最终 rollback：0.765 秒；
- RTO：PASS；
- RPO：0；
- `kb_release_items` 聚合不变，正式 Collection points 8,339 不变。

## 7. 验证矩阵

- Backend + Day2 Memory + RAG + Release/Day3B 合并矩阵：269 passed，0 failed，0 errors；
- Python compile：PASS；
- TypeScript + Vite production build：PASS，3,675 modules；
- 浏览器：登录页标题及账号/密码/登录控件可见，1280px 下横向溢出 0，console warning/error 0；
- 最终 SHA `run_project.bat`：连续两次 PASS；两次结果保存于同一证据目录的 `runtime` 子目录。

## 8. 非通过尝试与最终修复

失败证据均保留而未覆盖：attempt1 暴露 smoke 证据不足并安全回滚；attempt2 遇到 Docker Desktop/WSL 运行态中断，readiness fail-closed 且未进入发布；attempt3 暴露 AI smoke 未注入 authoritative alias runtime 以及冷索引预热不足；attempt4 已通过 publish/alias smoke，但回滚后预期拒绝未被 smoke 转换成 PASS 证据。修复仅涉及运行态显式注入、完整固定样本预热、预期拒绝证据化和 Snapshot 超时后的唯一新增接收逻辑，未改变质量/性能/ACL 门槛。

attempt5 为唯一权威 PASS 运行，完整同次覆盖 readiness、admit、snapshot validate、failure compensation、publish、alias smoke、rollback、post-rollback smoke、replay、RTO/RPO 与最终状态。

## 9. 外部生产门禁

本地开发/预发布等效闭环已完成，但以下仍是生产外部门禁：

- 真实业务专家/生产审批人签署；
- 生产变更窗口、生产密钥和生产环境授权；
- 生产监控、告警、容量与灾备值班确认；
- 生产切流批准与回退责任人确认。

以上不得由自动化 Reviewer A/B/Arbitrator 冒充真人签署，也不影响本次 Day3B 开发验收 PASS。
