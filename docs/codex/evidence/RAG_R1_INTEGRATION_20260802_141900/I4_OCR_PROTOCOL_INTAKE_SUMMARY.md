# Ingestion I4/I4A 受控转换与 OCR 协议接收证据

## 接收边界

- 来源：`4f91381986416e398eb7855e47abc2d6fddf749c`、`ea056b8258e19f38fb502a02936b03e4c353c7e7`。
- 接收 8 个文件、净新增 931 行；仅含受控 WPS/OFD 转换协议、OCR/VLM 契约与映射、测试及原证据。
- 未接收公共 Compose、Alembic、Router、模型二进制或正式运行资产。

## 依赖闭环

- 首次收集因缺公共 DTO 而失败，0 个测试执行；随后 M4 已独立接收并通过 9 项测试。
- 在 M4 之上复验转换/OCR 协议：`15 passed in 2.73s`。
- 覆盖 argv 数组、只读输入、白名单 profile、超时/输出失败、页尺寸/bbox/页身份和坏 OCR 结果 fail-closed。

## 当前真实状态

- 当前 Python 环境无 Paddle/PaddleOCR；本包只建立接口与门禁，OCR/VLM runtime 仍为 unavailable。
- PostgreSQL、Qdrant、模型加载、Corpus/资产和网络写入：0。
- 不把合成 runner 测试表述为正式 30 页 OCR/VLM 评测。

## 回滚

使用普通 `git revert <I4-integration-commit>`；无外部状态需要恢复。
