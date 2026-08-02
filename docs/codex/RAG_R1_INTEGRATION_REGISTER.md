# RAG-R1 最终集成登记

唯一基线：`7e8284f3b3ed7c748482066552da33857e2915b8`；集成分支：`beta10d/rag-r1-integration`。所有来源包均采用文件级审计与无提交 cherry-pick 接收，不合并任何候选分支。

| 顺序 | 包 | 来源提交 | 来源文件/有效变更 | 当前验证 | 外部写入 | 集成提交 |
|---:|---|---|---:|---|---|---|
| 1 | 公共契约冻结 | `e8052398…` | 4 / +604 | 契约测试 5 passed；diff check PASS | DB 0；Qdrant 0；模型 0；网络 0 | `d2fc8677…` |
| 2 | Ingestion I1 不可变源台账 | `49935aae…` + `410bbdaa…` + `63b79abe…` | 7 / +519 | I1 测试 7 passed；83/83 只读复核稳定 | DB 0；Qdrant 0；模型 0；Corpus 写入 0 | 本提交 |
| 3 | Ingestion I2 结构化解析 | `249662a4…` | 13 / +626 | PDF/DOCX/HTML/XLSX 测试 8 passed；diff check PASS | DB 0；Qdrant 0；OCR 0；Corpus 写入 0 | 本提交 |
| 4 | Ingestion I3 父子分块与引用定位 | `56b6575a…` + `792ee536…` | 11 / +768 | 分块/引用/质量/XLSX 测试 11 passed | DB 0；Qdrant 0；资产写入 0 | 本提交 |
| 5 | 公共 DTO 与迁移准备契约 M4 | `799f8dfa…` + Day 7A 最小适配 | 5 / +511，另 2 文件各 1–3 行适配 | DTO/静态迁移图测试 9 passed | DB 0；revision 0 | 本提交 |
| 6 | Ingestion I4/I4A 受控转换与 OCR 协议 | `4f913819…` + `ea056b82…` | 8 / +931 | 转换/OCR fail-closed 测试 15 passed | DB 0；OCR 模型加载 0；资产写入 0 | 本提交 |
| 7 | Ingestion I5/I5A Candidate 调度 | `8ed99cae…` + `0d24fdc3…` | 4 / +863 | Candidate 调度测试 17 passed | DB 0；Qdrant 0；正式 Candidate 写入 0 | 本提交 |
| 8 | Ingestion I6 Candidate 发布交接 | `4cce50bf…` | 4 / +630 | release envelope/handoff 测试 11 passed | DB 0；Qdrant 0；正式 sink 写入 0 | 本提交 |
| 9 | Runtime RT1 企业运行 profile | `0efc44d3…` + `0bc7a444…` | 7 / +724/-23 | runtime/health 一致性测试 25 passed | DB 0；模型加载 0；fallback 启用 0 | 本提交 |
| 10 | Runtime RT2 release-aware 混合检索 | `beeccbfe…` + `edbee654…` | 7 / +910 | hybrid/Qdrant adapter 测试 17 passed | DB 0；Qdrant 连接/写入 0 | 本提交 |
| 11 | Runtime RT3 Claim grounding 与内容安全 | `fe29c8bd…` | 9 / +620/-11 | grounding/content/hybrid 测试 35 passed | DB 0；正式检索/生成 0 | 本提交 |
| 12 | Runtime RT4 原子发布协议 | `a51b21ab…` | 3 / +823 | release service 测试 10 passed | DB 0；Qdrant alias 写入 0 | 本提交 |
| 13 | Runtime RT4A 事务终结修复 | `ed5f16f2…` | 3 / +183/-10 | release service 测试 14 passed | DB 0；Qdrant alias 写入 0 | 本提交 |
| 14 | Runtime RT4B embedding profile 准入 | `e0a437de…` | 3 / +86/-8 | release service 测试 19 passed | DB 0；模型加载 0 | 本提交 |
| 15 | 公共 M5 fail-closed 服务缝合 | 从 `948700f2…` 仅提取 service，拒绝 Router | 2 / +145 | 服务 seam 测试 9 passed | DB 0；Router 变更 0 | 本提交 |
| 16 | Runtime RT5 企业应用编排 | `834ef45e…` | 3 / +854 | application orchestrator 测试 10 passed | DB 0；Qdrant 0；正式事实写入 0 | 本提交 |
| 17 | Runtime RT5A 并发幂等修复 | `ab8df256…` | 3 / +164/-23 | orchestrator 测试 14 passed | DB 0；Qdrant 0；正式事实写入 0 | 本提交 |
| 18 | Runtime RT6 verified release adapter | `40d7e4c1…` + 1 行前序 schema 适配 | 5 / +840/-2 | adapter/release 测试 26 passed | DB 0；Qdrant 0；正式发布 0 | 本提交 |
| 19 | Runtime RT6A adapter 失败边界 | `c79671c8…` | 5 / +246/-7 | adapter/release 测试 40 passed | DB 0；Qdrant 0；正式发布 0 | 本提交 |
| 20 | PostgreSQL 0018 migration 实现与只读检查点 | 集成分支新增 | 6 个代码/测试文件，约 953 行 | 静态/目标守卫 13 passed；public 只读快照 PASS | DB 写入 0；public upgrade 0 | 本提交 |
| 21 | PostgreSQL 隔离 Schema 迁移回放 | 集成分支新增 | 2 个代码/测试文件，约 440 行 | 静态门禁 16 passed；`upgrade→downgrade→upgrade` PASS；两次 head 结构哈希一致；清理无残留 | public 写入 0；public revision/结构哈希前后一致 | 本提交 |
| 22 | M6 Qdrant 安全契约与 strict-mode 发布门禁 | `ec08c5af…` 安全核心，拒绝候选 `.env`/公共 Compose/Router | 7 个代码/测试文件，约 +280 | Qdrant/runtime/release/adapter/hybrid 75 passed | Qdrant 连接/写入 0；配置覆盖 0 | 本提交 |
| 23 | Qdrant 1.18.2 私有部署叠加层与 E 盘预检 | 集成分支新增，参考 `a902e5fc…` 门禁但不接收公共 Compose | 4 个部署/脚本/测试文件，约 +290 | 部署门禁相关 58 passed；占位配置 fail-closed | 镜像拉取 0；容器 0；E 盘资产写入 0 | 本提交 |
| 24 | Qdrant 1.18.2 固定镜像、本地 TLS 与角色权限实测 | 集成分支新增；用户确认外网拉取和 E 盘资产 | 5 个部署/脚本/测试/证据文件，约 +390 | bootstrap/preflight PASS；权限探针 9/9 PASS；静态测试 10 passed | E 盘新建运行资产；独立容器运行；Candidate/alias 写入 0 | 本提交 |
| 25 | BGE Embedding/Reranker 静态准入与全量哈希 | 集成分支新增 | 2 个脚本/测试文件，约 +300 | profile/license/manifest PASS；单测 3 passed | 网络 0；模型目录写入 0；权重反序列化 0 | 本提交 |
| 26 | 双模型离线数值烟测与企业 Runtime Profile | 集成分支新增 | 6 个脚本/测试/证据文件，约 +450 | Embedding/Reranker smoke PASS；Runtime contract issues 0；单测 13 passed | 网络 0；fallback 0；Git 外新增 model-profile.env | 本提交 |
| 27 | RAG-R1 旧旁路封口与本地模型加载加固 | 集成分支新增 | 3 个服务/测试文件，约 +120 | enterprise bypass/contract/hybrid 38 passed | 网络 0；Hash/heuristic/file fallback 触达 0 | 本提交 |
| 28 | 83 文件正式不可变源台账复核 | 集成分支运行 I1 | 1 个 ledger + 1 个证据摘要 | 83/83；SHA-256 与接管基线一致；I1 tests 7 passed | 源目录写入 0；DB/Qdrant/模型写入 0 | 本提交 |

下一阶段：Qdrant 1.18.2 安全契约与本地私有部署叠加层 → 双模型准入 → 83 文件正式处理 → Candidate Corpus/Collection → API/认证/AI/UI。
