# RAG-I1 实施证据

## 范围

- 分支：`codex/rag-enterprise-ingestion`
- 目标：83 份原始资料的稳定 source ID、SHA-256、格式准入、重复关系和确定性 JSONL 台账。
- 修改仅涉及 `knowledge_pipeline/enterprise/**`、一个定向测试文件和本证据文件。
- PostgreSQL、Alembic、配置、前端、旧处理器、原始资料写入：0。
- 网络调用、依赖或模型下载、正式发布：0。

## 验证

- 隔离专项测试：
  `python -m pytest -q -p no:cacheprovider --noconftest tests/test_rag_enterprise_ledger.py`
- 结果：`7 passed in 1.36s`。
- 首次未隔离 pytest 插件的调用在 60 秒门槛终止，未作为测试结果；随后禁用插件自动加载和仓库 conftest，避免无关运行栈及数据库接入。
- 权威原件目录固定为 `E:\智能运营分析项目\知识库`；该目录只读复测得到 83 条，`ready=58`、`duplicate=14`、`quarantined=11`、`corrupt=0`。
- 主代理针对权威原件完成同一 run 两次复测：首次为 `write_status=created`，第二次为 `write_status=unchanged`，文件修改时间未变化，台账 SHA-256 均为
  `EE61AF9A0AA4509B2E7947E37C99004E2029FBFD69A55FE663E8ACACAFEBF7D6`。
- RAG 工作树中的 `知识库` 是 Git checkout 副本，两份 HTML 因行尾规范化与权威原件存在字节差异，因此不可作为原件哈希或正式台账证据源；此前基于该副本得到的 `F36E...` 仅属无效工程探查结果，不作为验收结论。
- 不同内容写入同一 run 路径会以 `immutable_ledger_conflict` 拒绝。
- 重复内容 canonical 按 `ready → quarantined → 确定性路径` 选择，避免隔离文件抢占可解析原件。
- staging root 位于 corpus 内部时 fail-closed，避免运行产物改变原件盘点数量。
- `git diff --check`：通过。

## 状态语义

- `ready` 只表示进入后续解析候选，不等于 Candidate、Published 或 Active。
- `duplicate` 必须指向确定性的首个规范 source。
- 需要受控转换、OCR 或未知格式的资料进入 `quarantined`。
- 空文件、不可读文件和损坏容器进入 `corrupt`。

## 回滚与剩余项

- 回滚：在集成前放弃该支线提交，或集成后对本包提交执行普通 `git revert`；运行产物位于 `.runtime`，不进入 Git。
- 本包不判断扫描 PDF 的文本层质量，不解析正文、版面、表格或资产。
- WPS/DOC/OFD 转换、图片与扫描 PDF OCR、父子 Chunk、质量门禁和发布均由后续独立包完成。
