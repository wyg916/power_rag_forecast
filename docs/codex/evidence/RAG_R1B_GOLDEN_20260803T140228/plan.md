# RAG-R1B 黄金集治理计划与前置检查点

## 任务边界

- 工作树：`E:\智能运营分析项目_worktrees\beta10d_rag_r1b_golden_set`
- 分支：`beta10d/rag-r1b-golden-set`
- 基线 HEAD：`ec78c569bd4036f23341e40b2d4d212a6f85177c`
- 仅修改任务文档登记的白名单文件和本证据目录。
- 不访问或修改数据库，不执行迁移，不修改生产代码、公共配置、Compose、公共 API、release、alias 或 snapshot。
- 未经真实人工确认，候选题保持未批准状态，不声明正式黄金集 PASS。

## 前置检查点（2026-08-03T14:02:28+08:00）

- `git status --porcelain=v1 --branch`：仅 `## beta10d/rag-r1b-golden-set`，工作树干净。
- `git diff --stat`：空。
- `git diff --cached --stat`：空。
- 未跟踪文件：无。
- 已修改文件：无。
- 本任务已跟踪文件：
  - `scripts/rag_r1_candidate_ai_acceptance.py`
  - `tests/evaluation/ai_assistant_eval_questions.json`
  - `tests/evaluation/day8_golden_questions.json`
  - `tests/evaluation/phase5_base_30_questions.json`
  - `tests/evaluation/rag_r1_retrieval_golden_50.json`

### 关键文件 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| `tests/evaluation/rag_r1_retrieval_golden_50.json` | `fdde7a6a517a61b8340c1b8e82efea3766c74db9a6f4dc7106912c1205d4099c` |
| `tests/evaluation/ai_assistant_eval_questions.json` | `d3ab216f16449a80a422cfeac00dbb639d38cf9bdac8f655e5817d731d595ed7` |
| `tests/evaluation/phase5_base_30_questions.json` | `a91030f160f23e5c445d17993f56a531058fbd7152575c771e94e3fbd3c7a7b0` |
| `tests/evaluation/day8_golden_questions.json` | `5a24abd11adfc045e22dcc22f35ce2331052e633b79af2e7af92c80e2ca5a527` |
| `scripts/rag_r1_candidate_ai_acceptance.py` | `b69bfb39b4afb2900f20703991645ac3864ba3a0bb0b8a6c5d8797602b08c90b` |

## 环境与数据库影响

- Windows：`Microsoft Windows NT 10.0.22000.0`
- PowerShell：`5.1.22000.2538`
- Python：`3.11.9`
- Git：`2.55.0.windows.3`
- 数据库影响：无；本任务不连接数据库，不产生 schema、迁移或数据变更。

## 执行计划

1. 盘点四份既有评测题库和现有失败证据，建立字段、ID、critical 与来源映射。
2. 治理 Retrieval 50 和 AI 100 候选，补齐文档版本、Chunk、Citation、Claim、工具路由、拒答、ACL、评分及双人审核字段。
3. 对失败结果逐题归类；仅在白名单内修复评测夹具和评测器的 fail-closed 问题。
4. 生成 25 题一批的人工审核材料及 critical 汇总。
5. 运行定向测试、指标计算、敏感扫描与白名单检查，记录正式指标和待人工确认项。
6. 提交单一任务提交；不 merge、cherry-pick、rebase 或发布。

## 回滚基线

- 完成提交后以该单一提交作为回滚单元，可使用 `git revert <本任务提交 SHA>` 恢复到本检查点。
- 提交前若需回退，已跟踪白名单文件可从基线提交逐文件恢复；新增文件需按仓库删除规则逐一经人工确认后处理。
- 无数据库恢复步骤，因为本任务无数据库影响。
