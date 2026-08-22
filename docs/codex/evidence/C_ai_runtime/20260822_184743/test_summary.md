# Test summary

| 验证 | 结果 |
|---|---|
| 最终合并 AI/附件/权限/ChatBI/RC 门禁 | 165 passed / 5 isolated-only skipped |
| CI 最小 AI/附件/ChatBI 契约 | 85 passed / 5 isolated-only skipped |
| Provider/权限/附件受影响回归 | 90 passed |
| Endpoint/附件/Provider 定向 | 46 passed |
| RC launcher + 附件 | 32 passed |
| 权限矩阵可重复生成 | PASS，207 method-path / 191 unique path |
| compileall / diff check | PASS |
| Alembic | 唯一 head `0022_chatbi_semantic_v1` |
| 独立端口 start/status/stop | PASS，退出码均 0，最终 18000/15173/Celery 无残留 |
| 全量普通 pytest | 1010 passed / 20 skipped；29 failed + 21 errors 后到达 maxfail=50，于 91% 停止 |

全量失败分类：普通 pytest 数据库守卫主动清空数据库连接、显式 isolated-only integration、缺失且不归 C 所有的模型二进制资产。任务相关门禁在定向套件中无失败。
