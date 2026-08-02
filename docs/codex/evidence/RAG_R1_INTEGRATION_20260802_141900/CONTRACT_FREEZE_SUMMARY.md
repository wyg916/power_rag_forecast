# RAG-R1 集成契约冻结证据

## 基线与接收范围

- 集成基线：`7e8284f3b3ed7c748482066552da33857e2915b8`。
- 来源提交：`e8052398ee88046ef9182ddeb2cb01d976eba026`。
- 只接收 API/权限契约、迁移设计、Candidate Corpus JSON Schema 与对应契约测试，共 4 个来源文件。
- 未接收来源分支合并提交、治理基线、Compose、认证实现、运行态配置或其他越权文件。

## 验证

- `git diff --cached --check`：PASS。
- `E:\智能运营分析项目\.venv\Scripts\python.exe -m pytest tests/test_rag_enterprise_contract_spec.py -q`：`5 passed in 0.10s`。
- PostgreSQL DDL/DML：0；Qdrant 写入：0；模型加载：0；语料写入：0；外部网络调用：0。
- Candidate 激活、Active 切换、生产切换：NO。

## 回滚

该包提交后使用普通 `git revert <integration-commit>` 回滚；无外部状态需要恢复。
