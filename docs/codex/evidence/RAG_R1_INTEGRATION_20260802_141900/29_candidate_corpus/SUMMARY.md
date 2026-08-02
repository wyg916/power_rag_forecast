# RAG-R1 Candidate Corpus 构建

- 本步骤结论：`PASS`（仅代表 Candidate Corpus 构建通过；不代表发布、alias 切换或 RAG-R1 总验收通过）。
- 输入台账：83/83，SHA-256 `ee61af9a0aa4509b2e7947e37c99004e2029fbfd69a55fe663e8acacafebf7d6`；构建前重新扫描原目录并逐字节匹配台账。
- 模型契约：`BAAI/bge-large-zh-v1.5`，1024 维，manifest SHA-256 `a6854a4b265bc6c7159d02927ece3548e63e7b57cf49deee2a77b94bbb0ec3fa`；仅加载 tokenizer，权重反序列化 0、网络调用 0、fallback 0。
- Candidate：45 documents、8,339 chunks、0 assets、14 duplicates、24 isolations，终态合计 83；token 范围 3–480，超过 480 为 0，空 chunk/空 quote/控制字符均为 0。
- Citation：带页码 6,599、无页码 1,740；无页码来自 DOCX/HTML/XLSX 等不具备物理页定位的源格式，不伪造页码或 bbox。
- 隔离：台账既有 11；实际解析新增 11（4 份 PDF 存在无文本页/整页扫描，5 份 PDF 命中乱码字符门禁，2 份 HTML 为空）；Candidate 质量门禁新增 2（HTML 图片未具备可靠页码/bbox）。
- 资产：0。未把未定位 HTML 图片或待 OCR 页面伪装成可发布资产。
- Candidate corpus SHA-256：`2e50d392806dcb4959050ec6baed17ce0a4d071c741f91147a569cad6c357102`。
- Candidate 文件 SHA-256：`ed5f62ad50a36207ca7d0e729ae2bfb054e276b40816d8ac1da04eb376468ed7`，8,613,984 bytes。
- 构建报告 SHA-256：`b1da669260a326e0dba8063fe4ec12a300fe0adda30500cf096eddcdf87bcbe1`，26,263 bytes。
- 幂等：相同 release ID、时间戳、台账、模型 profile 二次完整运行，artifact/report 均返回 `unchanged`。
- 定向测试：36 passed；`git diff --check` PASS；变更文件敏感扫描 0 finding。
- 运行资产：`E:\智能运营分析项目\.runtime\rag\releases\RAG-R1`；原始资料和完整 Candidate 未提交 Git。
- 外部影响：源目录写入 0；PostgreSQL 写入 0；Qdrant collection/alias 写入 0；发布/生产切换 0。

## 未关闭门禁

- 24 份隔离项尚未处理，尤其 OCR/VLM 的 30 页人工标注、CER、表格单元格 F1、页码/元素定位与虚构数字门禁尚未验收。
- Candidate Collection、PostgreSQL Candidate 记录、payload indexes、snapshot、检索/AI 评测、alias 发布与回滚演练均未执行。
- 因此本步骤不得解释为 83 份资料已全部发布，也不允许进入生产切换。

## 回滚

- 代码回滚：`git revert <本包提交>`。
- 运行资产不自动删除；如需移除，必须按仓库规则对两个精确文件逐一列明并另行确认。
