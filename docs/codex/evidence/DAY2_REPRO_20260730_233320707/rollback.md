# Day 2 回滚

## 代码

按以下逆序使用 `git revert`，禁止 `git reset --hard`、`git clean` 或覆盖 Day 1 分支：

1. `97dcd5091692710407f7b977b0713733fc1124bb`
2. `2804716a2b4a10fca67b4ad5fa9dd8cf318bf1a7`
3. `bbbe43a58e94cf4503280dd6948a765f5e8217c0`
4. `18da943405750e259bb035b13af082c7c9b15b56`

收口证据提交应最先 revert；其完整哈希见最终报告与 Git 日志。

## 配置

- 仅回滚本轮受跟踪的模板、Compose、版本口径和文档。
- 实际 `.env`、随机密钥和验证目录配置未进入 Git。
- 如需恢复 Day 2 前状态，可从
  `E:\智能运营分析项目_备份\beta10d\20260730_233152624_DAY2_REPRO_PRE`
  核对 `git status`、diff、清单和关键哈希。

## 数据库

- 活动 `public` 未执行迁移或 downgrade，无需业务数据恢复。
- 两组 `beta10d_day2_` 临时 Schema/角色已精确清理并验证不存在。
- 若中断后残留，只能在核验数据库为 `postgres`、名称满足 `^beta10d_day2_`、Schema owner 为对应 NOLOGIN 角色后，逐一清理明确对象。
- 禁止 `DROP DATABASE`，禁止对 `public` 执行 downgrade。
- 若 `public` 或关键业务指纹变化，立即报告 `DATABASE ISOLATION BREACH`，不得自行覆盖。
