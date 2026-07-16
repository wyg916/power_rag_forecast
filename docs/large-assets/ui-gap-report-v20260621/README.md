# UI 差异分析文档分卷说明

原始文件：

`docs/智能运营分析项目_UI优化参考图与当前功能差异分析说明文档_v20260621.docx`

由于原始 DOCX 超过当前 GitHub API 单文件上传链路的稳定负载范围，仓库改为保存两个二进制分卷、校验清单和恢复脚本。原始文件继续保留在本地，并由 `.gitignore` 排除。

## 恢复

在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\docs\large-assets\ui-gap-report-v20260621\restore.ps1
```

脚本默认恢复到原始路径；如果目标已存在，脚本会停止，避免覆盖。可通过 `-OutputPath` 指定其他输出路径：

```powershell
powershell -ExecutionPolicy Bypass -File .\docs\large-assets\ui-gap-report-v20260621\restore.ps1 `
  -OutputPath .\.codex_tmp\ui-gap-report-restored.docx
```

恢复完成后，脚本会核对文件大小和 SHA-256。预期 SHA-256：

`26ef6e7811cdfca2bc0f3d1c84782017ecfafc8c4f435d51a434f2a26c6b1c68`
