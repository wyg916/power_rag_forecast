# RAG-I4 受控转换与 OCR/VLM 协议证据

## 实现

- 分支：`codex/rag-enterprise-ingestion`；起点：`e19be4c878fc3f00f564bce5f085827ba582578a`。
- WPS/DOC/OFD 仅允许转换为固定 DOCX/PDF；runner 只接收 argv tuple，无 shell 参数。
- 原件不传给 runner：先哈希复制到 staging 内只读输入；输入/输出均验证在 staging root 内且禁止覆盖。
- timeout、非零 exit、输入变化、缺失输出、DOCX/PDF magic/结构和输出 SHA-256 全部 fail-closed。
- OCR/VLM 协议覆盖 PDF/JPG/JPEG、tenant/version/status、source hash、page/page size、bbox、text/table/formula/chart/image、text/cells、confidence 和 content hash。
- OCR 门禁拒绝来源哈希不一致、页码/页尺寸错位、bbox 越界、空结果、重复 element ID、坏类型/内容/hash/confidence、未完成状态及新增数字。
- 每页必须携带源页数字证据（允许显式空集合）；OCR 输出数字集合必须是源页集合的子集。
- 通过门禁的结果确定性映射为 `ParsedDocument/Block/Table/Asset`；failed/incomplete 结果无法进入映射或 `build_candidate`。
- 表格/公式/图表/图片可无损导出为主线 `AssetContract`，Chunk Citation 可通过主线 `CitationContract`；测试直接执行 DTO 校验。

## 测试与边界

- 转换测试只使用 fake runner 和 pytest 临时目录，不调用真实程序。
- OCR/VLM 测试只使用 fake provider，覆盖 JPG 多元素、双页扫描 PDF、表格/公式/图表/图片和坏例。
- RAG-I4 合并测试：`12 passed in 1.56s`；最终转换定向复跑：`9 passed in 1.73s`。
- RAG-I3 回归：`9 passed in 0.36s`；I2 HTML/PDF 回归：`4 passed in 0.65s`。
- 一次 25 题合并回归测试本体完成，但进程清理超过 60 秒命令上限，未将该次执行计作正式 PASS；以上分组成功结果为交付证据。
- 未下载、安装或加载 PaddleOCR-VL、LibreOffice、OFD 工具或模型；未联网，未写 `.runtime`，未处理 83 份原件。
- 未连接 PostgreSQL/Qdrant，未修改迁移、API、公共配置、运行时检索或前端。

## 回滚

- 本包仅新增 ingestion 协议、fake 测试和本证据；集成前放弃提交，集成后使用普通 `git revert` 回滚。
