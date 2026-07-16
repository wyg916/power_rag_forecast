# 知识库批量整理工具

本工具用于把多格式电力市场资料批量整理为可追溯的 Markdown 文件和标准 `chunks.jsonl`，供后续 BGE embedding、FAISS、Chroma 或 PostgreSQL 知识库入库使用。

## 支持格式

| 类型 | 处理方式 |
|---|---|
| PDF | 使用 PyMuPDF 提取每页文本，扫描版 PDF 不做 OCR，写入失败清单。 |
| DOCX | 使用 python-docx 提取段落和表格，表格转 Markdown。 |
| DOC | 优先调用 LibreOffice 转 DOCX，再按 DOCX 处理。 |
| XLSX | 使用 openpyxl 读取所有 sheet，空 sheet 跳过，超大 sheet 会截断。 |
| XLS | 优先调用 LibreOffice 转 XLSX，再按 XLSX 处理。 |
| WPS | 优先调用 LibreOffice 转 DOCX，失败后写入失败清单。 |
| ET | 优先调用 LibreOffice 转 XLSX，失败后写入失败清单。 |
| HTML | 使用 BeautifulSoup 去除脚本、样式、导航、页脚并提取正文。 |
| TXT/MD | 按 UTF-8、UTF-8-SIG、GBK、GB2312、GB18030 等编码读取。 |
| 异常后缀/无后缀 | 读取文件头，尝试识别 PDF、Office Open XML、HTML 或文本。 |

不支持或需要人工处理的格式包括扫描版 PDF、图片、OFD、压缩包、无法识别的下载残留文件，以及无法自动转换的 WPS/ET/DOC/XLS。

## Windows 安装依赖

```bash
pip install -r knowledge_pipeline/requirements.txt
```

DOC、XLS、WPS、ET 自动转换依赖 LibreOffice。安装后工具会自动查找：

```text
C:\Program Files\LibreOffice\program\soffice.exe
C:\Program Files (x86)\LibreOffice\program\soffice.exe
```

也可以把 `soffice.exe` 加入系统 PATH。

## 运行示例

Dry-run 只扫描文件和格式分布：

```bash
python knowledge_pipeline/knowledge_batch_processor.py --input "知识库" --output "knowledge_pipeline" --dry-run
```

小批量测试：

```bash
python knowledge_pipeline/knowledge_batch_processor.py --input "知识库" --output "knowledge_pipeline" --max-files 10 --verbose
```

完整处理：

```bash
python knowledge_pipeline/knowledge_batch_processor.py --input "知识库" --output "knowledge_pipeline"
```

断点续跑：

```bash
python knowledge_pipeline/knowledge_batch_processor.py --input "知识库" --output "knowledge_pipeline" --resume
```

## 输出文件

| 路径 | 说明 |
|---|---|
| `markdown/` | 每个原始文件对应一个独立 Markdown，包含来源路径、文件类型、大小、分类和文本 hash。 |
| `chunks/` | 每个文件对应的 chunk JSONL，便于单文件追踪。 |
| `output/chunks.jsonl` | 全局标准 RAG chunks，每行一个 JSON。 |
| `output/failed_files.csv` | 失败文件清单和建议动作。 |
| `output/processing_log.txt` | 每个文件的处理状态日志。 |
| `output/processing_report.md` | 总体统计、分类、失败列表和验证结果。 |
| `output/validation_report.json` | `chunks.jsonl` 可用性验证结果。 |
| `output/processed_manifest.json` | resume 使用的已处理文件 hash 清单。 |

## chunks.jsonl 字段

每行包含：

```json
{
  "chunk_id": "knowledge_000001",
  "source_file": "原始文件.pdf",
  "source_path": "知识库/原始文件.pdf",
  "file_type": "pdf",
  "category": "电力现货交易",
  "title": "原始文件",
  "chunk_index": 1,
  "chunk_total": 3,
  "text": "chunk正文",
  "keywords": ["电力市场", "现货交易", "日前市场"],
  "text_hash": "sha256",
  "created_at": "yyyy-mm-dd hh:mm:ss"
}
```

## 接入后续 RAG

推荐两种方式：

1. 将 `knowledge_pipeline/markdown/` 加入现有 `rag_service.SEARCH_ROOTS` 或后续索引脚本的扫描目录，然后调用现有知识库索引流程生成 BGE embedding。
2. 读取 `output/chunks.jsonl`，按 `source_file/source_path/title/category/text/keywords` 写入知识库表或向量库，再调用 BGE embedding 生成向量。

本工具只做标准化文本和 chunk 输出，不直接写入 PostgreSQL、FAISS 或 Chroma。

## 常见问题

- 扫描版 PDF 为什么失败：当前阶段不引入 OCR，避免增加重依赖和误识别风险。
- DOC/XLS/WPS/ET 转换失败：请安装 LibreOffice，或手动另存为 DOCX/XLSX 后重新运行。
- 表格为什么被截断：默认每个 sheet 最多读取 500 行，防止超大表格卡死。
- 异常后缀文件如何处理：工具会先识别文件头，无法判断时写入 `failed_files.csv`。
- 原始文件是否会被移动：不会，工具只读取原始文件，所有输出都写到 `knowledge_pipeline/`。
