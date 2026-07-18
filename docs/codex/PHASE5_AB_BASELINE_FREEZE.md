# PHASE5_AB_BASELINE_FREEZE

## 结论

`PASS`

当前 PHASE5-A 与 PHASE5-B 的已验收状态已固化为进入 PHASE5-C 前的唯一回滚基线。

## 冻结对象

- 分支：`p5-frontend-ai-experience`
- 冻结前 HEAD：`251378fcf1b0fe83a058b12c7c647f126b454443`
- 冻结提交：以本文件所在提交为准
- A/B 总证据：`E:\智能运营分析项目_备份\phase5\20260718_195145245_PHASE5_AB_FINAL_RESULT`
- 前置检查点：`E:\智能运营分析项目_备份\phase5\20260718_204420818_PHASE5_AB_BASELINE_FREEZE_PRECHANGE`
- 冻结结果：`E:\智能运营分析项目_备份\phase5\20260718_204530045_PHASE5_AB_BASELINE_FREEZE_RESULT`

## 已固化内容

- A/B 33 项最终证据及逐文件 SHA256。
- 当前工作区全部变更/新增文件快照、完整 binary diff、状态、未跟踪文件清单和关键文件 SHA256。
- 隔离数据库 `intelligent_ops_phase5_ab_test` 的 schema-only SQL、完整 custom dump、表行数与 pg_restore 清单。
- A/B 最终测试、检索、Citation、100 题、读无副作用、运行健康、浏览器及 Artifact 校验证据。
- Git 分支、HEAD、远端、领先/落后状态、diff check 与敏感信息扫描结果。

## 回滚

1. 代码：优先回到本文件所在冻结提交；若只恢复单文件，使用 PRECHANGE 的 `workspace_snapshot` 或 `working_tree.diff`。
2. 数据库：将 `database_full.dump` 恢复到新建隔离数据库核验；不得覆盖正式数据库。Schema 可由 `database_schema_only.sql` 单独恢复。
3. A/B 证据：以总证据目录与 `phase5_ab_final_evidence.sha256` 为准。
4. Git：本冻结提交推送后，以远端同名分支为恢复锚点。

## 阶段边界

本文件只固化 PHASE5-A/B。正式数据库、正式预测、生产 Active、报告或策略写入均属于后续 PHASE5-C 独立任务，不包含在本冻结提交的运行副作用中。

## 已登记的非门禁问题

冻结时 A/B 专项回归为 `39 passed`。额外扩展运行旧助手/RAG/前端契约测试时出现 3 个非 A/B 门禁失败：旧助手用例缺少业务证据、旧 RAG 排序用例文本编码异常、旧复制按钮契约中文断言编码异常。原始日志保存在冻结结果目录，未将这些问题伪装为通过，也未在冻结任务中跨范围修复。
