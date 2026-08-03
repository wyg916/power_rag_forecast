# 脱敏命令摘要

- 每条命令固定 workdir 到指定性能工作树，并核验分支与起始 HEAD。
- 读取任务白名单内的 reranker、hybrid、Candidate 验收及定向测试实现。
- 运行本机 Torch/CUDA/ONNX/INT8 包与硬件只读探针，不安装依赖。
- 统计当前50题 dynamic top-k 和正式 Candidate 的精确 reranker 输入重复率，不输出文本。
- 通过 Git 补丁应用最小生产与测试差异。
- 使用现有项目 venv 两次运行74项定向回归。
- 运行 fresh CPU profile；资源门禁只停止精确识别的 profile 子进程，0 forward。
- 只读复核 Qdrant TCP 与当前黄金集 human_verified 状态。
- 执行白名单、敏感信息、diff 与 Git 状态扫描。