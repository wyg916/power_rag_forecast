# RAG-R1 enterprise retrieval binding pre-write checkpoint

- 时间：2026-08-02（Asia/Shanghai）。
- worktree：`E:\智能运营分析项目_worktrees\beta10d_rag_r1_integration`。
- branch：`beta10d/rag-r1-integration`。
- HEAD：`e9ad3566018d1a410a3d22dd17f9e939b7e3bc01`。
- Git 状态：clean；无已跟踪修改，无未跟踪文件。
- 数据库影响：本检查点及本阶段预检均为只读，业务持久化写入为 0。
- PostgreSQL 当前事实：`RAG-R1` 为 `candidate`，`is_current=false`；不存在 current published release。
- Qdrant 当前事实：`rag_chunks_RAG-R1` 存在 8,339 points，dense=1024/Cosine，sparse=`bm25`，strict mode=true；`rag_chunks_current` alias 不存在。
- 安全结论：当前 Candidate 不得被正式检索；新绑定必须在访问 collection 前因缺少 current published release 而 fail closed。

## 关键文件 SHA-256

- `backend/app/repositories/rag_enterprise_repository.py`：`14154C30A646058ACE6CD12E8825CBAA14D40B78A5D5D6C07E3378B6D1905000`
- `backend/app/services/qdrant_vector_store.py`：`AF563FBA2C2CA4E678822516EA5C8F43563C3732738ECE0018DBFEF4FF260B51`
- `backend/app/services/rag_runtime_contract.py`：`007442A89B6BBD3C03C2249D73C15BB23B2E95AEE42B4CBAB4A35E8574BCB7B2`
- `backend/app/services/rag_service.py`：`7A98212A520516395763CD89BD8D4FE6A9E3FBFB83A3EC5B504C7B092978BBE9`
- `backend/app/api/v1/endpoints/knowledge.py`：`E38CD15BC14A3507BFAD64A414DAE8A5B45E41071D27EC9BC8B94DD1558D5BFD`

## 计划修改与回滚

- 计划：增加只读 PostgreSQL current release 读取、Qdrant 只读 HTTP transport、BM25 query encoder、四方一致性绑定，并接入知识库 GET/POST search。
- 边界：不发布 Candidate，不切换 alias，不更新 PostgreSQL release，不写审计表；GET/Search 保持零写副作用。
- 回滚：对本任务提交执行普通 `git revert <commit>`；本阶段若没有数据库持久化写入，则无数据库恢复动作。
