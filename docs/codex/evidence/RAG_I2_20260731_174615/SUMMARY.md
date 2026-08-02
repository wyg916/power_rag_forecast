# RAG-I2 结构化解析核心证据

## 范围与实现

- 分支：`codex/rag-enterprise-ingestion`。
- 新增统一 `ParsedDocument/Block/Table/Asset` 不可变契约、资源上限和 fail-closed 编排器。
- DOCX 按 `document.xml` 子元素原始顺序输出标题、段落和表格。
- XLSX 使用 `read_only=True/data_only=True` 流式遍历全部 Sheet，502 行 fixture 完整保留。
- HTML 保留 title、heading、paragraph、table、image 的全局顺序。
- 文本 PDF 输出 1-based 页码和 bbox；空白页只生成 `ocr_required` 资产，不伪造正文。
- 第三方解析依赖仅在解析器函数内懒加载；没有安装或下载依赖。

## 测试

- DOCX：`2 passed in 16.15s`。
- XLSX：`2 passed in 18.35s`。
- HTML：`2 passed in 8.47s`。
- PDF/编排门禁最终复跑：`2 passed in 0.50s`。
- RAG-I1 回归：`7 passed in 0.48s`。
- 四文件首次合并命令在 60 秒门槛内未完成且无结果，进程由超时机制终止；最终验收采用上述四个独立且均低于 60 秒的命令。
- 覆盖确定性重跑、损坏容器、非法编码、空文档、行数/页数资源上限和不支持格式隔离。

## 安全、影响与回滚

- 83 份权威原件批量解析或写入：0；测试仅使用 pytest 临时 fixture。
- PostgreSQL、Alembic、Qdrant、网络、模型、OCR/转换依赖、发布：0。
- 未修改旧 `knowledge_batch_processor.py`、配置、运行时检索或前端。
- 回滚：集成前放弃本提交，或集成后对本包提交执行普通 `git revert`。

## 未覆盖

- WPS、DOC、XLS、OFD 的受控转换尚未实现。
- PaddleOCR-VL、扫描页 OCR、DOCX 内嵌图片、PDF 表格/公式/图表识别尚未实现。
- 本包不生成父子 Chunk、Candidate Corpus 或 Published Release。
