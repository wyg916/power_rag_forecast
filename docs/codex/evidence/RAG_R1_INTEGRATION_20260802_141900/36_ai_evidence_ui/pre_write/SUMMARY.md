# AI 证据 UI 写前检查点

- 时间：2026-08-02（Asia/Shanghai）
- 分支：`beta10d/rag-r1-integration`
- 基线提交：`08bef8d978c2f0157d70a7682481196204547eb3`
- 写前工作树：干净；无 tracked diff；无未跟踪文件。
- 数据库影响：无。本包不执行 SQL、迁移、seed、发布或回滚。
- RAG 运行时影响：无。本包不访问 Qdrant，不改变 alias、release 或 snapshot。
- Candidate 约束：保持 `candidate / is_current=false`，不晋升、不发布。

## 计划修改

- `frontend/src/pages/assistant/AssistantPage.tsx`
- `frontend/src/styles.css`
- `tests/test_ai_frontend_display_contract.py`
- `tests/test_assistant_copy_contract.py`
- `docs/codex/TASK_STATUS.md`
- 本证据目录下的测试与验收摘要

## 关键文件 SHA-256

- `frontend/src/pages/assistant/AssistantPage.tsx`：`39eff418c1050edd30d107fb72cf3799ae222ade6841be5f6590f8c6cbadfd79`
- `frontend/src/styles.css`：`2031a327a24a0be3547a4e0ac1680a8892325f9b763ae991c3d25c158ef30c2d`
- `tests/test_ai_frontend_display_contract.py`：`c470764d945f62d137cfb4b12293e12a2d9ff9ca47496889ee667d60c3fd5a5d`
- `tests/test_assistant_copy_contract.py`：`7ac41870944f7a82e6b59e6fbfa1640b8d8e70114ab55fa5f417b6b56b22db06`
- `docs/codex/TASK_STATUS.md`：`49bf25eac2a20613ec97ff8b347a3935666f399890ddf9dfe64949b01244225e`

## 回滚

本包完成后使用独立提交交付。若需回滚，仅回退该 UI 提交；数据库与 RAG 运行时无需恢复。
