# Day 2 已知问题与限制

以下均已如实记录，不影响本次“全新环境复现、迁移回放与配置闭环”结论：

1. `npm audit` 报告 4 个依赖漏洞：2 high、2 moderate、0 critical。未擅自执行可能改变依赖树或引入破坏性升级的 `npm audit fix`。
2. 全新 Python 环境在升级 pip 后出现一次 `Ignoring invalid distribution ~ip` 警告；`requirements.txt` 安装成功，`pip check` 为 `No broken requirements found`，核心导入和后端启动均通过。
3. 0015 的既有非破坏性 downgrade 会在临时 Schema 的 `roles` 表保留 `reviewer` 行；0015/0016 的结构对象均已正确撤销，随后整个临时 Schema 已清理，不影响 `public`。
4. 完整 Compose 未启动：本机 `8080`、`18000` 已被其他项目占用，为避免干扰，仅完成主版/企业版示例环境的 `config --quiet` 解析。后端与前端改用 `18080`、`15173` 独立冒烟。
5. 未启动 Celery Worker；健康接口如实返回 `worker_count=0`、`active_workers=[]`，Redis 可连接。数据库快照中的历史 worker 名称不等于当前活动 worker。
6. 未配置外部 LLM/RAG：RAG 健康状态为 `disabled`，DeepSeek 报 `missing_api_key`，Ollama 报无可用本地模型；未自动下载、未外部调用、未正式导入知识。
7. Word 原方案 Day 2 文本已完整提取核验；本机缺少 LibreOffice/soffice，无法完成 Word 页面渲染级视觉 QA。未修改该文档。
8. 外部验证目录保留了随机临时 `.env`、全新 `.venv`、`node_modules`、`dist`、缓存和原始日志用于审计；全部位于 E 盘、未进入 Git。早期两次被中断的前端安装 clone 也保留，未做批量删除。

未进入 Day 3，也未实施后续权限、数据真实性、预测、报告、任务状态机、RAG 正式导入或 UI 优化。
