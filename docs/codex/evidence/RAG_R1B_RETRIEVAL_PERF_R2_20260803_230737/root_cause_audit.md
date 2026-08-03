# RAG-R1B reranker 21 项根因审计

## 固定边界

- 分支：beta10d/rag-r1b-retrieval-performance
- 起始 HEAD：4a514d34113ee06a5725fa3f23bcf28298374040
- 正式模型：bge-reranker-v2-m3，准入 manifest sha256:2a581f058542bd175695f8f92097b7aa4fbdac637ad486739f26e4cbc11ca159
- 正式配置：CPU、batch 8、max length 128；Embedding 仍为 BGE 1024。
- 未修改 Compose、公共配置、数据库、migration、release、alias 或 snapshot；未关闭 ACL、Citation 或 reranker。

## 逐项证据

| # | 核验项 | 结论与证据 |
|---:|---|---|
| 1 | 模型是否单例 | 是，限定为同 Python 进程、同完整模型身份键。rerank_service.py 208-253 的缓存键含规范化模型路径、模型名、版本、设备、batch 和 max length；并发加载测试通过。不同进程仍各加载一份。 |
| 2 | tokenizer 是否单例 | 是，限定为同一 provider/进程。rerank_service.py 85-129 的 tokenizer 与 model 受同一 load lock 和双重早退保护；测试记录仅加载一次。 |
| 3 | 每请求是否重载 | 否。每请求调用 get_reranker，但命中进程缓存；_load_model 再次早退。模型身份或进程变化才重载。 |
| 4 | model.eval | 是。rerank_service.py 125-128 在发布实例前执行 model.eval；新增测试实测 model_eval_calls=1。 |
| 5 | inference_mode/no_grad | 使用 torch.inference_mode，见 rerank_service.py 150-152；每个真实 batch forward 均在该上下文内。 |
| 6 | 是否逐候选 forward | 否。rerank_service.py 138-153 按 batch 切片。17 候选测试的 forward batch 为 8/8/1。 |
| 7 | 是否真正批量 | 是。tokenizer 接收完整 pairs 列表，每个切片只调用一次 model。正式 3/5/8 候选在 batch 8 下通常各为一次 forward。 |
| 8 | batch size | 正式 profile 为 8；历史正式微基准也是 batch 8。新鲜 batch 1/2/4/8 扫描因资源门禁未进入 forward，未据此改配置。 |
| 9 | 候选数量 | 当前50题按 dynamic_k 为：3 个候选 9 题、5 个 38 题、8 个 3 题；Qdrant 每模式召回 20/20/32，再经身份归并与 RRF 截为 3/5/8。 |
| 10 | 每候选 token 长度 | 生产文本先截为 1800 字符，正式 tokenizer max length 128。资源门禁前确定性五段字符数为 3/19/29/64/926；真实 token shape 未完成，不能据此缩短正式长度。 |
| 11 | padding | padding=True，为当前 batch 最长序列补齐；新增测试直接断言该参数。 |
| 12 | truncation | truncation=True，正式 max length 128；新增测试直接断言。64/96 仅列入未完成实验，不曾修改正式配置。 |
| 13 | CPU 线程配置 | 服务未设置 Torch 线程；当前项目运行时默认 intra/inter 为 6/6。独立历史微基准使用 8/1。 |
| 14 | intra/inter-op | 默认 6/6 可设置，历史 8/1 优于 4 线程；新鲜 4/6/8/12 扫描在 model_loaded 前触发资源门禁，不能形成新的最优结论。 |
| 15 | CUDA | 机器有 GTX 1660 Ti 6GB，驱动可见；但项目与系统 Torch 均为 CPU-only，CUDA tensor 不可用。现有 device 路径支持 cuda 字符串，但当前运行栈不能执行。 |
| 16 | ONNX Runtime | 架构有导出定义，但 onnx、onnxruntime、optimum、onnxscript 均未安装；2.29GB FP32 reranker 还需要 external-data，当前内存余量不足。未安装依赖、未导出或写模型。 |
| 17 | CPU INT8 | 历史 dynamic INT8 warm P95 2624.347ms，较 FP32 改善 38.24%，但仍高于 1.5s 且 cold forward 回退到 6715.390ms；无正式质量等价证明，未采用。静态 INT8 仅 tiny-model smoke，正式模型不可行性仍未解除。 |
| 18 | rerank 前重复归并 | 已先按 document_id/version_id/content_hash 跨 dense/sparse 归并，再 RRF 截断。该身份归并保留 Citation 身份。 |
| 19 | parent expansion 顺序 | 顺序为 RRF/截断、parent expansion、内容安全、rerank。父块用于安全扫描，但 reranker 只读 title/content/source，所以父块不增加 reranker token；不能移到安全检查后。 |
| 20 | 重复文本反复 rerank | 原代码会对身份不同但最终输入完全相同的候选重复推理。本轮改为单次调用内对最终截断文本精确去重，只计算唯一 raw logit，再映射回每个候选后统一归一化；候选、ACL、Citation、身份和各自 hybrid score 均保留。正式 corpus 8339 个 chunk 中有 7235 个唯一输入、746 个重复组、1104 个超额重复 chunk，最大组 12；这不等同于正式 top-k 重复率。 |
| 21 | release-aware rerank 缓存 | 现有 release-aware key 包含 tenant/user/roles/ACL fingerprint/release/collection/embedding/query/filter/top_k，但只有键计算，没有结果缓存；reranker cache 仅缓存模型实例。跨请求 rerank 缓存尚未实现，安全键还必须含 reranker模型/版本/max length、有序候选身份/文本/分数指纹和 TTL，并且每次响应仍须执行 Citation。它不能解决 warm miss，本轮未用缓存制造 PASS。 |

## 优化顺序落实

1. 模型/tokenizer 进程级单例：已存在并复核。
2. 预热：prewarm_reranker 已存在，正式 warm 验收会调用；生产 app startup 未调用，且 main.py 不在任务白名单，未越界修改。
3. 批量推理：已存在并复核。
4. rerank 前重复归并：身份归并已存在；本轮新增精确模型输入去重。
5. 输入长度、6 候选数、7 batch、8 线程：没有新鲜正式质量/性能证据，不改正式值。
9. GPU：硬件存在但 CUDA Torch 不可用。
10. ONNX：缺少既有依赖与内存余量。
11. INT8：历史性能仍不达标且质量未证明。
12. release-aware rerank 缓存：未实现，不以 hit 替代 miss 门禁。

## 本轮验证

- 最终定向回归第1次：74 passed。
- 最终定向回归第2次：74 passed。
- 标准库语义探针：单例、eval、inference_mode、8/8/1 批处理、重复文本一次 forward、候选保留均 PASS。
- 代码审查：实现未发现正确性缺陷；审查建议的混合重复映射和 score-count fail-closed 测试已补齐。
- fresh CPU profile：BLOCKED_RESOURCE_GUARD；269.42s 未完成 model_loaded，0 forward，未生成虚假性能数据。

## 正式结论

RETRIEVAL PERFORMANCE NOT PASS。
LIVE ACCEPTANCE NOT EXECUTED。
DO NOT HAND OFF TO CONTROLLER。