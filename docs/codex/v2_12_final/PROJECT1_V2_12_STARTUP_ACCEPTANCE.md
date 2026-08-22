# PROJECT1 v2.12.0 Startup Acceptance

## 受控端口与来源

Round 1 使用独立端口 `18084`（backend）与 `15184`（frontend），并启动 `phase4_health` Celery。所有进程的 branch、SHA、PID、creation identity、port、working directory、log path 与 health 均可追溯到唯一 Integration worktree。

既有/来源未知的 `8000`、`5173` 未被终止或复用。

## 验收结果

| 动作 | 结果 |
|---|---|
| cold start | PASS；backend/frontend/celery 均 managed=true |
| second start | PASS；PID 与 creation identity 不变，managed=true |
| status | PASS |
| logs | PASS |
| doctor | PASS |
| restart | PASS；三个进程受控停止后以新 PID 启动 |
| controlled stop | PASS；18084/15184 释放 |
| visible consoles | 0（要求 <=1） |
| source provenance | PASS |

## 修复说明

第二次 start 原先会把同一控制器已拥有的相同进程标记为 unmanaged。`44e048d` 仅在以下条件同时满足时保留 ownership：既有状态属于同一 worktree、此前 `managed=true`、PID 与 creation identity 匹配。未知外部进程不会因此被接管。

新增 3 个运行控制回归测试，相关 targeted suite 共 15 tests PASS。该修复保持对来源不明进程的 fail-closed 策略。

## 证据

- `round1_runtime_cold_start_44e048d.json`
- `round1_runtime_second_start_44e048d.json`
- `round1_runtime_status_second_start_44e048d.json`
- `round1_runtime_doctor_44e048d.json`
- `round1_runtime_logs_44e048d.log`
- `round1_runtime_restart_44e048d.json`
- `round1_runtime_controlled_stop_44e048d.json`
- `round1_runtime_status_after_stop_44e048d.json`
- `round1_runtime_control_fix_tests.xml`

Round 2 将在 `FINAL_PRE_RELEASE_SHA` 上再次执行 cold/second start/status/logs/doctor/restart/controlled stop。
