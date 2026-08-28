# 未解决项

- 本次一键启动与自动打开页面范围无阻塞项。
- `tests/test_startup_scripts.py` 的既有 `run_celery_health.bat` LF/CRLF 失败仍保留；它在修复前已经存在，且与当前 `run_project.bat` 浏览器策略无关。
- 启动时短暂显示的主控制台用于输出分支、SHA、日志路径和失败码；Backend、Frontend、Celery 子进程继续使用无窗口模式。
