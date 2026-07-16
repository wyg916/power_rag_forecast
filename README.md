# 智能运营分析项目 Codex 分阶段执行包

## 使用顺序
1. 将本执行包中的 `AGENTS.md` 放到项目根目录。
2. 将 `docs/codex/` 整体复制到项目根目录下的 `docs/codex/`。
3. 首先把 `tasks/00_PHASE0_BASELINE.md` 的完整内容发送给 Codex。
4. Phase 0 完成并人工确认备份后，依次发送：
   - `01_T004_AUTH_FAIL_CLOSED.md`
   - `02_T001_MODEL_FACT_SOURCE.md`
   - `03_T002_SAFE_MODEL_CONTRACT.md`
   - `04_T003_RUN_ID_TRANSACTION.md`
   - `05_T005_SOURCE_CONTRACT.md`
   - `06_FINAL_ACCEPTANCE.md`
5. 每个任务必须单独开任务/对话；上一个任务验收通过后再进入下一个。

## 关键原则
- 一周仅以完成 P0 核心工程收敛和“可稳定本地运行”验收为目标。
- 不把 RAG 全量恢复、AI 100 题、报告策略状态机、完整企业部署等全部塞入同一周。
- 高风险步骤必须停下来请求人工确认。
