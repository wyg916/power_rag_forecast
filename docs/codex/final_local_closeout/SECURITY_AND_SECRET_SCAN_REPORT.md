# 安全与敏感信息检查报告

状态：`SECRET_SCAN=PASS`。

已完成：

- 应用数据库身份 `beta10d_app_login`、安全身份 `beta10d_security_login` 均保持最小权限；
- Alembic 仅使用本机迁移身份，应用启动不依赖超级管理员；
- Qdrant 运行时不加载 admin key，只读 Key 与 TLS/strict mode 校验通过；
- 浏览器临时管理员 `project1_closeout_admin_20260816` 精确删除，users 与 user_roles 残留均为 0；
- 临时凭据文件和清理脚本均已精确删除；
- 报告、终端摘要与提交信息不记录密码、Token、API Key、私钥或完整 DSN。

最终文档提交前已对起始 SHA 至当前 HEAD 的变更、工作区新增/修改文件及本轮证据目录中的文本型日志、JSON、XML、CSV 和报告执行脱敏模式扫描：共扫描 65 个文件，高置信真实凭据命中 0，私钥/GitHub Token/OpenAI Key/AWS Key 命中均为 0，超过 10 MiB 的新增文件为 0。

扫描器另报告 46 个 `credentialed_dsn` 形态；逐组只读分类后，全部来自既有自动化测试夹具，主机仅为 `localhost`、`127.0.0.1`、`db.example`、`remote`、`host` 或 `invalid`，口令均为显式测试字面量或单字符占位，不属于运行凭据。机器可读摘要见 `docs/codex/evidence/PROJECT1_LOCAL_FINAL_CLOSEOUT_20260816/security/secret_scan_summary.json`。
