# RAG-R1B OCR/VLM 30页任务证据

## 结论

- 分支与开始基线：`beta10d/rag-r1b-ocr` / `ec78c569bd4036f23341e40b2d4d212a6f85177c`。
- 固定抽取 10 份本地 PDF 的 30 个唯一页面，3 批、每批 10 页，覆盖扫描 PDF、文本 PDF、表格、复杂表格、图表、公式、多栏、数字密集和中英文混排。
- 生成 200 DPI 原页图、源文件/页面图/候选/归档 SHA-256、盲标模板、候选复核材料和联络图。
- 未连接数据库，未调用网络，未调用或加载 OCR/VLM 模型，未修改生产 API、配置、Compose、release、alias 或 snapshot。
- 人工标注与独立复核未完成，正式状态为 `MANUAL ANNOTATION REQUIRED`；CER、表格 F1、定位完整率和虚构数字正式分数均未计算，不得解释为 0 或 PASS。

## 实现

- `scripts/rag_r1_ocr_acceptance.py`：固定30页制包、严格金标契约、源文件与200 DPI重渲染校验、CER、表格单元格F1、IoU定位完整率、数字多重集门禁、稳定ZIP和CLI退出码。
- `tests/test_rag_r1_ocr_acceptance.py`：分层/分批、NFKC/CER、空单元格、25元素以上匹配、重复虚构数字、错误页码、固定阈值、盲标隔离、稳定ZIP和人工状态测试。
- `tests/evaluation/rag_r1_ocr_gold_30.json`：30页人工金标模板；所有页面均为 `template`，标注/复核字段为空，未预填自动候选内容。

## 标注包

- `rag_r1b_ocr_annotation_batch_01.zip`：10页盲标包，SHA-256 `795b3f2b87c205a199073c34a92684f3d7ae089751ee1a703a3cd7660b562677`。
- `rag_r1b_ocr_annotation_batch_02.zip`：10页盲标包，SHA-256 `fe4e69d01f4485acc19b875a44f041ca4c64929e3b27a35603e5a1434bbc18ba`。
- `rag_r1b_ocr_annotation_batch_03.zip`：10页盲标包，SHA-256 `a2ec85c789b5899318b47f0145fc1f9056095b9806bfd3ce850d1426da4a70d2`。
- `rag_r1b_ocr_candidate_review.zip`：30页候选与bbox叠框，仅供盲标提交后复核；SHA-256 `72a9a7ef904aef9dcb8b3d3608f6822ee26fb3e3bc09c30bad3582d3858592db`。
- `package_manifest.json`：10源、30页、分类、路径与哈希清单。
- `rag_r1b_ocr_contact_sheet.png`：30页联络图；已目视确认无黑页、裁切或渲染失败。

## 测试与扫描

- 新增验收测试：`5 passed in 11.50s`。
- 现有 OCR 流水线回归：`3 passed in 0.33s`。
- 制包双跑：两次输出的 3 个盲标包、候选包、联络图和 manifest SHA-256 完全一致。
- `validate-gold`：退出码 `3`，30页逐页报告 `page_not_verified`，`metrics=null`。
- AST、`git diff --check`：通过；新增有效代码 999 行，未越过 1000 行停止线。
- 敏感信息扫描：通过，0 命中；证据不含密码、Token、API Key 或连接串。
- 运行环境：项目虚拟环境 Python 3.11，pytest 8.4.2，PyMuPDF 1.28.0，Pillow 12.3.0；使用 `-B`、禁用 pytest 插件自动加载与 cacheprovider。

## 人工待办

1. 初标人员仅打开三个盲标包，逐页填写非表格文本、元素类型/阅读序/bbox、表格及单元格行列/span/text/bbox、页码和核验数字；不得先看候选包。
2. 初标提交并固化哈希后，由不同复核人员打开候选复核包逐项复核；填写两人 ID、带时区时间戳和五项检查，清空 `unresolved_issues`。
3. 仅当30页全部双审为 `verified` 后运行 `evaluate`；正式门禁固定为 CER `<=5%`、表格F1 `>=0.90`、定位完整率 `100%`、虚构数字 `0`。

## 回滚

- 任务无数据库影响，不需要数据库恢复。
- 提交后由主控执行 `git revert <任务提交>` 可完整回滚；未授权本任务自行 merge、cherry-pick、rebase 或发布。
- 开始前检查点位于本目录 `baseline/`，包含状态、差异、未跟踪文件、清单、关键哈希、环境和恢复说明。
