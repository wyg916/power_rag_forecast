# Ingestion I2 结构化解析接收证据

## 接收边界

- 来源提交：`249662a4b5cab3ea1675f0bd97ea3cc57efca1ba`。
- 接收 13 个文件、净新增 626 行；仅含结构化解析契约、调度器、PDF/DOCX/HTML/XLSX 解析器、测试与 I2 原证据。
- 未接收分支合并、Alembic、Router、Compose、正式数据或运行态配置。

## 验证

- DOCX：段落/表格顺序与确定性；PDF：页、bbox、空白页 OCR 标记；HTML：标题/段落/表格/资产顺序；XLSX：全 Sheet 流式读取与资源门禁。
- 4 个解析器测试文件：`8 passed in 5.01s`。
- `git diff --cached --check`：PASS；敏感扫描在提交前执行。
- PostgreSQL、Qdrant、OCR/VLM、Corpus 和网络写入：0；未宣称 83 文件已解析或发布。

## 回滚

使用普通 `git revert <I2-integration-commit>`；无外部状态需要恢复。
