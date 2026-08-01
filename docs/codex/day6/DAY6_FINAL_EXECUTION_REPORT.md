# Day 6 最终执行报告

## 1. 最终结论

**DAY 6 CONDITIONAL PASS**。

开发/演示环境已经形成一条真实、可追溯、幂等的“未来 24 小时输入 → online-safe Candidate → 推理落库 → 报告 → 策略 → 人工审核 → API → 预测中心”闭环。原 Active 模型及其 170 项特征契约保持冻结，未覆盖、未激活 Candidate、未执行生产切流，也未进入 Day 7。

条件项不阻断 Day 6 开发闭环，但阻断生产切流：Candidate 的测试 RMSE 优于 24 小时朴素基线，极端价格 RMSE 和 sMAPE 仍弱于该基线；外部 Provider 的生产 SLA、监控、灾备和正式切换审批尚未建立。因此，允许在用户另行明确授权后进入 Day 7 开发任务，生产切换仍为 **NO**。

## 2. Git、检查点与提交

- Worktree：`E:\智能运营分析项目_worktrees\beta10d_day6_final_delivery`
- 分支：`beta10d/day6-final-delivery`
- 基线 HEAD：`abcde0e8310aa618ce9b1dc3a8391fefad04ef99`
- 实现提交：`3e41d2c9a1b3e6a5d271fc77a19876e0ff73b273`
- 前端与权限矩阵提交：`68a94eae48b8e4badb41c707bc742d674287b2fb`
- 文档收口提交：见本文件所在提交
- 最终 Git 状态：要求并已在提交后复核为 clean
- 脱敏预检查点：`E:\智能运营分析项目_备份\beta10d\20260801_220753588_DAY6_FINAL_PRE_SANITIZED`
- 任务证据：`docs/codex/evidence/DAY6_FINAL_20260801_222656646`（本地忽略目录）

## 3. 修改文件清单

后端、迁移与运行链：

- `backend/app/repositories/forecast_repository.py`
- `backend/app/services/forecast_transaction_service.py`
- `migrations/versions/0017_day6_operational_delivery.py`
- `prediction_engine/day6_operational.py`
- `scripts/day3_test_database_guard.py`
- `scripts/day6_provision_runtime.py`
- `scripts/day6_run_operational_closure.py`
- `scripts/day6_train_operational_candidate.py`

Candidate 元数据与 SHA-256 清单：

- `model_artifacts/model_day6_operational_20260801_143802/feature_cols.json`
- `model_artifacts/model_day6_operational_20260801_143802/input_schema.json`
- `model_artifacts/model_day6_operational_20260801_143802/manifest.json`
- `model_artifacts/model_day6_operational_20260801_143802/metrics.json`
- `model_artifacts/model_day6_operational_20260801_143802/model_card.md`
- `model_artifacts/model_day6_operational_20260801_143802/sha256_manifest.json`
- `model_artifacts/model_day6_operational_20260801_143802/thresholds.json`
- `model_artifacts/model_day6_operational_20260801_143802/training_config.json`

API 权限、前端与测试：

- `docs/codex/security/API_PERMISSION_MATRIX.csv`
- `docs/codex/security/API_PERMISSION_MATRIX.md`
- `frontend/src/api.ts`
- `frontend/src/components/forecast/ForecastDesign.tsx`
- `frontend/src/pages/forecast/ForecastCenterPage.tsx`
- `frontend/src/services/forecastApi.ts`
- `frontend/src/styles.css`
- `tests/test_day6_final_operational.py`
- `tests/test_p6_p1_2b_forecast_facts.py`
- `tests/test_phase5_c_report_generation.py`

收口文档：

- `docs/codex/day6/DAY6_FINAL_EXECUTION_REPORT.md`
- `docs/codex/PARALLEL_INTEGRATION_REGISTER.md`
- `docs/codex/TASK_STATUS.md`

## 4. 数据库迁移与最小权限

Alembic 从 `0016_strategy_runtime` 升级为 `0017_day6_operational`。隔离 Schema 已执行 `0016 → 0017 → 0016 → 0017`，均通过；正式开发库只执行一次受控升级。

新增表：

- `forecast_input_batches`：预测锚点、24 小时窗口、契约/输入哈希、来源元数据、幂等状态。
- `forecast_input_snapshots`：每小时 31 项特征、dtype/顺序、来源和时效快照，共 24 行。

修改表：

- `forecast_runs`：增加 `input_batch_id`、来源元数据、freshness 和开发模式标识。
- `forecast_results`：增加 `input_batch_id`，绑定结果与输入批次。

新专用身份：

- 权限组：`beta10d_forecast_runtime`，`NOLOGIN`。
- 登录身份：`beta10d_forecast_login`；运行时确认非超级用户、不可建库/建角色、不可复制、不可绕过 RLS。
- 只读：`raw_market`、`raw_load`、`raw_weather`。
- 受限写入：Day 6 输入批次/快照、预测、报告、策略、审核和审计所需表；无 `DELETE`，无无关业务表写权限。
- Candidate 仅登记为 `validated/is_active=false`；无 Active 切换权限和动作。

数据库前后结构为 62 → 64 张表，视图 8、序列 47、函数 37 均不变。预期业务增量：Candidate registry 1、input batch 1、snapshot 24、forecast run 1、result 24、report 1、report review 1、strategy 1、strategy review 2、audit 3；三张原始源表行数及指纹不变。非预期变化为 0。

## 5. 输入、锚点与 online-safe 契约

- 统一锚点：`2026-08-01T10:44:56.620079-04:00`
- 预测窗口：`2026-08-01T11:00:00-04:00` 至 `2026-08-02T10:00:00-04:00`
- 时区：`America/New_York`
- 连续性：24/24 小时，严格逐小时，无重复、无缺口、无 DST 伪造。
- 输入批次：`batch_day6_b2a29353150b12331b43d8a0ded8556b`
- 输入哈希：`15e38109161c3dc2e0c95e87bb03b96b36030554973c11a0a9db6e6abd55d6be`

真实来源：

- 天气：Open-Meteo Forecast API，24 行未来预报。接口时间语义见 [Open-Meteo Forecast API](https://open-meteo.com/en/docs)。
- 负荷：PJM Data Miner `load_frcstd_7_day` / `DOMINION`，24 行发布负荷预测。接口契约见 [PJM Data Miner 2 API Guide](https://www.pjm.com/-/media/DotCom/etools/data-miner-2/data-miner-2-api-guide.pdf)。
- 市场：PJM `da_hrl_lmps`，只使用锚点前已经发布的 347 条日前价格历史。
- 日历：确定性 US Federal Calendar v1。
- 训练期天气：使用 Open-Meteo Previous Runs 的固定 lead 语义，而不是用未来实况代替预测；语义见 [Open-Meteo Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api)。

新契约共 31 项：17 项确定性时间特征、5 项独立 Provider 预测特征、9 项锚点前已发布价格的 lag/rolling/same-hour 特征。名称、顺序、dtype 和 schema hash 全部 fail-closed；禁止 future target、未来实际负荷、未来实时价格/价差、补零、历史复制、日期平移和预测时点后的聚合窗口。

## 6. Candidate 训练、模型和评估

- 模型版本：`model_day6_operational_20260801_143802`
- 特征版本：`features_day6_operational_589ede956c04`
- Schema hash：`589ede956c041de58194c7864043b32453e82c715956e41b735cf4f1c6ad3114`
- 模型：HistGradientBoosting，固定随机种子 `20260801`
- 状态：`validated`、`is_active=false`、`development_demo_only=true`
- Active 保持：`model_20260620_063015` / `features_140db8af25f9`
- Artifact SHA-256：`afd8a9ca98c7d6b97e28846c6c1257835cddf6e1d7413e66d038040b9f91db6d`

固定时间切分：

| 数据集 | 时间范围 | 行数 |
|---|---|---:|
| 训练 | 2024-07-13 06:00 – 2026-04-18 23:00 | 15,136 |
| 验证 | 2026-04-19 00:00 – 2026-05-18 23:00 | 720 |
| 测试 | 2026-05-19 00:00 – 2026-06-17 23:00 | 720 |

无随机打乱；测试集不参与模型选择；转换器只在训练区间拟合。泄漏审计覆盖时间穿越、future target、future actual load、future realized market value、全量 scaler/encoder、rolling 越界和未来聚合，全部 PASS。

| 指标 | 验证 Candidate | 验证 naive-24h | 测试 Candidate | 测试 naive-24h |
|---|---:|---:|---:|---:|
| RMSE | 54.9414 | 65.5877 | 102.7719 | 118.6337 |
| MAE | 16.6825 | — | 45.6075 | 48.0021 |
| R² | 0.4570 | — | 0.4514 | 0.2689 |
| sMAPE | 21.6872% | — | 38.1862% | 34.0801% |
| 峰时 RMSE | 60.4731 | — | 79.3588 | 95.9249 |
| 谷时 RMSE | 50.6215 | — | 116.6531 | 132.4923 |
| 极端价格 RMSE | 167.5977 | — | 289.9166 | 217.1068 |

验证/测试 RMSE 分别改善 16.2321% / 13.3704%；重复推理最大差值 0；测试推理 55.5531 ms；缺失率 0。极端价格和测试 sMAPE 的回退是生产切流条件项，不允许以恢复泄漏特征解决。

## 7. 运行闭环身份

- `run_id`：`run_20260801T140000000000Z_b2a2935315`
- 预测结果：24 行，结果哈希 `072140d385b3cf4d1410f8a64aedba537fdee83d705d3257368f6a7180c4c05b`
- 报告 ID：`p5c_operation_decision_run_20260801T140000000000Z_b2a2935315`
- 报告审核 ID：`1`
- 策略 ID：`p5d_09eae59f4b0126eb584d983f`
- 策略状态：`approved`，`published=false`，无自动交易或设备动作。
- 策略提交审核：`srv_26fb8ce37d2c42c1b1db47cb50b7fa17`
- 策略批准审核：`srv_4f62be6f5b5040a284b02547abbcd159`
- 幂等复跑：相同 batch/run/report/strategy/review 标识，未重复写入，PASS。

实际命令（配置文件内容未输出）：

```powershell
E:\智能运营分析项目\.venv\Scripts\python.exe scripts/day6_train_operational_candidate.py --runtime-config E:\智能运营分析项目_本地配置\beta10d_day6_final_runtime.env --artifact-root model_artifacts --evidence-root docs/codex/evidence/DAY6_FINAL_20260801_222656646/candidate_training
E:\智能运营分析项目\.venv\Scripts\python.exe scripts/day6_run_operational_closure.py --runtime-config E:\智能运营分析项目_本地配置\beta10d_day6_final_runtime.env --model-version model_day6_operational_20260801_143802 --artifact-root model_artifacts --output-root docs/codex/evidence/DAY6_FINAL_20260801_222656646/runtime_output --evidence docs/codex/evidence/DAY6_FINAL_20260801_222656646/operational_closure.json
```

## 8. API 与前端验收

认证读取接口均为 200，且读取前后数据库计数一致：forecast run/results/latest、report/reviews、strategy/reviews/latest。开发身份头只在 `VITE_AUTH_REQUIRED=0` 构建中启用；默认生产构建不发送，后端在生产/认证必需模式继续 fail-closed。

预测中心显示 24 行，并展示本次推理模型/特征版本、run_id、batch_id、预测窗口、开发演示标签、来源与 freshness。1366、1440、1920 三视口无页面级横向溢出，控制台 error 0。1920 全页截图存在浏览器宿主 1440 表面拼接限制，但 DOM 测量为 `documentWidth == viewportWidth == 1920`，不属于产品布局缺陷。

最终本地 `npm run build`：TypeScript + Vite PASS，3675 modules，19.29 s。一次重复 `pnpm` 验证因下载 `echarts` 超时而失败，恢复既有本地依赖后上述离线构建通过；该失败未改变 Git 文件，也不是产品测试失败。

## 9. 测试、敏感信息与 RAG 隔离

- 最终 Day 6/P6 一次性 Schema：20 passed / 0 failed / 0 skipped；public 前后指纹一致，临时 Schema/角色残留 0。
- 权限矩阵 + Day 6 静态门禁：55 passed / 0 failed / 0 skipped。
- 核心隔离回归：70 passed / 0 failed / 28 skipped。
- Phase 5 关联隔离回归：71 passed / 0 failed / 0 skipped。
- 迁移往返、运行身份、API、幂等、浏览器和构建：全部 PASS。
- 敏感信息：28 个变更文本文件，0 finding；指定 sentinel 脱敏测试 PASS；未记录密码、完整 DSN、Token、API Key 或环境变量正文。
- RAG：Day 6 变更路径中 RAG 相关为 0；ingestion `4cce50bf…`、runtime `c79671c8…`、旧 RAG-R1 `7eaf8d31…` 均 HEAD 不变且 worktree clean；无 merge/cherry-pick/复制或 RAG 数据写入。

## 10. 回滚

1. 代码按“文档收口 → `68a94ea…` → `3e41d2c…`”逆序执行 `git revert`，不使用 reset/clean。
2. 在管理员审批和事务保护下，按外键逆序仅删除本报告列出的 review、strategy、report、forecast result/run、snapshot/batch 和 Candidate registry 精确 ID；原始源表不动。
3. 确认 Day 6 事实已清理后执行 `alembic downgrade 0016_strategy_runtime`。
4. 使用 `scripts/day6_provision_runtime.py --rollback` 精确撤销 Day 6 专用角色；盘外凭据不写回仓库。
5. 本地 Candidate 二进制可保留为未激活审计件；如需清理，逐个明确文件处理，不批量删除目录。

## 11. 后续条件项

- 为极端价格区间建立独立门槛和误差监控，改进 sMAPE，但不得恢复泄漏特征。
- 建立 Open-Meteo/PJM Provider 的生产 SLA、超时、重试、熔断、freshness 告警和可审计灾备。
- 完成生产角色复核、切换申请、双人审批和回滚演练后，才可申请 Active 切换。
- Day 7：**YES（仅允许在新任务中明确授权后进入开发工作；本轮未进入）**。
- 生产切换：**NO**。
