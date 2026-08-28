# 测试摘要

| 检查 | 结果 |
|---|---|
| `npm run typecheck` | PASS |
| `npm run build` | PASS；3,690 modules |
| `pytest tests/test_p6_report_center_viewport_layout.py tests/test_phase5_c_report_generation.py` | 13 passed，2 skipped（缺少隔离数据库 URL） |
| `node --test tests/reportCenterPresentation.test.mjs` | 4/4 PASS（包含在全量 unit 中） |
| `npm run unit` | 56/57；唯一失败为主项目既有 10px 全局样式门禁，未修改 main 同样失败 |
| 扩大 pytest | 71 passed，2 skipped，3 个非报告失败；未修改 main 同项复现 |
| 浏览器两页只读冒烟 | PASS；真实数据加载、报告切换、可见入口、控制台均通过 |

未执行写操作型浏览器冒烟，避免更改正式报告审核/发布状态。
