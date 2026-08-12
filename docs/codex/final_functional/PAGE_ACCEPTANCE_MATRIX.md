# 页面最终验收矩阵

| 页面域 | 正式路由 | URL/刷新/直接访问 | 主要功能 | Empty/Error/权限 | 四视口 | 结论 |
|---|---:|---|---|---|---|---|
| 首页 / 驾驶舱 | 1 | PASS | KPI、趋势、风险、预测、策略、任务、刷新、跳转 | PASS | PASS | PASS |
| 数据中心 | 2 | PASS | 目录、检索、过滤、分页、字段、质量、同步、预览、CSV 导出 | PASS | PASS | PASS |
| 预测中心 | 3 | PASS | 24h、历史、模型信息、特征版本、小时详情、图表、刷新 | PASS | PASS | PASS |
| 策略中心 | 3 | PASS | 高价窗口、储能、复核、SOC、记录、建议、导出、详情 | PASS | PASS | PASS |
| AI 助手 | 4 | PASS | 五模式、发送、Loading、复制、导出、多轮、Provider、工具 | PASS | PASS | PASS |
| 报告中心 | 4 | PASS | 列表、生成、预览、详情、下载、审核、发布、筛选、搜索 | PASS | PASS | PASS |
| 模型中心 | 4 | PASS | Active/Candidate/异常/回滚、详情、指标、比较、历史、权限 | PASS | PASS | PASS |
| 知识库 / RAG | 4 | PASS | 文档、详情、检索、Chunk、Citation、问答、ACL、拒答 | PASS | PASS | PASS |
| 任务中心 | 4 | PASS | 列表、状态、日志、过滤、详情、重试、取消、健康、分页 | PASS | PASS | PASS |
| 系统设置 | 3 | PASS | 配置、Provider、健康、保存、连接测试、用户与权限 | PASS | PASS | PASS |

## 路由终验

- 32/32 正式业务路由完成最新代码复跑。
- `horizontal overflow = 0`，业务禁词命中 0，页面错误态误报 0。
- 任务中心 4 个路由首次扫表捕获正常短暂 Loading；稳定等待后二次核验全部收敛为 0，无无限 Spinner。
- 四视口对 32 条正式路由共完成 128 个页面组合：1920×1080、1440×900、1366×768、1280×800，全部无横向溢出、禁词或页面错误。

证据：`browser_release_final_routes.json`、`browser_release_final_task_stability.json`、`browser_four_viewports_final.json`、`browser_release_final_screenshots.json`。

