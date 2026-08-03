# 回滚

- 本轮仅修改 reranker 单次调用的输入去重和对应测试，不涉及数据库、Qdrant 数据、release、alias、snapshot、Compose 或公共配置。
- 提交前回滚：对两个修改文件应用本轮反向补丁。
- 提交后回滚：对本轮独立提交执行 git revert；不得 reset、rebase、cherry-pick 或切换其他工作树。
- 回滚后复跑相同74项定向回归。