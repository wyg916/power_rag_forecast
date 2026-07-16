你正在处理“智能运营分析项目”。请严格遵守项目根目录 `AGENTS.md`、`docs/codex/PROJECT_BASELINE_SUMMARY.md`、`docs/codex/MASTER_ENGINEERING_RULES.md`，以及本任务文件。

执行要求：
1. 不重复全仓扫描，优先精确定位。
2. 任何修改前先建立任务级检查点并写入项目盘。
3. 不在 C 盘新增、删除或修改项目文件。
4. 不删除、批量移动或覆盖已有文件；需要时停止等待用户确认。
5. 回复保持简洁，完整证据写入 `docs/codex/evidence/`。
6. 遇到停止条件时不要变通，直接列出需要用户确认的事项。

# 任务：T005 — 移除真实页面 seed/fallback 冒充并统一来源契约

## 目标
让核心 API、Web 页面和 AI 工具读取同一个成功 run，并统一返回/显示 `source_type`、`domain`、`run_id`、`generated_at`、模型/特征版本和过期状态。无真实数据时显示可解释空态，不自动 seed 或回退旧文件。

## 前置门禁
T003 已验收，能够查询 latest_successful_run。未满足则停止。

## 范围
核心预测/模型相关 API 响应契约、前端来源状态条和空态、AI 工具适配、契约测试。不要进行大规模 UI 重构。

## 强制要求
- 读取接口无写副作用。
- source_type 使用严格枚举：real/historical/demo/seed/fallback/derived/unavailable。
- demo/seed/fallback 必须明显标记，不能被描述为实时真实数据。
- AI 工具没有真实 run 时返回 unavailable，不自行编造数值。

## 实施要点
1. 建立统一 response meta。
2. 页面显示来源、run_id、生成时间、模型和是否过期。
3. 空表显示原因与操作建议，不创建数据。
4. AI 工具默认接受 run_id；未传时仅使用 latest_successful_run。
5. 保留必要的旧接口兼容层并明确 deprecated。

## 验收测试
- 空数据库不会新增 seed。
- Web/API/AI 对同一查询返回相同 run_id。
- demo/历史/不可用状态显示正确。
- 连续 GET 不改变数据库。
- React typecheck/build、后端相关测试通过。

## 输出
给出统一契约示例、页面/AI 同源证据、空态证据、兼容策略和回滚路径。
