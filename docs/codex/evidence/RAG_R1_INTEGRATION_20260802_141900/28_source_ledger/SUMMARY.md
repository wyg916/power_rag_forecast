# RAG-R1 83 文件正式源台账

- 结果：`PASS`。
- 输入：`E:\智能运营分析项目\知识库`，只读扫描。
- 文件：83/83；总字节 44,314,588；零字节 0。
- 终态：ready 58、duplicate 14、quarantined 11、corrupt 0。
- 隔离原因：受控转换 8、OCR 2、unsupported/unknown 1；重复内容 14。
- Ledger SHA-256：`ee61af9a0aa4509b2e7947e37c99004e2029fbfd69a55fe663e8acacafebf7d6`。
- 稳定性：文件数、字节数、状态分布和 ledger hash 均与接管前基线一致。
- 源目录写入：0；数据库写入：0；Qdrant 写入：0；模型加载：0。
- 机器证据：`RAG-R1-20260802-ledger/source_ledger.jsonl`。

## 回滚

台账为证据文件；代码未改变。若需撤销，仅执行 `git revert <本包提交>`，不触碰原始资料。
