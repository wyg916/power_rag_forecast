# 全站功能清单

## 统计口径

- UI 冻结：`UI_LAYOUT_FREEZE = TRUE`，本轮未调整页面布局、导航结构、卡片位置或视觉体系。
- 正式业务路由：32 个；可见交互元素：1,345 个。
- `FUNC-ID`：`FUNC-0001` 至 `FUNC-1345`，逐项明细见 `INTERACTIVE_ELEMENT_MATRIX.csv`。
- 状态：PASS 1,247；FAIL 0；Disabled-by-design 98；UNKNOWN 0。
- 数据链路：页面只消费 API；受控缺失数据仅由隔离生成程序写入一次性 PostgreSQL schema，再经 Repository/Service/API 返回。前端未生成业务数据，也未以失败后的成功态 fallback 补齐。

## 页面与交互汇总

| 业务域 | 路由数 | FUNC-ID | PASS | Disabled-by-design | FAIL |
|---|---:|---:|---:|---:|---:|
| 首页 | 1 | 27 | 26 | 1 | 0 |
| 数据中心 | 2 | 75 | 72 | 3 | 0 |
| 预测中心 | 3 | 101 | 98 | 3 | 0 |
| 策略中心 | 3 | 90 | 81 | 9 | 0 |
| AI 助手 | 4 | 220 | 208 | 12 | 0 |
| 报告中心 | 4 | 164 | 146 | 18 | 0 |
| 模型中心 | 4 | 120 | 116 | 4 | 0 |
| 知识库 / RAG | 4 | 148 | 136 | 12 | 0 |
| 任务中心 | 4 | 220 | 204 | 16 | 0 |
| 系统设置 | 3 | 180 | 160 | 20 | 0 |
| 合计 | 32 | 1,345 | 1,247 | 98 | 0 |

## 功能类别

清单覆盖当前页面可见的 `button`、`a`、`input`、`select/combobox`、`tab`、`menuitem`、复选/单选控件、分页、表格与图表入口，以及登录、搜索、筛选、刷新、导出、下载、生成、保存、详情、审核、发布、重试、取消、AI 提问、Provider 选择、ChatBI 分析、RAG 引用和 Memory 会话操作。

Disabled-by-design 仅用于当前身份无权限、无选中记录、运行中防重复提交、Candidate 不得自动晋升、正式执行未获批准等明确边界；页面没有 UNKNOWN 或“看似可点但无业务实现”的入口。

## 证据

- `docs/codex/evidence/FINAL_FUNCTIONAL_ACCEPTANCE_20260812_153751673/INTERACTIVE_ELEMENT_MATRIX_current_pre_route_fix.csv`
- `docs/codex/evidence/FINAL_FUNCTIONAL_ACCEPTANCE_20260812_153751673/browser_current_final_pre_chatbi_route_fix.json`
- `docs/codex/evidence/FINAL_FUNCTIONAL_ACCEPTANCE_20260812_153751673/browser_release_final_routes.json`
- `docs/codex/evidence/FINAL_FUNCTIONAL_ACCEPTANCE_20260812_153751673/api_functional_audit_rc4.json`

