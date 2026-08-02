# RAG-R1 AI Claim/Citation pre-write checkpoint

- 时间：2026-08-02 23:31（Asia/Shanghai）。
- branch：`beta10d/rag-r1-integration`。
- HEAD：`1c944feb9a85ebabf0c66ff5cf8d0d0f64a88743`。
- Git 状态：clean；无已跟踪修改，无未跟踪文件。
- 数据库/Qdrant 影响：本任务预检为只读；计划不发布 Candidate、不切 alias、不写数据库或 Qdrant。
- 当前缺口：现有 Citation 与 Claim 绑定校验器尚未进入公开 AI 契约；`rag-answer` 与主 Chat 尚未传递服务端企业检索上下文。
- 安全边界：知识型回答必须由已验证 Citation 构造 Claims；无证据拒答。数值型经营问题继续使用受控业务工具，不允许 RAG 替代 SQL/预测事实源。

## 关键文件 SHA-256

- `backend/app/api/v1/endpoints/assistant.py`：`86B42CB4EC650A3DE17610ECF04CAB12D299DE24FA82CD4520FE729F73BB36EB`
- `backend/app/platform_services.py`：`777F89106E180CC47DD34A5D2A0BDDFAE0513316150EF1195888B16B48212BDA`
- `backend/app/ai/assistant_service.py`：`17AA7CCFDFD3A86964FAF1FF0BD2111B9190C7CA4773B9CC1BC12DB2D1D2AFB9`
- `backend/app/ai_assistant/service.py`：`3F52C4647A256700DECF59E86C3C9EE8CA9B4A35987D983DAA96CF3B995E4645`
- `backend/app/ai_assistant/core/trace_manager.py`：`6F92D33DD3123173ED2D601E1DD916E7EE1C6AD11CA9EF391354C6319466398D`
- `backend/app/services/rag_grounding_service.py`：`8FD8320EC16CD9E3016261769197EB5187AB7B17827382AF012FBCB0CFF0DEC9`

## 回滚

- 对本任务原子提交执行 `git revert <commit>`。
- 本任务计划持久化业务写入为 0，无数据库或 Qdrant 恢复动作。
