# 基线与来源证明

## 已确认候选

- 分支：`codex/ui-forecast-center-fidelity-20260814`
- SHA：`7090de4f76a4df228f7b98e9203b205c5aeba0fd`
- Worktree：`E:\智能运营分析项目_worktrees\ui_forecast_center_fidelity_20260814`
- 状态：clean
- 反例 `bc8c4c568fe838cc6927890d0d6c20bb760fa730` 不是候选祖先，未集成。

## 当前 Release

- 分支：`release/beta10d-agent-rc-20260807`
- 本次重新收敛时 SHA：`b4cfdd06dc9fb63ebbc66565531f9a5c40f4b589`
- Worktree：`E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807_report_integration`
- 状态：clean
- `1f4f7e50e3177aec21594b52ce74cd03dd77ea7d` 是其祖先；该 Release 另含已批准的报告中心和数据中心集成。

## 隔离集成

- 分支：`codex/integrate-forecast-center-20260815`
- Worktree：`E:\智能运营分析项目_worktrees\integrate_forecast_center_20260815`
- 合并候选提交：`cd850d5`。
- 跨页面页头契约修正：`70a7ce9d4a647df2cd86d4b72947d9823db74327`。
- 合并最新 Release：`e1c3e324d4c5a4bfd410c30d842cf6561a7dafea`。
- 本证据提交只增加文档/截图，不改变页面运行代码。

## 文件来源核验

- 数据中心源文件及其专项测试的 Git blob 与 Release `b4cfdd0…` 完全一致。
- 预测中心 `ForecastDesign.tsx`、`ForecastCenterPage.tsx`、`forecastApi.ts` 与候选 `7090de4…` 完全一致。
- `styles.css` 为已批准报告中心样式与预测中心候选样式的自动无冲突并集；最新数据中心使用独立 CSS 文件，未覆盖预测中心样式。
- 唯一人工冲突为 `tests/test_p6_p0_2_frontend_contract.py` 的跨页面页头契约；实现代码无人工冲突。
