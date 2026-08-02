# RAG-R1 双模型运行时验收

- 结果：`PASS`。
- 执行：CPU、离线、顺序隔离子进程；Hub/遥测/GPU 关闭；网络调用 0；fallback 0。
- Embedding：输出 shape `3×1024`，三个向量 norm 均为 `1.0`；相关相似度 `0.831930`，无关相似度 `0.157897`，margin `0.674033`。
- Reranker：相关得分 `0.998397`，无关得分 `0.000017`，margin `0.998381`；模型配置 max length 8192，烟测使用 512。
- 版本：Embedding `sha256:a6854a4b265bc6c7159d02927ece3548e63e7b57cf49deee2a77b94bbb0ec3fa`。
- 版本：Reranker `sha256:2a581f058542bd175695f8f92097b7aa4fbdac637ad486739f26e4cbc11ca159`。
- 企业 Runtime Contract：issues 0；Qdrant TLS/strict/read-only/digest、BGE 1024、reranker、release/collection/alias 全部一致。
- Runtime 进程只获得 Read-only Key，Admin Key 未进入合并配置或报告。
- Git 外配置：`model-profile.env` 已以独立新文件创建并限制 ACL；没有覆盖 `runtime.env`。
- 机器证据：`model_runtime_smoke.json`、`runtime_profile.json`、`model_profile_report.json`。

## 回滚

停止相关运行进程；保留模型目录不变。代码使用 `git revert <本包提交>`。Git 外 `model-profile.env` 不自动删除，如需清理须另行按单文件精确确认。
