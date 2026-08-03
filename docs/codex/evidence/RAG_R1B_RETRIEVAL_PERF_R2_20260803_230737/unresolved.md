# 未解决项

1. Qdrant TCP 已可达，但正式 TLS/HTTP 健康、Candidate Collection、read-only key、release/collection/embedding profile 一致性尚未由主控确认。
2. 当前50题文件 human_verified=false；不能作为最终正式黄金集。
3. fresh CPU profile 因内存/I/O资源门禁在 model_loaded 前停止，0 forward；没有本轮新鲜 P50/P90/P95/P99。
4. 历史正式 reranker CPU warm P95 4158.143ms，单项已超过全链路 1500ms 门槛。
5. CUDA硬件存在，但现有 Torch 是 CPU-only；ONNX/ORT/Optimum 未安装；不得自行安装或改公共运行配置。
6. Dynamic INT8 历史 P95 2624.347ms，仍不达标且无质量等价证明。
7. 正式 cold/warm、hit/miss、Recall、MRR、critical、Citation、ACL 尚未 live 复验。
8. 生产 startup 未调用现有 reranker 预热入口；startup 文件不在本任务白名单。
9. release-aware rerank 结果缓存尚未实现；不能用于掩盖 warm miss。
10. 当前状态不得交主控接收。