# Day 1 可信基线冻结与可复现性报告

## 结论

- 日期：2026-07-30
- 分支：`beta10d/day1-trusted-baseline`
- 基线起点：`5b61cab0e9fcf48bb9f81141dd349bd40620f761`
- 全量备份验证：`FULL BACKUP VERIFICATION PASS`
- 基线漂移复核：PASS
- Day 1：PASS
- Day 2：具备准入条件，但本轮未执行

## 全量备份

- 源：`E:\智能运营分析项目`
- 备份：`E:\智能运营分析项目_备份\beta10d\20260730_212742_FULL_PROJECT_BACKUP`
- 完成时间：2026-07-30 21:53:45
- 原始 Robocopy：111792 文件全部复制，mismatch 0、failed 0、退出码 3
- 用户确认时的 1 文件、15,108,545 字节差异精确对应 `FULL_BACKUP_ROBOCOPY.log`
- 后续 `FULL_BACKUP_CONFIRMATION.txt` 增加 289 字节
- Dry-run 的两个 Extra 仅为上述日志与确认文件
- 备份后源目录新增一个 41 字节 `.git/refs/codex/turn-diffs` 会话元数据
- 107 个 `.git/objects` 仅时间戳更新，源/备份内容哈希不一致 0
- 原 67 个状态文件在备份中缺失 0、哈希不一致 0
- `.git`、`.env`、`.env.docker`、0015/0016、后端、前端、测试、模型和知识资产均已覆盖

## 时间敏感测试根因

生产实现按全部运行事实中最新 `generated_at` 与当前 UTC 的年龄计算，阈值固定为 6 小时，严格使用 `age > 6h` 判 stale。活库最新运行事实为 `2026-07-28T17:53:37.831544+08:00`，核验时年龄约 52.55 小时，所以 `is_stale=true` 符合生产规则。

原测试把“读取链无写副作用”和“固定历史数据必须 fresh”混为一个断言。唯一硬编码 `is_stale is False` 的测试已经改为：

1. 比较策略、审核、运行事实、审计和任务表调用前后的行数与内容指纹；
2. 验证接口读取成功；
3. 验证返回 stale 状态与生产纯函数计算一致；
4. 独立覆盖阈值内、恰好 6 小时、超过边界、缺失时间和非法时间。

生产阈值、历史数据、数据库记录和 stale 展示均未放宽或伪造；未冻结系统时间，未增加测试专用业务分支。

## 数据库零写入

Day 1 后半程没有执行：

- Alembic upgrade/downgrade
- DDL
- DML
- Seed
- 模型训练或激活
- 报告或策略生成

最终综合测试前后 12 张相关业务表的行数与内容组合指纹均为：

`bc5899712db4249c569b622d1846953706c6de392c022cec0b56c417ba116894`

前后一致，数据库写入为 0。

## 最终测试

| 测试组 | 结果 |
|---|---|
| 原失败单测试 | 1 passed |
| 运行事实非写入组 | 11 passed / 1 controlled-seed test deselected |
| Phase5-D 非写入组 | 55 passed / 9 database-write tests deselected |
| 其余 P6/Data/Forecast/Strategy/Knowledge/T005 只读或静态组 | 58 passed |
| Pytest 合计 | 124 passed / 0 failed / 10 deselected |
| Node view-state | 7 passed / 0 failed / 0 skipped |
| Python 变更文件语法 | 26 passed |
| TypeScript | `tsc --noEmit` PASS |
| Alembic | 单 head `0016_strategy_runtime`，无 branch |
| Git diff check | PASS |
| 全提交高置信敏感信息扫描 | 0 命中 |

明确 deselect 的 10 个用例包含 Seed 或数据库 INSERT/UPDATE/DELETE，符合 Day 1 写入封锁要求，不是伪造 skip。

## 原子提交

1. `c3ba7cb11019c1364dc92fe19d4db3a7a3b5eea7` — 依赖兼容
2. `25664a00a7c8db86b7baea6546f6a38b0479aab6` — 0015/0016 迁移
3. `b2f52768ac64d7af377e62113b9cb4ccd42a579f` — 策略治理与运行事实后端
4. `90b3a258386beba87f6c0aa116b18188f1b376f7` — 时间敏感测试职责拆分
5. `5db5074f31bfefa98f41d4bb3824c00d0534d837` — Phase5-D 与来源契约测试
6. `e752ec69a91051b02bfe4f2b4af7558552602e49` — 前端 API 与状态适配
7. `4d85cd3fc9d6fd2829f94175c3499e9d830e5ea7` — 公共页面壳与七态
8. `4943e7f0443532a0756b5576436168839572050e` — 数据中心真实只读闭环
9. `11d57bb210503009694913f74a395b4fb5390c53` — 预测中心事实 UI
10. `4c604be5f113e59aaf84793961f557648bced123` — 策略中心三页治理 UI
11. `f7c2f3d626591ae53cd7d4deab08e77c4e9dc311` — 工程规则与阶段文档
12. `2ae354fea8a2ff9fba1c64da50a7a4334614874f` — PostgreSQL 运行证据

本报告与 `TASK_STATUS.md` 的收口提交哈希以本分支最终 Git 历史为准。

## 0015 / 0016 纳管

- `migrations/versions/0015_phase5d_strategy_governance.py`：已跟踪
- `migrations/versions/0016_p6_strategy_runtime_facts.py`：已跟踪
- parent：`0014_t003_run_transaction → 0015_phase5d_strategy → 0016_strategy_runtime`
- 活库版本：`0016_strategy_runtime`
- 当前代码已经能表达活库依赖的正式迁移能力
- Day 1 未执行迁移回放；全新环境空库回放仍属于后续经批准的验证

## 未提交与本地文件

根目录 `智能电力分析AI助手_10天优化落地与验收方案_v1.0.docx` 与外部最高执行附件 SHA-256 一致，属于输入附件副本，不参与运行；正式需求参考 Word 已在 `docs` 下纳管。根目录副本保留在磁盘和全量备份中，不删除、不移动、不提交，并使用精确的本地 `.git/info/exclude` 规则避免污染工作树。

`.env`、`.env.docker`、日志、缓存、构建产物和模型大文件均未进入 Git。

## 恢复与回滚

完整恢复：

1. 从全量备份复制到新的恢复目录，不覆盖当前工作区；
2. 核对备份 `.git` 的 HEAD 和 67 项原始哈希；
3. 如仅需 Git 基线，从远端/本地对象检出本分支最终 HEAD；
4. 只读核对活库 `alembic_version`，不得在恢复核验阶段直接迁移。

代码回滚：

- 使用逐提交 `git revert <commit>`，按逆序回滚；
- 不使用 `git reset --hard`、`git clean` 或强制覆盖；
- 迁移提交的 Git revert 不等于数据库 downgrade。

数据库回滚：

- Day 1 无数据库写入，无数据回滚；
- 0016/0015 downgrade 只能在批准的隔离环境先验证；
- 当前活库不得因 Git 回滚直接执行 downgrade。

## 剩余风险

- 数据库应用角色仍是 `postgres` 超级用户，属于 Day 2 安全门禁范围；
- 当前运行事实诚实标记 stale；
- Celery Broker 健康不代表 Worker 可用；
- 旧 SQL 与 Alembic 管理对象存在重叠；
- 干净环境完整部署与空库回放尚未执行。

以上风险不再阻塞 Day 1 基线冻结，但必须由后续对应 Day 处理。
