# RAG-I4A 转换器与 OCR Provider 准入加固证据

## 基线与范围

- 基线提交：`4f91381986416e398eb7855e47abc2d6fddf749c`。
- 检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_184925_RAG_I4A_PRE`。
- 仅修改 I4 converter/OCR 协议、fake 测试和本证据。

## 加固

- `convert_document` 强制接收 `ConverterApprovalPolicy`；运行 spec 的 name、规范化绝对 executable、fixed_args 必须与 registry 中某项全等。
- 相对 executable、shell executable、未知 name、executable 漂移和 argv 漂移均在 staging 写入前 fail-closed；实际 argv 使用规范化 executable。
- `OCRRequest` 冻结 `expected_profile(provider, provider_version)`，并强制通过 `OCRApprovalPolicy` 显式 registry 准入。
- OCR/VLM 返回的 provider/version 必须与已批准 expected profile 精确一致；未知 provider、请求选择未批准 profile 或版本漂移均拒绝。
- 测试仍仅使用 fake runner/provider；未执行真实程序、下载/加载模型、联网、写 `.runtime` 或处理正式语料。

## 测试

- Converter 准入、漂移与既有失败门禁：`12 passed in 23.38s`。
- OCR provider/profile 准入、漂移与既有 OCR 门禁：`3 passed in 0.38s`。

## 回滚

- 数据库、Qdrant、模型和外部服务影响均为 0。
- 集成前放弃本提交；集成后使用普通 `git revert` 回滚，不删除或覆盖其他 I4 文件。
