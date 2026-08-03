# 测试摘要

- 凭据轮换：PASS；新凭据有效、旧凭据拒绝、安全身份仍有效、活动旧会话 0。
- 角色/ACL：PASS；轮换前后稳定哈希一致。
- 双父基线：PASS；final-integration 与 integration 均为新基线祖先，代码 tree 与 final-integration 一致。
- RAG enterprise/R1/release/Qdrant 定向回归：`330 passed`。
- AI/权限/脱敏裸环境诊断：`108 passed / 4 failed`；3 项缺正式业务证据资产，1 项缺 production 数据库配置。该组按既有 final 报告归类为裸环境诊断，不作为正式隔离回归，也未被改写为 PASS。
- 关键 RAG/OCR/检索脚本 `py_compile`：PASS。
- `git diff --check`：PASS。
- 新凭据扫描：工作线与任务前检查点共扫描 1,246 个文件，命中 0；新增任务文档通用连接串/Authorization 模式命中 0。
- GitHub 推送：BLOCKED；本机到 `github.com:443` 无法连接，GitHub API 复核 `1de4036` 尚不存在于远端。
