# C 全量诊断失败归因矩阵

## 结论

- 复现基线：`94602989f97168de9662efbbd721bac07f014b2c`，任务修改前、指定 C 工作树为 CLEAN。
- 命令：`E:\智能运营分析项目\.venv\Scripts\python.exe -m pytest -q --disable-warnings --maxfail=50`。
- 新鲜结果：`1010 passed / 20 skipped / 29 failed / 21 errors`，耗时 `433.74s`，在 91% 处达到 50 项上限。
- `C_INTRODUCED_REGRESSION=0`：下列 50 项全部在本任务开始、任何代码修改之前已复现；未删除测试、未扩大 skip、未修改失败用例所属业务实现来掩盖失败。
- 本任务修改后的 C 定向门禁通过；其中 6 项旧 AI 用例再次定向复现，失败仍由标准 pytest 的数据库 fail-closed 模式造成，不是本任务新增回归。

## 原因代码

| 代码 | 失败原因 | 处理边界 |
|---|---|---|
| `DB-GUARD` | 标准 pytest 启动时 `scripts/day3_test_database_guard.py` 按设计清空 `DATABASE_URL/SECURITY_DATABASE_URL/MIGRATION_DATABASE_URL`；依赖业务事实或持久会话的用例得到 `engine=None`、503、空 evidence 或无持久上下文。 | 仅可用受限临时 Schema/角色运行器复验；禁止连接 public 直接补跑或伪造成功数据。 |
| `ISOLATED-RUNNER` | Phase5 A2 fixture 明确要求 `BETA10D_TEST_ISOLATION_ACTIVE=1`，普通 pytest 必然在 setup fail。 | Integration 使用 `scripts/day3_test_database_guard.py` 创建/销毁隔离 Schema 后运行。 |
| `MODEL-ASSET` | 冻结模型目录缺少 `base_model.joblib`、`peak_model.joblib`、`spike_classifier.joblib`，module fixture 在反序列化前 fail-closed。 | A/模型所有者提供经 hash/manifest 准入的资产；C 禁止修改 `model_ops/` 或伪造二进制。 |

复现列中的节点统一使用：`E:\智能运营分析项目\.venv\Scripts\python.exe -m pytest -q <节点>`。需要数据库的 Integration 命令必须再包裹 `scripts/day3_test_database_guard.py --evidence <path> -- <命令>`。

## 逐项矩阵

| # | 测试节点 | 失败原因 | 代码回归 | 环境依赖 | 模块 / Owner | Integration 动作 |
|---:|---|---|---|---|---|---|
| 1 | `tests/test_ai_assistant.py::test_ai_assistant_forecast_extreme_is_question_specific` | `DB-GUARD`：预测事实不可读，evidence 为空。 | 否 | 是 | AI 工具事实 / Final Integration 隔离 DB | 在受限 Schema 注入受控 24h fixture 后复验。 |
| 2 | `tests/test_ai_assistant.py::test_ai_assistant_hour_explain_uses_hour_tool` | `DB-GUARD`：工具无预测事实，答案正确 fail-closed，缺少 18:00 事实。 | 否 | 是 | AI 工具事实 / Final Integration 隔离 DB | 同上，验证工具事实而非固定回答。 |
| 3 | `tests/test_ai_assistant.py::test_ai_assistant_core_intents` | `DB-GUARD`：意图正确但多个事实工具 evidence 为空。 | 否 | 是 | AI 工具事实 / Final Integration 隔离 DB | 受限 Schema 下复验全部核心意图事实。 |
| 4 | `tests/test_ai_assistant_accuracy.py::test_weather_data_latest_time_answer` | `DB-GUARD`：天气 freshness 查询无连接。 | 否 | 是 | AI 数据新鲜度 / Final Integration 隔离 DB | 受控天气 fixture 下复验。 |
| 5 | `tests/test_ai_assistant_accuracy.py::test_storage_discharge_has_multiple_windows` | `DB-GUARD`：预测曲线不可读，输出为显式不可用而非推荐窗口。 | 否 | 是 | AI 储能工具 / Final Integration 隔离 DB | 受控预测 fixture 下复验。 |
| 6 | `tests/test_ai_assistant_accuracy.py::test_followup_reason_uses_previous_low_price_context` | `DB-GUARD`：首轮事实/持久会话不可用，后续上下文未建立。 | 否 | 是 | AI 会话 / Final Integration 隔离 DB | 同一隔离 Schema 下连续两轮复验。 |
| 7 | `tests/test_data_trust_service.py::test_controlled_ai_business_query_uses_registered_dataset_and_public_fields` | `DB-GUARD`：受控 Dataset 查询无 engine。 | 否 | 是 | 数据信任 / Data Security + Integration | 隔离数据集 fixture 下复验白名单查询。 |
| 8 | `tests/test_data_trust_service.py::test_ai_catalog_empty_dataset_and_readiness_use_dataset_contract` | `DB-GUARD`：catalog readiness 依赖数据库元数据。 | 否 | 是 | 数据信任 / Data Security + Integration | 隔离 Schema 迁移后复验。 |
| 9 | `tests/test_data_trust_service.py::test_ai_chat_business_data_query_uses_controlled_tool` | `DB-GUARD`：受控业务查询工具无数据库。 | 否 | 是 | 数据信任 / Data Security + Integration | 隔离 fixture 下验证受控工具链。 |
| 10 | `tests/test_day3_database_isolation.py::test_active_pytest_database_is_restricted_and_not_public` | `DB-GUARD`：普通 pytest 故意处于 disabled-no-database，而测试要求临时受限角色。 | 否 | 是 | DB 隔离 / Final Integration | 只从 Day3 隔离运行器启动。 |
| 11 | `tests/test_day3_database_isolation.py::test_restricted_role_cannot_write_public` | `DB-GUARD`：缺少临时受限角色上下文。 | 否 | 是 | DB 隔离 / Final Integration | 运行器创建 NOLOGIN 角色并复验 public 写拒绝。 |
| 12 | `tests/test_day4_data_access_security.py::test_unregistered_dataset_and_field_fail_closed` | `DB-GUARD`：安全查询服务在无数据库模式拒绝。 | 否 | 是 | 数据访问安全 / Data Security + Integration | 隔离 Schema 下复验未注册对象拒绝。 |
| 13 | `tests/test_day4_data_access_security.py::test_injection_text_is_bound_as_data_not_executed` | `DB-GUARD`：参数绑定测试无受限数据库会话。 | 否 | 是 | 数据访问安全 / Data Security + Integration | 隔离 Schema 下复验绑定参数和表完整性。 |
| 14 | `tests/test_p6_p1_1a_data_center.py::test_database_target_is_the_authorized_local_postgres_and_not_superuser` | `DB-GUARD`：标准 pytest 的 URL 为空，无法断言隔离身份。 | 否 | 是 | 数据中心后端 / A + Final Integration | 隔离运行器验证 localhost/postgres/受限角色。 |
| 15 | `tests/test_p6_p1_1a_data_center.py::test_quality_and_sync_reads_do_not_write_protected_tables` | `DB-GUARD`：无法取得 protected counts。 | 否 | 是 | 数据中心后端 / A + Final Integration | 隔离 fixture 前后做只读指纹比对。 |
| 16 | `tests/test_p6_p1_1a_data_center.py::test_quality_report_uses_registered_dataset_contract` | `DB-GUARD`：质量报告查询无数据库。 | 否 | 是 | 数据中心后端 / A + Final Integration | 隔离 Dataset Registry 事实下复验。 |
| 17 | `tests/test_p6_p1_1a_data_center.py::test_data_center_read_api_has_dataset_meta_pagination_and_permission` | `DB-GUARD`：读取 API 返回 503。 | 否 | 是 | 数据中心后端 / A + Final Integration | 隔离 Schema 下复验分页与权限。 |
| 18 | `tests/test_p6_p1_1b_data_catalog.py::test_registered_dataset_reads_and_export_remain_read_only` | `DB-GUARD`：数据集读/导出无 engine。 | 否 | 是 | 数据目录后端 / A + Final Integration | 隔离 Schema 前后指纹复验。 |
| 19 | `tests/test_p6_p1_1b_data_catalog.py::test_table_and_view_are_addressed_only_by_dataset_id` | `DB-GUARD`：受控对象解析无数据库。 | 否 | 是 | 数据目录后端 / A + Final Integration | 隔离 Registry 下复验 dataset_id-only。 |
| 20 | `tests/test_p6_p1_1b_data_catalog.py::test_search_is_parameterized_and_unregistered_objects_fail_closed` | `DB-GUARD`：参数化查询无受限会话。 | 否 | 是 | 数据目录后端 / A + Final Integration | 隔离 Schema 下复验注入文本。 |
| 21 | `tests/test_p6_p1_1b_data_catalog.py::test_dataset_rows_api_has_permission_and_canonical_pagination` | `DB-GUARD`：合法读取返回 503。 | 否 | 是 | 数据目录后端 / A + Final Integration | 隔离 fixture 下复验 200/403 与分页。 |
| 22 | `tests/test_p6_p1_1b_data_catalog.py::test_export_is_authenticated_memory_csv_and_does_not_create_temp_file` | `DB-GUARD`：内存 CSV 导出前的数据读取返回 503。 | 否 | 是 | 数据目录后端 / A + Final Integration | 隔离 fixture 下复验导出且无临时文件。 |
| 23 | `tests/test_p6_p1_2a_forecast_layout.py::test_forecast_24h_uses_real_stale_run_without_read_side_effects` | `DB-GUARD`：protected counts 的 engine=None。 | 否 | 是 | Forecast 事实 / A | 使用隔离 24h fixture，验证无读副作用。 |
| 24 | `tests/test_p6_p1_2b_forecast_facts.py::test_forecast_fact_endpoints_remain_read_only_and_traceable` | `DB-GUARD`：forecast facts 无数据库。 | 否 | 是 | Forecast 事实 / A | 隔离 run_id 事实下复验。 |
| 25 | `tests/test_p6_p1_2b_forecast_facts.py::test_previous_batch_is_not_replaced_by_history_mean` | `DB-GUARD`：runs 为空而非 1 条受控批次。 | 否 | 是 | Forecast 事实 / A | 隔离 fixture 写入单一 run 后复验。 |
| 26 | `tests/test_p6_p1_3a_strategy_layout.py::test_strategy_get_chain_has_no_strategy_or_audit_write_side_effects` | `DB-GUARD`：策略只读指纹无法建立。 | 否 | 是 | Strategy 事实 / A | 隔离 Schema 下复验 GET 前后写计数。 |
| 27 | `tests/test_p6_p1_3c_strategy_runtime.py::test_unique_database_target_and_migration_head` | `DB-GUARD`：空 URL 无法解析。 | 否 | 是 | Strategy runtime / A + Final Integration | 由隔离运行器注入唯一 head/目标。 |
| 28 | `tests/test_p6_p1_3c_strategy_runtime.py::test_controlled_seed_is_idempotent_and_traceable` | `DB-GUARD`：seed 前数据库身份门禁失败。 | 否 | 是 | Strategy runtime / A | 仅在一次性隔离 Schema 执行受控 seed。 |
| 29 | `tests/test_p6_p1_3c_strategy_runtime.py::test_runtime_read_chain_has_no_write_side_effect` | `DB-GUARD`：create_app_engine 因空 URL fail-closed。 | 否 | 是 | Strategy runtime / A | 隔离 fixture 下做前后表指纹。 |
| 30 | `tests/test_phase5_a2_integration.py::test_a2_1_database_metadata_and_pending_embeddings` | `ISOLATED-RUNNER`：module fixture 主动 fail。 | 否 | 是 | RAG A2 / Final Integration + RAG | Day3 隔离运行器单独运行 Phase5 A2。 |
| 31 | `tests/test_phase5_a2_integration.py::test_a2_1_no_active_content_duplicates_and_stable_order` | `ISOLATED-RUNNER`：module fixture 主动 fail。 | 否 | 是 | RAG A2 / Final Integration + RAG | 同上。 |
| 32 | `tests/test_phase5_a2_integration.py::test_a2_1_explicit_import_failure_rolls_back_without_half_product` | `ISOLATED-RUNNER`：module fixture 主动 fail。 | 否 | 是 | RAG A2 / Final Integration + RAG | 同上，并保留回滚指纹。 |
| 33 | `tests/test_phase5_a2_integration.py::test_a2_1_content_change_supersedes_old_version_without_delete` | `ISOLATED-RUNNER`：module fixture 主动 fail。 | 否 | 是 | RAG A2 / Final Integration + RAG | 同上。 |
| 34 | `tests/test_phase5_a2_integration.py::test_a2_1_get_and_search_100_times_have_no_database_side_effects` | `ISOLATED-RUNNER`：module fixture 主动 fail。 | 否 | 是 | RAG A2 / Final Integration + RAG | 同上，检查 100 次前后指纹。 |
| 35 | `tests/test_phase5_a2_integration.py::test_a2_2_all_active_chunks_have_stable_finite_embeddings` | `ISOLATED-RUNNER`：module fixture 主动 fail。 | 否 | 是 | RAG A2 / Final Integration + RAG | 同上。 |
| 36 | `tests/test_phase5_a2_integration.py::test_a2_2_persisted_vector_index_returns_real_filtered_chunks` | `ISOLATED-RUNNER`：module fixture 主动 fail。 | 否 | 是 | RAG A2 / Final Integration + RAG | 同上，并使用冻结预生产 RAG profile。 |
| 37 | `tests/test_phase5_a2_integration.py::test_a2_2_vector_index_fail_closed_for_missing_index_and_wrong_dimension` | `ISOLATED-RUNNER`：module fixture 主动 fail。 | 否 | 是 | RAG A2 / Final Integration + RAG | 同上，保持错误关闭。 |
| 38 | `tests/test_t002_safe_model_contract.py::test_artifact_manifest_identity_and_hashes_are_complete` | `MODEL-ASSET`：fixture 构建 manifest 前发现 3 个模型文件缺失。 | 否 | 是 | 模型安全 / A | 提供准入资产与 hash；不得在 C 分支补伪文件。 |
| 39 | `tests/test_t002_safe_model_contract.py::test_safe_load_rejects_incompatible_sklearn_before_deserialization` | `MODEL-ASSET`：同一 module fixture 失败，尚未进入目标断言。 | 否 | 是 | 模型安全 / A | 同上，隔离且只读地复验。 |
| 40 | `tests/test_t002_safe_model_contract.py::test_manifest_rejects_unauthorized_artifact_path` | `MODEL-ASSET`：同一 module fixture 失败。 | 否 | 是 | 模型安全 / A | 同上。 |
| 41 | `tests/test_t002_safe_model_contract.py::test_manifest_rejects_simulated_artifact_hash_tamper` | `MODEL-ASSET`：同一 module fixture 失败。 | 否 | 是 | 模型安全 / A | 同上。 |
| 42 | `tests/test_t002_safe_model_contract.py::test_contract_rejects_missing_feature` | `MODEL-ASSET`：同一 module fixture 失败。 | 否 | 是 | 模型安全 / A | 同上。 |
| 43 | `tests/test_t002_safe_model_contract.py::test_contract_rejects_extra_feature` | `MODEL-ASSET`：同一 module fixture 失败。 | 否 | 是 | 模型安全 / A | 同上。 |
| 44 | `tests/test_t002_safe_model_contract.py::test_contract_rejects_reordered_features` | `MODEL-ASSET`：同一 module fixture 失败。 | 否 | 是 | 模型安全 / A | 同上。 |
| 45 | `tests/test_t002_safe_model_contract.py::test_contract_rejects_dtype_mismatch` | `MODEL-ASSET`：同一 module fixture 失败。 | 否 | 是 | 模型安全 / A | 同上。 |
| 46 | `tests/test_t002_safe_model_contract.py::test_contract_rejects_illegal_string` | `MODEL-ASSET`：同一 module fixture 失败。 | 否 | 是 | 模型安全 / A | 同上。 |
| 47 | `tests/test_t002_safe_model_contract.py::test_contract_rejects_nan` | `MODEL-ASSET`：同一 module fixture 失败。 | 否 | 是 | 模型安全 / A | 同上。 |
| 48 | `tests/test_t002_safe_model_contract.py::test_contract_rejects_inf` | `MODEL-ASSET`：同一 module fixture 失败。 | 否 | 是 | 模型安全 / A | 同上。 |
| 49 | `tests/test_t002_safe_model_contract.py::test_contract_rejects_missing_timezone` | `MODEL-ASSET`：同一 module fixture 失败。 | 否 | 是 | 模型安全 / A | 同上。 |
| 50 | `tests/test_t002_safe_model_contract.py::test_contract_rejects_wrong_timezone` | `MODEL-ASSET`：同一 module fixture 失败。 | 否 | 是 | 模型安全 / A | 同上。 |

## Integration 阶段动作

1. 使用 `scripts/day3_test_database_guard.py` 创建唯一临时 Schema 和 NOLOGIN 受限角色，先运行 1–37；验证 public 指纹不变且临时对象清理为 0 残留。
2. 由 A/模型所有者提供通过 manifest/hash 准入的冻结模型资产后，在不联网、只读模型挂载条件下运行 38–50；C 不接触模型二进制。
3. Integration 以同一最终 SHA 重跑普通全量与隔离全量。普通全量继续保留 fail-closed 数据库守卫；不得删除测试或无条件 skip。
