# RC 集成清单

## 目标

- 分支：`release/beta10d-agent-rc-20260807`
- 工作树：`E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807`
- 基线：Day 8 `bc36715d6943c212197d2e3dce5d8f2c6949bd08`

## 白名单集成

| 顺序 | 来源 | 处置 | RC 结果 |
|---|---|---|---|
| 1 | `d5376bf899028b2353b73c84dfac2b25b3e6c7f9` | 从共同祖先快进，保留 Day7A、Day8、RAG-R1 与证据闭环 | tree 与来源一致 |
| 2 | `63fc9fc` | `cherry-pick -x`，接入 R3 检索性能契约 | `9ff8caebe68f47e9481fa512b7c660af8691fc98` |
| 3 | `ef5217b58bb8c888d4f6e2c724775d065c0cd9e8` | `cherry-pick -x`，接入性能修复 | `0f6f1841e64b6f4bd83e01d57584c901254c3302` |

## 去重与冲突处置

- `4a514d34113ee06a5725fa3f23bcf28298374040` 与证据线已含的 `c622754bc2e42e1d488bce9d86c88b8c0084ea32` 经 `git cherry` 证实补丁等价，跳过重复合入。
- 未整分支合并存在服务与测试文件的冲突风险，因此按白名单提交定向集成。
- R3 的逐问题 `_embedding` 性能计时与 AI 验收原有批量 `_embeddings` 故障注入/缓存契约冲突；保留逐问题路径，同时恢复批量兼容 seam，并新增回归测试。
- 启动器旧逻辑会隐式同步、强制重启和联网安装依赖；改为 `--skip-sync`、复用健康服务、缺依赖失败关闭。

## 当前门禁

- 静态单 head：`0018_rag_enterprise_r1`。
- Python 目标回归：87 passed。
- 前端生产构建：PASS。
- 一键启动与组合健康：PASS。
- 数据库快照：只读，写入 0。
- 生产、模型、RAG 发布：均未授权。
