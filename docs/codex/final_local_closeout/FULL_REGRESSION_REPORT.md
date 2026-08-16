# 全站联合回归报告

## 结果摘要

| 门禁 | 结果 |
|---|---|
| Alembic | 唯一 Head `0022_chatbi_semantic_v1`；public current/幂等 upgrade/current PASS |
| 后端权威全量 | 1153 collected；1119 passed，34 skipped，0 failed，0 errors，129.08s |
| 公共数据库保护 | public_match=true；临时 Schema/role 残留 0 |
| AI grounding 定向 | 25/25 |
| 失败闭环与当前契约 | 54/54 |
| 前端专项/路由/组件契约 | 230/230 |
| TypeScript | `npx tsc --noEmit` PASS |
| lint | NOT_CONFIGURED（package.json 无 lint script） |
| JS 单元测试 | NOT_CONFIGURED（package.json 无 test script） |
| Vite 正式构建 | PASS；3675 modules；37.65s |
| 浏览器正式路由 | 32/32 |
| 最终关键请求 | 30 requests；4xx=0；5xx=0 |
| Console/Page/Request failed | 0/0/0 |

34 个 skip 都有显式环境原因：RAG 排名需要在线知识库、Memory/报告/策略/T003 需要专用隔离夹具或真实推理批次；未把 skip 伪报为通过。

## 诊断与权威口径

直接裸跑系统 Python 曾因解释器、共享模型二进制和数据库隔离缺失产生历史环境失败，不作为权威结果。最终权威命令使用项目 venv、`POWER_TRADING_ASSET_ROOT=E:\智能运营分析项目` 和 Day3 临时 Schema guard；证据为：

- `tests/backend_full_final_tree_authoritative_junit.xml`
- `tests/backend_full_final_tree_authoritative_guard.json`

浏览器期间曾发现 `kb_releases` ACL 漂移导致知识库 503；按代码受控 ACL manifest 幂等应用后，四个知识库路由全部恢复，最终网络窗口 4xx/5xx 均为 0。
