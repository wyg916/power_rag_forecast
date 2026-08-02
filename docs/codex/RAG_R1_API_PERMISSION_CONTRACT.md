# RAG-R1 API、权限与状态契约

## 1. 不可变原则

- `tenant_id` 仅从认证上下文取得，客户端提供同名字段时拒绝请求。
- 所有读写、缓存、Release、Citation 和审计事实必须携带 `tenant_id`、`release_id`、`run_id` 或 `trace_id` 中适用的标识。
- GET 与只读搜索不得 seed、同步、激活、记录运行或产生其他写副作用。
- Candidate 只能经 `knowledge:publish` 权限和显式发布动作晋升；后台任务不得自动 Published。
- PostgreSQL current release、Qdrant alias、Collection payload 和 Embedding profile 不一致时，搜索及回答返回 unavailable。

## 2. 权限

| 权限 | 能力 | 默认角色 |
|---|---|---|
| `knowledge:read` | 读取已发布文档、搜索和普通健康状态 | Admin、Reviewer、Analyst |
| `knowledge:write` | 创建 Draft ingestion、重试解析、隔离 Draft | Admin、Reviewer |
| `knowledge:publish` | 创建/校验 Candidate、发布和回滚 | Admin、Reviewer |
| `knowledge:diagnose` | 技术健康、评测详情和受控 Trace | Admin、Developer |

普通用户不得获得技术模型路径、Provider、维度、Collection、原始 Trace、密钥或系统路径。

## 3. 接口矩阵

| 方法与路径 | 权限 | 写副作用 | 成功契约 |
|---|---|---:|---|
| `POST /api/knowledge/upload` | `knowledge:write` | 创建 Draft | `202`，返回 `ingestion_id` |
| `GET /api/knowledge/ingestions/{id}` | `knowledge:write` | 无 | 解析、OCR、Embedding、隔离状态 |
| `GET /api/knowledge/releases` | `knowledge:read` | 无 | Release 列表 |
| `POST /api/knowledge/releases` | `knowledge:publish` | 创建 Candidate | Candidate 标识与门禁状态 |
| `POST /api/knowledge/releases/{id}/validate` | `knowledge:publish` | 记录验证事实 | 门禁结果 |
| `POST /api/knowledge/releases/{id}/publish` | `knowledge:publish` | 两阶段发布 | Published 或原子回滚 |
| `POST /api/knowledge/releases/{id}/rollback` | `knowledge:publish` | 原子回滚 | RolledBack |
| `GET /api/knowledge/search` | `knowledge:read` | 无 | 已发布证据或 unavailable |
| `POST /api/knowledge/search` | `knowledge:read` | 可记录检索运行 | 已发布证据或 unavailable |
| `GET /api/knowledge/health` | `knowledge:read` | 无 | 公共组件可用性 |
| `GET /api/knowledge/health/diagnostics` | `knowledge:diagnose` | 无 | 脱敏技术诊断 |

## 4. 状态机

Ingestion：

`draft → parsing → validating → ready`

任一步骤失败进入 `quarantined` 或 `corrupt`；重新解析产生新运行事实，不覆盖不可变版本。

Release：

`candidate → validated → published → superseded`

发布失败保持或回到 `candidate`；显式回滚后为 `rolled_back`。任何状态跳跃均拒绝。

## 5. Citation 与 AI 响应

Citation 必须包含：

- `document_id`、`version_id`、`chunk_id`
- `page`、`section_path`、`char_start`、`char_end`
- `bbox`、`asset_id`
- `quote`、`content_hash`
- `release_id`

AI 响应固定为：

- `answer`
- `claims`
- `citations`
- `grounding_status`
- `refusal_reason`
- `release_id`
- `trace_id`
- `degraded_components`

每个 Claim 必须引用至少一个通过版本、权限、定位和内容哈希复核的 Citation。关键 Claim 无证据时整体拒答；普通无支撑 Claim 必须删除。

## 6. 公共页面字段

普通用户只显示文档标题、版本、页码、章节、更新时间、处理/发布状态和可用性。禁止显示 raw `data_origin`、`data_source`、`source_type`、`is_simulated`、模型路径、Collection 或原始工具 Trace。
