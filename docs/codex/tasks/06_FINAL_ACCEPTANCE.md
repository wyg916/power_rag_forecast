你正在处理“智能运营分析项目”。请严格遵守项目根目录 `AGENTS.md`、`docs/codex/PROJECT_BASELINE_SUMMARY.md`、`docs/codex/MASTER_ENGINEERING_RULES.md`，以及本任务文件。

执行要求：
1. 不重复全仓扫描，优先精确定位。
2. 任何修改前先建立任务级检查点并写入项目盘。
3. 不在 C 盘新增、删除或修改项目文件。
4. 不删除、批量移动或覆盖已有文件；需要时停止等待用户确认。
5. 回复保持简洁，完整证据写入 `docs/codex/evidence/`。
6. 遇到停止条件时不要变通，直接列出需要用户确认的事项。

# 任务：Final — “可稳定本地运行”总验收，只验证不扩展功能

## 目标
在隔离环境执行阶段三总验收，判断项目是否可以从“开发演示”升级为“可稳定本地运行”。不得为通过测试而临时关闭安全、写 seed、跳过契约或修改验收标准。

## 验收范围
1. 基线恢复材料完整。
2. production 认证 fail-closed。
3. 唯一模型事实源与唯一 Active。
4. 模型安全加载、严格 170 项契约和负向测试。
5. 两次端到端 run，各 24 行，旧批次共存。
6. 同 run 幂等、故障注入完整回滚。
7. Web/API/AI 同一 run_id 和来源标签。
8. 原有 FastAPI health、React build/typecheck、数据库迁移不回退。
9. 无 C 盘项目写入、无文件删除、无正式库写入。

## 双跑步骤
使用冻结输入依次执行两次完整链；保存 input_hash、result_hash、model_version、feature_version、run_id、24 行数量和查询结果。再执行至少两项故障注入，证明无半成品。

## 输出判定
- PASS：全部 P0 门禁通过，明确仍不等于企业生产部署。
- CONDITIONAL PASS：仅存在不影响核心闭环的 P1 问题，并逐项列出。
- FAIL：任一 P0 未通过。

生成 `docs/codex/evidence/FINAL_<timestamp>/acceptance_report.md` 和简洁最终回复。不要在验收阶段新增功能或大规模修复；发现问题只定位并建议回到对应任务。
