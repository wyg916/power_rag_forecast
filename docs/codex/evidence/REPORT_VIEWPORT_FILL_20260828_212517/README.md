# 报告中心日报与审核发布页视口填充验收

## 任务范围

- 报告中心 / 日报：消除页面底部和右侧多余空白，使发布记录内容完整显示。
- 报告中心 / 报告审核与发布：消除页面底部和右侧多余空白。
- 未改指标卡、筛选、列表、预览、图表、按钮、API、权限、状态机或数据口径。
- `report-weekly` 保持既有外层留白和滚动策略，证明本次样式只作用于用户指定页面。

## 实现

- 页面根节点增加基于 `activeSubKey` 的报告视图修饰类，仅供 CSS 精确限定日报与审核/发布页。
- 指定页面取消报告内容壳的右侧 `16px` 内边距、`15px` 稳定滚动条槽和底部 `92px` 浮动助手预留；页面继续由卡片内部区域承担滚动。
- 日报发布记录卡继承剩余高度，四个时间线节点纵向使用可用空间；说明文案允许正常换行，不再使用省略裁切。

## 1920×926 / 100% 浏览器验收

| 项目 | 修改前 | 修改后 |
|---|---:|---:|
| 工作区右边界 | 1889 | 1920 |
| 工作区底边界 | 834 | 926 |
| 右侧空白 | 31px | 0px |
| 底部空白 | 92px | 0px |
| 日报发布记录节点 | 4 | 4，全部可见 |
| 指标说明 | 4/4 可见 | 4/4 可见 |
| 控制台 warning/error | 0 | 0 |

日报发布记录四个说明文本的 `scrollHeight` 均等于 `clientHeight=16px`，最末节点底边 `919px` 小于卡片内容底边 `925px`，无裁切。

## 截图

- `screenshots/report-daily-full-1920x926.jpg`
- `screenshots/report-review-full-1920x926.jpg`

浏览器普通截图接口会按当前可见窗口裁切到 1506px，故验收使用同一浏览器的 `fullPage` 截图；页面布局视口仍为 `1920×926`，截图文件尺寸也是 `1920×926`。

## 测试

- `npm run typecheck`：PASS。
- `npm run build`：PASS，Vite 3,690 modules。
- `node --test tests/reportCenterPresentation.test.mjs`：4/4 PASS。
- `pytest tests/test_p6_report_center_viewport_layout.py tests/test_phase5_c_report_generation.py`：14 passed，2 skipped；跳过项均因未配置隔离数据库 URL。
- 全量前端 unit：56/57；唯一失败仍是既有全局 10px 视觉门槛，与上一主项目基线一致，本次未修改对应规则。

## 数据库与业务影响

无数据库迁移、Seed、模型、报告状态或外部网络写入；浏览器验收只做页面导航、只读几何检查与截图，未点击审核、发布、重新生成或下载操作。

## 回滚

对本任务独立提交执行 `git revert <commit>`。修改前检查点：`backups/phase3/20260828_212517_REPORT_VIEWPORT_FILL_PRE`。
