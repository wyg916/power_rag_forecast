# RAG-R1 enterprise retrieval binding

- 状态：`PASS`（仅企业检索绑定与只读知识库入口；Candidate 仍未发布）。
- 新增 PostgreSQL 唯一 current published release 只读读取；事务显式 `READ ONLY`，tenant 固定为认证上下文的 `default`。
- 新增 Qdrant 1.18.2 只读 REST transport；仅允许 GET 与查询型 POST，使用 API 专用只读 Key，BM25 profile 在加载时校验自哈希。
- 检索前强制核验 PostgreSQL current、运行时 release/profile、Qdrant alias、Collection dense/sparse/strict 配置及 payload profile；任一不一致均 fail closed。
- 正式点查询只允许通过 `rag_chunks_current` alias，且继续强制 tenant、ACL、published、有效期、embedding 与 sparse profile 过滤和返回 payload 二次校验。
- 知识库 GET/POST Search、QA Test 和 Batch Validate 已注入服务端认证身份、角色、run_id 与 trace_id；客户端 tenant 覆盖继续返回 400。
- 当前真实状态为 `RAG-R1/candidate/is_current=false` 且 alias 不存在；受限数据库身份真实 API 冒烟返回 200 + `release_unavailable`，Qdrant transport 构造 0 次，Candidate collection 未查询，内部诊断原因未泄露。
- 三张检索审计表真实冒烟前后计数均为 `[0,0,2]`，持久化写入 0；Candidate、alias、snapshot、Published 与生产切换均未改变。
- 定向回归 `170 passed, 2 skipped`；Python compile、权限矩阵 `--check`、`git diff --check` 和真实敏感值扫描均 PASS。
- 范围：9 个代码/测试文件，907 行新增，小于 20 文件/1000 行门禁。

## 尚未收口

- API 进程仍需独立安全配置包：只能注入 Read-only Qdrant Key，并显式提供镜像 digest、BM25 profile path、受限 DATABASE_URL 与独立 SECURITY_DATABASE_URL；不得直接加载同时含 Admin Key 的控制面 env。
- 当前无 current published release，因此正向真实 Qdrant hybrid 查询必须等待 Candidate 全部门禁通过与受控发布；本包只证明一致状态的单元正向路径和当前真实状态的 fail-closed 路径。
- 探索性组合回归发现既有 legacy `test_rag_hybrid` 单测仍失败；其执行路径不经过本次 enterprise 分支，已保留到最终全量回归任务处理，不据此宣称 RAG-R1 总体完成。

## 回滚

- 代码与任务状态：对本任务提交执行 `git revert <commit>`。
- 数据库：本包持久化写入 0，无数据库恢复动作。
- Qdrant：本包未切 alias、未写 collection、未生成 snapshot，无 Qdrant 回滚动作。
