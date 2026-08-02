# RAG-R1 Qdrant 1.18.2 运行时验收

- 结果：`PASS_WITH_RISK`；功能与安全门禁通过，E 盘 NTFS bind mount 告警保留。
- 镜像：`qdrant/qdrant:v1.18.2`。
- Repo digest：`sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c`。
- Image ID：`sha256:e13294053db80229932ca53f6ace97c3da1ae2581b770373e187a15707244eb5`；平台 `linux/amd64`。
- 端点：`https://127.0.0.1:6333`；仅 loopback 映射；6334 未映射到主机。
- TLS：启用；CA/服务端证书已生成并记录哈希；私钥仅在 Git 外 E 盘目录。
- Key：Admin 与 Read-only 独立生成，值未进入输出或 Git。
- strict mode：探针 Collection 实测为 `enabled=true`。
- 角色：无 Key 读取拒绝；Read-only Key 可读、建 Collection/写 Point 均拒绝；Admin Key 可控创建。
- 遥测：日志确认 `Telemetry reporting disabled`。
- 探针：唯一 Collection 创建后精确删除，Candidate Collection 与 alias 写入均为 0。
- 运行资产：`E:\智能运营分析项目_运行资产\rag-r1\qdrant`，ACL 已限制。
- 机器证据：`bootstrap_report.json`、`preflight_runtime.json`、`runtime_probe.json`。

## 风险

Qdrant 对 Docker Desktop 的 E 盘 NTFS bind mount 报告 `Unrecognized filesystem - cannot guarantee data safety`。本轮开发/预发布功能可继续，但在该风险解决或被正式接受前，不得把可靠性门禁标记为全 PASS，也不得生产切换。

## 回滚

使用同一 Git 外 `runtime.env` 执行 Compose `stop qdrant` 即可停止服务；不删除 E 盘 storage/snapshots/tls，不删除镜像，不切换任何 alias。代码使用 `git revert <本包提交>`。
