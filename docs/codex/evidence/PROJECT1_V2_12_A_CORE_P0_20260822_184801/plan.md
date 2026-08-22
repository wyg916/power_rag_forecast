# PROJECT1 v2.12.0 A Core P0 执行计划

- 工作树：`E:/智能运营分析项目_worktrees/project1_v2.12.0_core_p0`
- 分支：`codex/project1-v2.12.0-core-p0`
- 起始 SHA：`3b6eb33df96ece08a60acce802d6ec249ec5a826`
- 启动 Gate：PASS，起始工作树 clean。
- 检查点：`backups/phase3/20260822_184801_PROJECT1_V2_12_A_CORE_P0_PRE/`

## 完成结果

1. 已复核 PostgreSQL 模型、输入、预测、报告、策略和任务事实。
2. 已复现并关闭公开入口、linked-worktree 资产定位和输入事务三个断点。
3. 正式 Celery worker 已生成 run `run_20260822T115159818317Z_5370682c70`。
4. 输入 batch、24 个 snapshot、run 和 24 个结果已原子落库。
5. 缺特征、hash 不匹配、模型缺失、行 12 故障均 FAILED 且结果 0；重复请求复用同一 run。
6. API/任务中心/两轮刷新/worker 重启及报告、策略、异人审核链全部通过。
7. ChatBI Catalog 归 C，本任务仅登记集成依赖。

禁止项：不改 frontend、AI Runtime、启动脚本、CI、main、B/C 分支；不使用 Mock、Demo、fallback 或手工结果行。
