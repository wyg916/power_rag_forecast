# RAG-I5A Candidate 编排异常边界修复证据

## 基线与范围

- 基线提交：`8ed99cae74361905ebe874963eed5810f0bcd330`。
- 前置检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_191547_RAG_I5A_PRE`。
- 修改范围：Candidate 编排器、对应 fixture 测试和本证据，共 3 个文件；代码与测试净增 136 行。

## 修复结果

- 删除逐文档流程中的宽泛 `except Exception -> isolation` 行为。
- 仅 `CandidateOrchestrationError`、`ChunkBuildError`、`FrozenExportError` 这三类已知数据或契约失败可进入单文档隔离。
- 构建器、导出器及内部校验的未知程序异常立即中止整个 Candidate，分别只暴露固定脱敏错误码，不保留原始异常链。
- 隔离原因使用显式 allowlist；动态 block/chunk ID、上游 reason、路径或内容后缀不会写入 Candidate 清单；未分类的已知异常归一化为稳定拒绝码。
- 83 条台账终态、重复规则、确定性 ledger/corpus/artifact 哈希逻辑未修改。

## 测试

- 定向测试：`17 passed in 0.41s`。
- Candidate + I3 Chunk/Quality 回归：`24 passed in 0.60s`。
- 覆盖构建器与导出器未知 `RuntimeError` 整体中止、固定错误码、路径/内容脱敏、已知数据异常单文档隔离和未知已知异常归一化。

## 外部影响与回滚

- 未读取或处理 83 份正式资料；未写 `.runtime`、PostgreSQL、Qdrant、模型或发布状态；未调用网络、转换器或 OCR/VLM。
- 回滚使用普通 `git revert` 撤销本任务提交；检查点包含基线状态、关键文件哈希和恢复说明。
