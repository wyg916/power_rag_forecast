# Package 3 验收记录

- 状态：PASS
- 工作树：`E:\智能运营分析项目_worktrees\ai_assistant_runtime_hotfix_20260812`
- 分支：`hotfix/ai-assistant-runtime-providers-20260812`
- PRE checkpoint：`E:\智能运营分析项目_worktrees\ai_assistant_runtime_hotfix_20260812\backups\phase3\20260812_161550913_AI_ASSISTANT_HOTFIX_PACKAGE3_PRE`

## 实现

- AI Assistant 独立模型选择器仅包含 `AUTO（推荐）`、`Kimi K2.6`、`MiMo V2.5`、`DeepSeek V4-Flash`。
- 选择结果按会话保存；新建对话重置为 AUTO，历史会话切换时恢复对应选择。
- 回答卡展示后端返回的实际 provider/model；AUTO 降级与显式 provider 不可用采用不同状态标签。
- 业务预测模型与 LLM provider 保持独立；未删除、替换或混用页面顶部的业务预测模型事实。
- 显式 provider 不可用时，后端把实际 provider 标记为 `unavailable`，另行保留 `requested_provider`，避免 UI 假报已调用指定 provider。

## 自动化验证

- `pytest -q tests/test_ai_frontend_display_contract.py`：5 passed。
- `pytest -q tests/test_ai_frontend_display_contract.py tests/test_ai_multi_provider_contract.py tests/test_ai_assistant_runtime_hotfix.py tests/test_ai_assistant_llm_router.py`：23 passed。
- `npm.cmd run build`：TypeScript 与 Vite 构建 PASS，3675 modules transformed。
- `git diff --check`：PASS。

## 浏览器验证

测试实例为当前热修工作树的独立 localhost 服务：backend `8001`，frontend `5174`；未复用或中断已有 `8000/5173` 实例。

| 视口 | selector | horizontal overflow | 截图 |
|---|---:|---:|---|
| 1920x1080 | visible, 178px | 0 | `assistant-1920x1080.png` |
| 1440x900 | visible, 178px | 0 | `assistant-1440x900.png` |
| 1366x768 | visible, 178px | 0 | `assistant-1366x768.png` |
| 1280x800 | visible, 178px | 0 | `assistant-1280x800.png` |

交互 PASS：登录、进入 AI 助手、展开四个 provider 选项、选择 DeepSeek、填写问题、五个回答模式可见、新建会话恢复 AUTO。控制台最终错误数与未处理 Promise 将在 Package 4 的完整浏览器矩阵统一采集并结论化。

## 边界

- 未写入或展示任何 provider API key。
- 未切换 production RAG alias，未激活生产模型，未执行 production cutover，未远程推送。
