# Day 7A T004 脱敏热修验收报告

## 1. 最终判定

**DAY 7 PASS**。

- 允许进入后续开发阶段：**YES**；
- 生产切换：**NO**；
- Candidate 激活：**NO**；
- Active 切换：**NO**。

原 `docs/codex/day7/DAY7_FINAL_ACCEPTANCE_REPORT.md` 的 Day 7 FAIL 是修复前的有效历史事实，本报告不删除、不覆盖该报告，仅记录后续 T004 最小热修与重判结果。

## 2. 基线、工作线与检查点

- 基线提交：`f22d4fd594cad7c57ba5cccd34d212d51b21f04a`；
- worktree：`E:\智能运营分析项目_worktrees\beta10d_day7a_t004_redaction_hotfix`；
- 分支：`beta10d/day7a-t004-redaction-hotfix`；
- 代码提交：`ff81a99d3e0b8b8bc0ed4f28927c156e384eddc6`；
- 文档收口提交 / 最终 HEAD：本报告所在第二提交，精确哈希由同证据目录最终状态记录和 `git rev-parse HEAD` 复核；
- 最终 Git 状态：clean；
- T004 前置检查点：`E:\智能运营分析项目_备份\beta10d\20260802_130403042_T004_PRE`；
- 检查点哈希自校验：PASS；
- 证据目录：`docs/codex/evidence/DAY7A_T004_20260802_130403042`。

## 3. 根因与最小修复

根因是 `backend/app/core/redaction.py` 的统一 `_SECRET_ASSIGNMENT_RE` 仅识别独立的 `secret`、`password`、`token`、`api_key` 等键名。下划线属于正则单词字符，既有 `\bsecret\b` 不会在 `jwt_secret_key` 中命中；原表达式也不识别 JSON 风格的带引号键名。

本次仅修改统一脱敏器和必要测试：

- `_SECRET_ASSIGNMENT_RE` 新增大小写不敏感的 `jwt[_-]?secret[_-]?key`；
- 支持无引号、单引号、双引号键名和赋值值，以及 `=`、`:` 与可选空格；
- 赋值类 Secret 保留键名与原引号，值统一替换为 `[REDACTED]`；
- 已脱敏输入再次处理结果不变；
- PostgreSQL/SQLAlchemy URL、查询参数、Bearer、password、token、api_key、secret、Authorization 的既有覆盖保持；
- 未修改异常主体契约、公共异常中间件、API 业务逻辑、数据库、模型、Provider、预测、前端或 RAG。

修改文件：

- `backend/app/core/redaction.py`；
- `tests/test_day6a_credential_redaction.py`；
- `docs/codex/day7/DAY7A_T004_HOTFIX_REPORT.md`；
- `docs/codex/TASK_STATUS.md`。

## 4. 新增测试覆盖

新增覆盖包括：

- 环境变量、普通文本、JSON；
- `=` / `:`、键值空格、大小写；
- 单引号、双引号、带引号 JSON 键；
- 下划线与连字符键名；
- 普通字符串、stdout、stderr、logging；
- exception message 与 exception chain；
- JSON、Markdown、TXT 证据；
- 重复脱敏幂等与已脱敏输入；
- 不传 `extra_secrets` 时的 JWT 和既有 password/token/api_key/secret/Authorization/数据库 URL 路径。

测试只使用由片段合成的指定 sentinel，不含真实密码、Token、JWT Secret、API Key 或完整正式连接串。

## 5. 实际测试与结果

### 5.1 原失败复现与修复后复验

原 Day 7 `.codex_tmp/day7_security_probes.py` 在修复前原样运行：

- 测试：`day7_security_probes.sentinel_redacted`；
- 输出通道：`redact_text_return`；
- 匹配数量：1；
- 结果：FAIL；
- 退出码：2。

修复后复跑同一探针：

- 输出通道：`redact_text_return`；
- 匹配数量：0；
- 结果：PASS；
- 退出码：0。

报告和证据均未记录 sentinel 所处的完整原始异常正文。

### 5.2 命令与统计

```powershell
E:\智能运营分析项目\.venv\Scripts\python.exe -m pytest tests/test_day6a_credential_redaction.py -q
```

- 定向格式与通道测试：`36 passed / 0 failed / 0 skipped`。

```powershell
E:\智能运营分析项目\.venv\Scripts\python.exe -m pytest tests/test_day6a_credential_redaction.py tests/test_secret_masking.py tests/test_audit_logs.py tests/test_day6b_online_safe_model.py::test_sentinel_secret_is_redacted_before_serialization tests/test_t004_security.py::test_api_sse_export_and_log_messages_are_redacted tests/test_day3_api_security.py::test_cors_headers_are_preserved_on_authentication_errors -q
```

- T004 脱敏、凭据/异常不回显、HTTP/SSE/导出/日志直接路径：`42 passed / 0 failed / 0 skipped`。

原 Day 7 `security_regression.xml` 的 94 个 nodeid 被逐项重建并精确复跑：

- 原认证安全回归：`94 passed / 0 failed / 0 skipped`。

```powershell
E:\智能运营分析项目\.venv\Scripts\python.exe -m pytest tests/test_t004_security.py::test_health_and_isolated_database_health_do_not_regress tests/test_web_platform.py::test_web_health_endpoint -q
```

- FastAPI health smoke：`2 passed / 0 failed / 0 skipped`。

所有 JUnit XML 均保存于本报告证据目录。

## 6. 数据库、模型与 RAG 隔离

使用 Day 7 原只读快照脚本连接规则允许的 `localhost:5432/postgres`，事务显式设为只读：

- Day 7 基线 SHA-256：`0e2a74337f18d40c213d2148bc30e3d137e972e78740d763cdb55aa1ca54d739`；
- 热修后 SHA-256：`0e2a74337f18d40c213d2148bc30e3d137e972e78740d763cdb55aa1ca54d739`；
- 正式业务写入：0；
- Schema/迁移变化：0；
- Active：唯一 `model_20260620_063015`，身份与 artifact hash 未变；
- Candidate：`model_day6_operational_20260801_143802`，`validated / is_active=0`，未激活。

只读复核的隔离支线均保持既有 HEAD 且 clean：

- RAG Ingestion：`4cce50bf40fe1b50ddbe3bdd62e2c33aaf657227`；
- RAG Runtime：`c79671c82b2b2cd6deedc0f9cb136349fc3d0b1d`；
- RAG-R1：`7eaf8d3152f8ffe5bd983068a99145c9693b4925`；
- Day 6 final：`3d92acd89206530b62fc5cc79e261666cdc94845`；
- merge、cherry-pick、复制与 RAG 数据库写入：0。

## 7. 敏感扫描

扫描范围包含工作区 diff、暂存区、基线至当前 HEAD 的提交内容、分支提交消息、新增/修改文件、JUnit XML、JSON 证据、Markdown 报告和 TXT 输出。

- 动态 sentinel 泄露：0；
- Git working/staged/committed diff 中非法 sentinel：0；
- 真实敏感信息 finding：0；
- 合法合成 sentinel 定义：1 处，分类为 `allowed_test_definition`；
- 合成数据库测试夹具匹配：10 处，分类为 `allowed_synthetic_test_fixture`；
- 扫描输出仅保存路径、匹配类型、数量和整改状态，不保存匹配正文；
- 最终结果：PASS。

## 8. 回滚

1. 先对本报告所在文档提交执行 `git revert <docs-commit>`；
2. 再执行 `git revert ff81a99d3e0b8b8bc0ed4f28927c156e384eddc6`；
3. 使用 `E:\智能运营分析项目_备份\beta10d\20260802_130403042_T004_PRE` 的原件、关键哈希和全仓 manifest 复核；
4. 禁止使用 `git reset --hard` 或 `git clean`；
5. 本任务无数据库、模型、Candidate/Active 或 RAG 变更，因此无需数据、模型或 RAG 回滚。

## 9. 最终结论

唯一 P0 已关闭，受影响门禁全部通过，数据库、模型和 RAG 隔离事实未变化，敏感扫描为 0 finding。

**DAY 7 PASS**。

- 后续开发阶段准入：YES；
- 生产切换：NO；
- Candidate 激活：NO；
- Active 切换：NO。
