# Day 6A 未来 24 小时预测输入准入收口报告

## 最终结论

- `ACTIVE MODEL ONLINE FEATURE CONTRACT NOT PASS`
- `DAY6A NOT PASS`
- 原 Day 6 重新准入：`NO`
- 本轮停在阶段 A 的 Active 模型线上特征契约门禁；未进入 Provider、输入批次、迁移、24 小时快照、预测、报告、策略、审核、反馈或 Day 7。

## 凭据事件收口

- 事件事实：Day 6A 指纹工具曾把 SQLAlchemy DSN 直接传给 psycopg，异常回显了本地运行角色密码；不得改写为“未发生泄露”。
- beta10d_app_login 已轮换为随机新凭据；新凭据连接成功，旧凭据拒绝，既有连接已终止。
- 角色仍为 NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS/LOGIN；应用身份仍为 beta10d_app_login，安全仓储身份仍为 beta10d_security_login，未回退到 postgres。
- Day 4 ACL 前后摘要一致：f1336d0cd745052dc041572572b431719d090dcb2625cbe457a2f7c797440ed1。
- 本地证据、工作树、相关检查点、Git diff/历史的文件级扫描未确认包含旧密码的文件，故脱敏删除/隔离文件数均为 0；旧密码仅存在于此前任务终端输出，现已失效。
- 修复提交：49201c430689e8d3c0197a2dd029dd1c44bd5f7c；事件记录提交：6a55cd17da6563441a0b12be9ca32ca8d9e8e162。
- 原部分检查点保留为过程证据但不再作为基线；最终脱敏检查点：E:\智能运营分析项目_备份\beta10d\20260801_154850197_DAY6A_PRE_SANITIZED。

## Active 模型与 170 项矩阵

- Active：model_20260620_063015；feature version：features_140db8af25f9；schema hash：a855692756793862b1fcfd3c68c701d1ad231b32e6581797d74f4a8ab4199281。
- FEATURE_AVAILABILITY_MATRIX.csv 共 170 行；表头、名称顺序、dtype 与 artifact 完全一致，重复 0、必填空值 0。
- 分类：锚点已知 23、历史新鲜时可用 33、递归模型输出 43、正式负荷预测条件可用 31、正式天气预测条件可用 25。
- 阻断 15：未来实际负荷语义 11、未来实时价差 1、未实现且当前补零的误差记忆特征 3。
- 这 15 项只能通过重训/换模或建立训练与线上完全一致的预测时可得语义解决；不得复制历史、补零、改 Active schema 或用代理值冒充。

## 可再生能源与来源状态

- Active schema 中可再生能源特征为 0，属于任务书“情况 A”；当前模型不要求 Renewable Provider，raw_renewable=0 不构成本模型的独立阻断项。
- 基线与收口只读关键事实一致：raw_market=35036、raw_load=35006、raw_weather=17520、raw_renewable=0；前三者最大业务时间均为 2026-06-18 23:00:00。
- 审计日为 2026-08-01，历史事实同时不满足当前预测的新鲜度要求。
- 负荷和天气 Provider、统一预测锚点、输入批次 ID、24 小时窗口、来源发布时间、时区转换、质量门禁、170 项快照/hash、幂等和真实来源冒烟均因前置契约失败而未实施、未生成，不能报告为 PASS。

## 测试与隔离

- 凭据异常路径：18 passed；schema/泄漏静态回归：7 passed。
- Day 3 静态门禁 + Day 4/Day 5 契约回归：26 passed、2 failed；两项失败均为 pytest 数据库守卫屏蔽本地数据库后接口返回 503，不是本轮业务写入结果，未伪报通过。
- T002 artifact 回归在工作树未复制模型二进制时为 1 passed、1 setup error；本轮按安全边界未反序列化模型。
- RAG Ingestion 4cce50bf40fe1b50ddbe3bdd62e2c33aaf657227、Runtime c79671c82b2b2cd6deedc0f9cb136349fc3d0b1d 均 clean，且均不是 Day 6A HEAD 的祖先；无 merge、cherry-pick、文件复制、迁移或数据库写入。

## 数据库、证据与回滚

- 新 Alembic revision、DDL、DML、Seed 和业务写入均为 0；未创建输入批次或预测事实。
- 脱敏基线完整指纹：Alembic 0016_strategy_runtime，public 62/8/47/37，schema SHA-256 a0a3f650124d6e2a477793b034810cc6cff42858457d45ffd90ed22c00bae923。
- 收口时普通/安全身份均按 Day 4 ACL 正确拒绝读取 alembic_version；因此未以放宽权限换取完整 after 指纹。最小权限关键业务只读指纹与基线行数、水位及 Active 身份一致。
- 证据目录：docs/codex/evidence/DAY6A_FORECAST_INPUT_AUDIT_20260801_160908。
- 回滚代码与文档：按提交逆序执行 git revert；本地凭据保持轮换后状态，不回退旧密码；数据库无业务变更，无数据恢复操作。
