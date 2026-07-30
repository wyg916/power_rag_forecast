# P6-P1.3c 策略运行事实模拟入库与全链路联调

## 目标

在不修改核心预测事务链、不触发自动交易或设备控制的前提下，补齐策略中心缺失的储能设备清单、SOC、执行反馈和已实现收益展示。

## 唯一数据链路

`业务规则模拟 → localhost:5432/postgres → Repository → GET API → 前端服务适配 → 策略中心`

禁止前端生成 SOC、设备、执行反馈或收益；禁止接口失败后的静态成功 fallback。

## 数据表

- `storage_devices`：设备能力、效率、SOC 约束、运行状态。
- `storage_soc_snapshots`：设备时点 SOC、可用电量、充放电功率。
- `strategy_execution_items`：计划/实际功率和电量、执行状态、反馈、已实现收益。

三表均要求 `data_source`、`is_simulated`、`batch_id`、`generated_at`、`scenario`。

## API 与权限

- `GET /api/strategy/runtime-facts`
- 权限：`strategy:read`
- GET 必须无写副作用。

## 当前模拟批次

- 批次：`p6_strategy_runtime_20260726_v1`
- 场景：`zhejiang_day_ahead_storage_arbitrage`
- 来源：`business_rule_simulation`
- 规模：2 台设备、48 个 SOC 时点、6 条执行反馈。
- 工具：`scripts/seed_strategy_runtime_facts.py`
- 回滚：工具参数 `--rollback-batch` 仅删除该批次且 `is_simulated=true` 的记录。

## 验收

1. 唯一数据库目标校验 PASS。
2. Alembic 0016 upgrade/downgrade 路径存在。
3. 模拟入库重复执行不产生重复行。
4. API 返回设备、SOC、执行反馈、收益及完整来源元数据。
5. 前端设备筛选、SOC 图、执行清单、反馈详情和收益展示来自 API。
6. “当前展示的是可追溯旧数据”大信息框移除；stale 原因仍以紧凑语义保留。
7. 不存在参数化 SOC、前端静态成功 fallback、自动交易或设备控制。
