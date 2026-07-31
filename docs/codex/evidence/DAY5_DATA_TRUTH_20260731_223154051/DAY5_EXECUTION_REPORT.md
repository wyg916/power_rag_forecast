# Day 5 数据真实性、时效语义与业务展示收口报告

## 1. 结论

- 结论：`PASS`
- 分支：`beta10d/day5-data-truth`
- Day 4 基线：`e1be5d0bb4213daa52025e01cf84320f271d0898`
- Day 5 最终业务提交：`6e7dcde6cf1544ff9aa6b84480ead987c68e0f7f`
- Day 5 收口提交：本报告所在提交
- Day 6 准入：`GO`；本轮未执行 Day 6。
- 正式 Alembic revision：新增 0；当前单一 head 保持 `0016_strategy_runtime`。
- 当前 PostgreSQL 业务数据写入：0；测试写入均位于一次性受限 Schema，清理残留 0。
- RAG merge/cherry-pick/文件复制：0。

按任务验收项归并，本轮关闭 32 个真实性问题点：报告 8、预测 6、策略 6、首页 6、数据中心 3、共享事实/页面状态契约 3。报告中心删除或替换 8 组伪事实模式，包括 8 个固定同比/较昨日趋势、`本期值 × 0.85` 伪同期曲线、24 点补零成功态、固定日期/审核人/版本/模板/变更说明/流程时间线，以及预测价格冒充实时电价。

## 2. 现有 13 项修改接管审计

外部可恢复检查点：`E:\智能运营分析项目_备份\beta10d\20260731_223154051_DAY5_EXISTING_CHANGES_INTAKE`

- 原始 13 文件：606 insertions、195 deletions；文件丢失 0。
- 补丁恢复：`git apply --check --reverse --whitespace=nowarn tracked_diff.patch` PASS。
- 接管时高置信敏感信息：0 命中。
- 来源判断：修改时间、diff 风格和依赖关系连续；其他 worktree 未出现同组未提交内容。无法从 Git 对未提交 hunk 做作者学证明，但不存在持续并发写入或外部依赖。
- 接管结论：`DAY5 EXISTING CHANGES INTAKE PASS`。

| 文件路径 | 修改 | 内容 | Day5 目标 | 范围 | RAG | Day6+ | 迁移 | 公共配置 | DB 写入 | 敏感 | 质量 | 归属/提交组 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `backend/app/source_contract.py` | modified | 统一来源、有效期、freshness、追溯元数据 | 状态契约 | yes | no | no | no | no | no | no | usable | SHARED_CONTRACT / 1 |
| `frontend/src/components/common/States.tsx` | modified | 七态、来源与 stale 元数据、禁用成功 fallback | 状态契约 | yes | no | no | no | no | no | no | usable | SHARED_CONTRACT / 1、6 |
| `frontend/src/components/forecast/ForecastDesign.tsx` | modified | 历史预测窗口与追溯展示 | 预测 | yes | no | no | no | no | no | no | usable | DAY5_OWNED / 3 |
| `frontend/src/components/strategy/StrategyDesign.tsx` | modified | 测算/执行/审核/有效性语义拆分 | 策略 | yes | no | no | no | no | no | no | usable | DAY5_OWNED / 4 |
| `frontend/src/pages/dashboard/DashboardPage.tsx` | modified | stale 首页、KPI 口径、1366–1600 响应式 | 首页 | yes | no | no | no | no | no | no | usable | DAY5_OWNED / 5、6 |
| `frontend/src/pages/forecast/ForecastCenterPage.tsx` | modified | run/model/feature/window/stale 页面契约 | 预测 | yes | no | no | no | no | no | no | usable | DAY5_OWNED / 3 |
| `frontend/src/pages/report/ReportCenterPage.tsx` | modified | 移除伪同比、固定审核与静态结论 | 报告 | yes | no | no | no | no | no | no | usable | DAY5_OWNED / 2 |
| `frontend/src/pages/strategy/StrategyCenterPage.tsx` | modified | 历史策略、审核状态、不可执行边界 | 策略 | yes | no | no | no | no | no | no | usable | DAY5_OWNED / 4、6 |
| `frontend/src/services/forecastApi.ts` | modified | 预测窗口与真实追溯，禁止映射观测/结算价 | 预测 | yes | no | no | no | no | no | no | usable | SHARED_CONTRACT / 3 |
| `frontend/src/services/homeDashboardApi.ts` | modified | 预测峰谷价差口径、空值不补零 | 首页 | yes | no | no | no | no | no | no | usable | DAY5_OWNED / 5 |
| `frontend/src/services/reportApi.ts` | modified | 报告绑定 run 的曲线、审核记录和版本事实 | 报告 | yes | no | no | no | no | no | no | usable | SHARED_CONTRACT / 2 |
| `frontend/src/services/strategyApi.ts` | modified | 策略/审核/预测/运行事实分层 | 策略 | yes | no | no | no | no | no | no | usable | SHARED_CONTRACT / 4 |
| `tests/test_t005_source_contract.py` | modified | 新来源类型、隔离 Schema 和无副作用回归 | 测试 | yes | no | no | no | no | yes，仅隔离清理 | no | usable | DAY5_OWNED / 7 |

特别核验结果：RAG/Qdrant/Embedding/知识库/AI 引用改动 0；Alembic、权限矩阵、Docker Compose、公共配置、Day4 ACL/角色、任意 SQL、数据集白名单修改 0；Seed/真实历史业务数据脚本修改 0；skip/xfail/放宽 freshness 阈值 0。旧静态测试的冲突断言被更新为更严格的禁止技术来源文案与禁止 fallback 契约。

## 3. 统一真实性契约

后端统一输出并在服务层消费：`data_origin`、`source_type`、`source_name`、`generated_at`、`updated_at`、`valid_from`、`valid_to`、`freshness_status`、`is_stale`、`staleness_reason`、`run_id`、`model_version`、`feature_version`、`data_version`、`simulation`、`degraded`、`availability`、`unavailable_reason`。

来源分类覆盖真实当前、真实历史、模拟、Seed/Demo、推导、AI 推断、降级、不可用；历史类型强制 stale，根字段不能覆盖 `meta` 的真实性结论。普通业务页面只展示中性业务来源、业务时间、更新时间和状态；技术来源字段保留在受控后端/API 契约中。

## 4. 模块收口结果

### 报告中心

- 无同期事实时显示“无同比/昨日基线”“不可计算”，不生成趋势。
- 曲线只取报告绑定 `run_id` 的预测结果；空曲线显示 Empty，不补 24 个 0。
- 审核人来自登录身份或持久化审核记录；版本、模型、特征、数据版本、窗口和时间线来自接口。
- 固定流程节点改为根据报告和审核事实逐步完成；无记录明确显示未完成。
- “实时电价”改为“报告绑定预测值”，单位统一为接口事实口径。

### 预测中心

- 保留 2019-12-31 至 2020-01-01 的历史预测事实，不写库制造当前预测。
- 展示实际窗口、生成时间、`run_id`、模型版本、特征版本、历史/过期状态与原因。
- 预测价格与 observed/actual/clearing 价格读取分离；页面不存在“今日预测”“当前未来 24 小时预测”“实时电价”。

### 策略中心

- 区分策略建议、审核状态、预测有效性、运行反馈与执行收益。
- `unreviewed` 映射为“未进入审核”；过期/未审核记录明确不可作为当前策略。
- 规则测算、测算收益和非实际结算显式区分；运行事实不可用时不补 0 成功态。

### 首页

- “策略预计收益”改为“预测峰谷价差”，并声明不代表收益或结算。
- 历史预测驱动 stale 状态；无数据不显示绿色正常，业务更新时间不使用浏览器加载时间。
- 1366/1440/1600 使用 3×2 KPI，1920 使用单行 6 卡；卡片无逐字换行、重叠或内容溢出。

### 数据中心

- Day4 的 11 个稳定 `dataset_id` 和物理对象封装保持不变。
- 展示业务名称、质量、更新时间、可用/过期/空表状态；普通用户不获得任意对象、Schema 或 SQL 能力。
- “实时电价”仅是白名单内真实市场数据集/字段，当前明确显示空表；它不是预测值，也未显示为实时成功态。

## 5. 测试与浏览器结果

| 门禁 | 结果 |
| --- | --- |
| Day5 定向隔离测试 | 110 passed、2 skipped；2 项为旧 Phase5-C 固定 0014/专用环境前提 |
| Day3/Day4 原生隔离回归 | 268 passed；public match、cleanup PASS、残留 0 |
| Day5 数据真实性契约 | 13 passed |
| 页面状态/静态契约 | 20 passed |
| Node 七态 | 7 passed |
| TypeScript `--noEmit` | PASS |
| Vite build | PASS，3675 modules |
| Python compileall | PASS |
| 报告硬编码扫描 | 0 命中 |
| “今日/当前/实时”误导扫描 | 0 有效命中；3 个文本命中均是否定/不可作为当前策略的安全说明 |
| 高置信敏感信息扫描 | 0 命中；真实 `.env`、Word、`backups/` 变更 0 |
| 浏览器核心页面矩阵 | 5 页面 × 4 分辨率 = 20/20 PASS；console error 0 |
| 首页 KPI 修复复验 | 4/4 PASS；6 卡、重叠 0、内容溢出 0、body 横向溢出 0 |

浏览器证据：

- `E:\智能运营分析项目_验证\beta10d_day5_browser_20260731.json`
- `E:\智能运营分析项目_验证\beta10d_day5_browser_dashboard_final_20260731.json`
- `E:\智能运营分析项目_验证\beta10d_day5_browser_runtime_final_20260731`

## 6. 历史测试债务台账

Day4 早期全历史诊断为 425 passed、23 failed、30 skipped、46 errors。当前同类诊断（Day3 门禁 6 项已单独通过，故本次排除该文件）为 463 passed、15 failed、30 skipped、24 errors；失败减少 8、错误减少 22。当前 JUnit：`E:\智能运营分析项目_验证\beta10d_day5_full_history_20260731.xml`。

| 分类 | 当前数量 | 明细 | Owner | 计划日期 |
| --- | ---: | --- | --- | --- |
| 已被 Day4/Day5 收敛 | 30 | 相对早期诊断净减少 8 failed、22 errors | Day4/Day5 主线 | 2026-07-31 已完成 |
| 环境依赖 | 45 | 24 errors：T002 三个模型二进制缺失；19 skips：T003 真实推理批；2 skips：RAG 知识库不可用 | 模型/测试基础设施；RAG 支线 | 2026-08-04（Day9 验收前） |
| 过时测试 | 5 failed | Phase5-A2 测试硬编码独立数据库，不能接受当前安全隔离 Schema | RAG ingestion/runtime | 2026-08-03（Day8 集成） |
| 当前真实缺陷 | 2 failed | AI 助手复制按钮契约、设置中心用户管理入口契约 | 主线前端 | 2026-08-04（Day9 UI/总验收） |
| Day5 范围 | 0 | 本轮真实性定向门禁无遗留失败 | Day5 主线 | 2026-07-31 已完成 |
| Day6 范围 | 9 skipped | Phase5-C 报告 2、Phase5-D 策略治理 7，需 Day6 专用隔离数据库参数 | Day6 闭环主线 | 2026-08-01 |
| Day7 范围 | 0 | Celery/任务状态正式回归已包含在 268 项门禁且通过 | Day7 主线 | 2026-08-02 复验 |
| Day8–Day9 范围 | 8 failed | AI 核心意图 1、A2 向量/索引 3、RAG hybrid 1、tariff/knowledge tools 3 | RAG 集成与 AI 工具线 | 2026-08-03 至 2026-08-04 |

分类为环境/后续范围不代表忽略；全历史诊断仍明确为 FAIL，未伪报全绿。Day5-owned 未解决项为 0。

## 7. PostgreSQL 指纹与隔离

接管检查点与最终值完全一致：

| 项目 | 接管前 | 最终 |
| --- | --- | --- |
| public 表/视图/序列/函数 | 62 / 8 / 47 / 37 | 62 / 8 / 47 / 37 |
| Alembic heads | `0016_strategy_runtime` | `0016_strategy_runtime` |
| 结构 SHA-256 | `9610393a5c8a626f3cea41c534145402a789bbe7cf68741c4869ed329827cf02` | 相同 |
| 全部表内容指纹 | 基线 | 全部相同 |
| 全部序列状态 | 基线 | 全部相同 |

所有隔离测试和两次浏览器运行均为 public match PASS、临时 Schema/角色残留 0。Day5 未修改 Day4 正式角色、ACL、运行账号或迁移账号。

## 8. RAG 与并行隔离

| worktree/分支 | 接管 HEAD | 最终 HEAD | 状态 | Day5 动作 |
| --- | --- | --- | --- | --- |
| 旧 RAG-R1 `beta10d/day4-data-access-security` | `7eaf8d3152f8ffe5bd983068a99145c9693b4925` | 相同 | clean | 只读 |
| `codex/rag-enterprise-ingestion` | `4cce50bf40fe1b50ddbe3bdd62e2c33aaf657227` | 相同 | clean | 未集成 |
| `codex/rag-enterprise-runtime` | `c79671c82b2b2cd6deedc0f9cb136349fc3d0b1d` | 相同 | clean | 未集成 |
| Day4 v2 | `e1be5d0bb4213daa52025e01cf84320f271d0898` | 相同 | clean | 只读 |

潜在冲突仅限统一来源/时效元数据、Router、公共配置与数据库契约；本轮不实现 RAG、Qdrant、Embedding、知识库权限或 AI 引用。

## 9. 原子提交与修改范围

1. `245cd3e3356b25bf311c639523b0db060591e61a` — shared fact metadata contract
2. `6d285b9fa4950f37476fe7364d59fbd699fc5874` — report truth remediation
3. `ff625e59d2089465add9a022971593eabb154d31` — forecast freshness
4. `8e3c5a1ed7d30904b24ce8cac5adc7637a9465bf` — strategy truth separation
5. `974d1e989527a18a0df656c64df58e5e68d32e81` — dashboard KPI semantics
6. `5e82fbc5f71fa729debc470ac720a2e5f2c7eea6` — truth contract tests
7. `beb4bc288cacaea7513e4790300c2948f8ebd272` — no-fallback page states
8. `6e7dcde6cf1544ff9aa6b84480ead987c68e0f7f` — responsive and review-state closure
9. 本报告所在提交 — status/register/evidence closure

最终相对 Day4 基线为 20 个文件：17 个代码/测试文件、2 个状态/集成登记文件、1 个证据报告；无 Alembic、Compose、公共配置、权限矩阵、RAG 或真实凭据文件。

## 10. 回滚与已知问题

- 代码回滚：在独立回滚分支按 8→1 逆序执行 `git revert <完整哈希>`，再 revert 收口文档提交；不使用 reset/clean。
- 数据库：Day5 对 public 无结构/内容/序列变更，无需数据恢复；若复验异常，以接管检查点和最终 guard JSON 做精确比较。
- 浏览器测试管理员仅存在于一次性 Day5 Schema，Schema 和角色已清理。
- 已知问题仅为第 6 节登记的历史环境/后续任务债务；不影响 Day5 真实性门禁。

最终判定：`PASS`。Day 6 准入：`GO`，但本轮未开始 Day 6。
