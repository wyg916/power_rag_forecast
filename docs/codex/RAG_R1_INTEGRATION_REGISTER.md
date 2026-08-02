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

待接收顺序：I2 → I3 → I4/I4A → I5/I5A → I6 → RT1 → RT2 → RT3 → RT4/RT4A/RT4B → RT5/RT5A → RT6/RT6A → 公共冲突统一。
