# RAG-R1 双模型静态准入

- 结果：`PASS`。
- Embedding：`BAAI/bge-large-zh-v1.5`，MIT，BertModel，24 层/16 heads，1024 维，max length 512。
- Embedding manifest：`a6854a4b265bc6c7159d02927ece3548e63e7b57cf49deee2a77b94bbb0ec3fa`。
- Embedding weight：`pytorch_model.bin`，1,302,220,525 bytes，SHA-256 `bf84a56fb045c24e090495195584a3922c3e4204107f0bba8b79c11f67a207f2`。
- Reranker：`BAAI/bge-reranker-v2-m3`，Apache-2.0，XLMRobertaForSequenceClassification，24 层/16 heads，max length 8192。
- Reranker manifest：`2a581f058542bd175695f8f92097b7aa4fbdac637ad486739f26e4cbc11ca159`。
- Reranker weight：`model.safetensors`，2,271,071,852 bytes，SHA-256 `d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286`。
- 文件：Embedding 14 个/1,302,802,803 bytes；Reranker 15 个/2,293,567,037 bytes；零字节 0；LFS pointer 0。
- 网络调用：0；fallback：关闭；权重反序列化：0。
- 机器证据：`model_admission.json`。

## 回滚

代码使用 `git revert <本包提交>`；模型目录全程只读，无模型资产回滚动作。
