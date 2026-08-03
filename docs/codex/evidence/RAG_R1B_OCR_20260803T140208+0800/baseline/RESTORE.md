# 恢复说明

- 基线分支：`beta10d/rag-r1b-ocr`
- 基线提交：`ec78c569bd4036f23341e40b2d4d212a6f85177c`
- 任务开始时工作树干净。
- 仅白名单文件和 `docs/codex/evidence/RAG_R1B_OCR_*` 可变化。
- 恢复方法：由主控对任务提交执行 `git revert <commit>`；或从上述基线提交逐文件恢复白名单文件。
- 禁止在本任务中自行 merge、rebase 或 cherry-pick。
