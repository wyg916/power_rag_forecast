# Day 6A 凭据暴露事件收口记录

## 结论

- 事件状态：`CLOSED`
- 收口日期：`2026-08-01`
- 影响账号：`beta10d_app_login`
- 影响范围：当前 Codex 任务的一次数据库指纹异常输出；未发现包含该密码的项目文件、Git 对象或本地证据文件。
- 处置原则：如实记录、立即轮换、不复述新旧密码、不降低 Day 6A 数据真实性门禁。

## 事件事实

Day 6A 只读数据库指纹工具错误地把 SQLAlchemy DSN 传给 `psycopg.connect`，异常文本回显了
`beta10d_app_login` 的本地密码。该事实不能改写为“未发生泄露”。

暴露发生在当前 Codex 任务的工具异常输出中。旧密码已轮换；本文件、测试证据和后续检查点均不保存
旧密码、新密码或完整 DSN。

## 影响范围核验

已扫描以下范围：

- Day 6A Worktree；
- Day 6A 部分检查点；
- Day 4、Day 5、Day 6 本地证据目录；
- 当前工作树和 staged diff；
- 当前分支提交历史；
- 本轮新生成的 JSON、Markdown 和 TXT 指纹证据。

原部分检查点：

`E:\智能运营分析项目_备份\beta10d\20260801_144716102_DAY6A_PRE`

核验结果：

- 该检查点未命中数据库 URL、密码赋值或旧角色凭据正文；
- 该检查点不完整，已废弃为执行基线，但作为无秘密的事件过程证据保留；
- 已确认包含密码的本地证据文件数量为 `0`，因此未删除、覆盖或隔离任何项目文件；
- 当前任务的历史异常输出包含已经失效的旧密码，该任务记录不属于本地项目文件，未进行伪造或改写。

## 轮换与权限验证

- 新凭据连接：`PASS`
- 旧凭据连接：`DENIED`（轮换进程强制门禁）
- 旧会话：已终止；独立复验时该角色活动会话数为 `0`
- 运行身份：`beta10d_app_login`
- 安全身份：`beta10d_security_login`
- 超级用户回退：`false`
- Day 4 最小权限角色属性：保持不变
- 轮换前后 ACL：轮换进程哈希比较一致
- 独立复验 ACL SHA-256：`f1336d0cd745052dc041572572b431719d090dcb2625cbe457a2f7c797440ed1`

角色继续满足：

- `NOSUPERUSER`
- `NOCREATEDB`
- `NOCREATEROLE`
- `NOREPLICATION`
- `NOBYPASSRLS`
- `LOGIN`

## 根因与修复

根因是一次性检查点命令混淆了 SQLAlchemy URL 和 psycopg conninfo，并让原始异常字符串逃逸到终端。

修复提交：`49201c430689e8d3c0197a2dd029dd1c44bd5f7c`

修复内容：

- SQLAlchemy URL 先由 `make_url` 解析，再向 psycopg 传递明确连接参数；
- PostgreSQL、Redis、AMQP URL userinfo 统一脱敏；
- `password`、`token`、`api_key`、`secret` 和 Authorization Header 统一脱敏；
- 异常链只保留错误类型和脱敏后的有界消息；
- JSON、Markdown、TXT 证据在写入前再次执行结构化脱敏；
- 两个既有 PostgreSQL 诊断入口改用统一安全异常摘要。

## 测试与扫描

- Python 编译：`PASS`
- 原有秘密脱敏测试与 Day 6A 新测试：`20 passed`
- 覆盖：URL 解析、psycopg、DNS、认证、端口、库不存在、环境配置、指纹异常、JSON、Markdown、stdout、stderr、日志和 Git diff。
- 最终合成哨兵泄露：`0`
- 当前轮换后真实密码在指定文件中的命中：`0`
- 当前轮换后真实密码在 Git 历史中的命中：`0`
- 当前轮换后真实密码在 staged/working diff 中的命中：`0`
- staged diff 中 URL/Authorization 形态均为运行时拼接的合成测试夹具；待整改记录：`0`

脱敏只读指纹证据：

`docs/codex/evidence/DAY6A_CREDENTIAL_CLOSURE_20260801_153254181`

指纹结果：Alembic `0016_strategy_runtime`；public 对象数为 62 表、8 视图、47 序列、37 函数；
本轮指纹事务只读并已回滚。

## 后续防护

- 原部分检查点不得作为 Day 6A 恢复基线；
- 必须重建 `DAY6A_PRE_SANITIZED` 完整检查点并通过秘密扫描；
- Day 6A Provider 和输入批次继续使用 Day 4 最小权限运行身份；
- 本事件不改变 Active 模型、预测事实、报告、策略、RAG、Alembic 或业务数据；
- 事件收口后直接恢复 Day 6A，不进入原 Day 6 或 Day 7。
