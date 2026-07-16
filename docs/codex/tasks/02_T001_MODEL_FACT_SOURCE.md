你正在处理“智能运营分析项目”。请严格遵守项目根目录 `AGENTS.md`、`docs/codex/PROJECT_BASELINE_SUMMARY.md`、`docs/codex/MASTER_ENGINEERING_RULES.md`，以及本任务文件。

执行要求：
1. 不重复全仓扫描，优先精确定位。
2. 任何修改前先建立任务级检查点并写入项目盘。
3. 不在 C 盘新增、删除或修改项目文件。
4. 不删除、批量移动或覆盖已有文件；需要时停止等待用户确认。
5. 回复保持简洁，完整证据写入 `docs/codex/evidence/`。
6. 遇到停止条件时不要变通，直接列出需要用户确认的事项。

# 任务：T001 — 统一模型事实源并消除读时 seed 副作用

## 目标
将 `model_registry` 收敛为电价模型唯一事实源，确保 GET/查询接口绝对只读，并建立同一 domain+target 最多一个 Active 的约束与人工激活流程。

## 当前事实
- `model_registry=0`。
- `model_versions=5` 条 seed/展示记录。
- 唯一最新完整模型 `model_20260620_063015` 目前只能是 Candidate。

## 范围
模型注册仓储、服务、API、必要迁移、兼容读取和对应测试。不要加载 joblib，不要执行快速预测，不要删除 `model_versions`。

## 强制要求
- 开始前建立 T001 检查点；数据库只用隔离开发/测试库。
- GET 接口不得执行 seed、激活、同步或写入。
- 旧表保留，采用兼容层/只读迁移策略。
- 任何迁移必须有 downgrade，并先在空库/隔离库验证。

## 实施要点
1. 明确模型字段：domain、target、artifact_id、artifact_hash、feature_version、schema_hash、status、验证/激活时间等。
2. 建立 candidate→validating→validated→active→archived/rejected 生命周期。
3. 同一业务域和目标只允许一个 Active，使用数据库约束和事务保护。
4. 将 Web、快速预测入口和 AI 模型工具统一到同一查询服务；尚无 Active 时返回明确空态。
5. 将 seed 初始化迁移为显式 demo 命令，仅允许 demo 环境执行。

## 验收测试
- 连续读取模型列表/Active 100 次，数据库内容不变化。
- 没有 Active 时返回空态，不自动创建。
- Candidate 不自动激活。
- 同一 domain+target 无法同时出现两个 Active。
- 负荷模型不出现在电价模型域。
- 迁移 upgrade/downgrade 通过，旧数据未删除。

## 输出
给出唯一事实源结论、兼容策略、迁移/测试结果和回滚方法。
