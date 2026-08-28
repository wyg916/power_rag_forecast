# 测试摘要

| 验证 | 结果 |
|---|---|
| `run_project.bat doctor` | PASS；Git 根、Python、运行配置、前端依赖、唯一 Alembic head 全部 PASS |
| `tests/test_runtime_control.py` | PASS；4/4 |
| 启动控制 + RC 契约 + 脚本专项 | PASS；18 passed / 1 deselected |
| Python 语法 | PASS；`runtime_control.py`、`web_platform_launcher.py` |
| 默认一键启动 | PASS；Backend/Frontend/Celery healthy/running |
| 二次一键启动 | PASS；健康服务幂等复用 |
| HTTP | PASS；Frontend 200、Backend health 200 |
| 浏览器 | PASS；Chrome 可见窗口标题为“售电交易 AI 辅助决策平台” |

修复前全量 `tests/test_startup_scripts.py` 已存在 1 项 `run_celery_health.bat` LF/CRLF 门槛失败；该文件不在本任务变更范围，相关启动器专项已单独通过。
