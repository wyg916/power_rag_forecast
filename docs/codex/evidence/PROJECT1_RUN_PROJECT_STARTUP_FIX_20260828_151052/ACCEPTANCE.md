# run_project.bat 一键启动修复验收

- 结论：`PASS`
- 目标项目：`E:/智能运营分析项目`
- 修复前提交：`f8c8f456b07a4c923ed175247786ef827642bb72`
- 检查点：`backups/phase3/20260828_151052_RUN_PROJECT_STARTUP_FIX_PRE`

## 根因

`scripts/runtime_control.py` 对所有启动模式都固定向 Web 启动器传递 `--no-browser`。因此默认双击虽然能启动服务，却永远不会调用 Windows 默认浏览器；黑色窗口只是启动控制进程的可见表现，页面不出现是浏览器被显式禁止造成的。

## 修复

- 交互启动（默认双击 `run_project.bat`）不再传递 `--no-browser`，Web 健康后自动打开默认浏览器。
- `run_project.ps1 start -Silent` 继续传递 `--no-browser`，保持后台自动化无 UI 副作用。
- Web 启动日志去除过时的硬编码 v2.11.2，实际版本以 branch/SHA 为准。
- README 指向当前 `main` 项目目录和 v2.12.1 正式标签，不再误导用户进入旧 RC 工作树。

## 真实验收

- 默认一键启动两次均成功，第二次幂等复用健康服务。
- Backend `127.0.0.1:8000` healthy，Frontend `127.0.0.1:5173` healthy，Celery worker running。
- Frontend HTTP 200，Backend `/api/health` HTTP 200。
- Windows 可见 Chrome 窗口标题为“售电交易 AI 辅助决策平台 - Google Chrome”。
- 最新控制器日志：`logs/runtime/20260828_153229/controller.log`。
