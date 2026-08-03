# 两条 RAG-R1 分支对账

- merge-base：`7e8284f3b3ed7c748482066552da33857e2915b8`。
- final-integration 独有 51 个提交；integration 独有 52 个提交。
- 普通三方预演产生 42 个内容冲突；`-X ours` 虽可自动决议，但会带入 113 文件、约 9 万行平行实现与历史证据，违反最小变更原则。
- 权威代码树选择 `beta10d/rag-r1-final-integration@1c8c2b195c01a18eb69715fa3017c0f5015498ce`：它包含最终发布 worker/API、候选检索和 AI 验收器、受治理 UI、最终回归门禁。
- `beta10d/rag-r1-integration@1de4036247b38e5e688c846f25ac1836f6c2a5e5` 作为第二父提交纳入历史，保留过程证据和凭据阻断事实，不重新叠加被替代的平行实现。
- 双父 merge 后 tree 必须精确等于 final-integration tree；任何偏差均不得作为并行基线。

