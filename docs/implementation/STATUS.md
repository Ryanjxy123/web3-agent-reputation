# 真实进度与会话交接

更新时间：2026-10-02；环境：用户 Windows 正式项目工作目录。

| Task ID | Status | 实施结果 |
|---|---|---|
| M0-01 | DONE | 已克隆私有仓库、保留 main 历史、创建功能分支、安全安装启动基线并合并 README；36 项参考测试通过 |
| M0-02..06 | NOT_STARTED | workspace、契约、数据库、API、CI 尚未完成 |
| M0-07 | NOT_STARTED | 公网上游准备不阻塞本地 M1 |
| M1-01..08 | NOT_STARTED | 合约、Agent、worker、报告、存证和复核尚未实现 |

## 2026-10-02 / M0-01

- Implemented：Git/认证/目录审查；启动包 44 项 manifest 校验；安全 clone、fetch 和功能分支；规划 overlay；README 语义合并；保留 Ponytail 约束。
- Files changed：AGENTS、PLAN、README、docs、scripts、configs、core 评分参考、fixtures golden、reference tests、Git 模板。未复制启动包外层、ZIP、验证日志或安装器。
- Commands executed：git rev-parse/status/remote/branch/log、工具版本检查、gh auth status/login、git ls-remote、gh repo view、git clone、git fetch origin --prune、git switch -c、install_plan --dry-run / --on-conflict sidecar。
- Tests：启动包 SHA-256/size 校验 44/44；安装 dry-run 退出 0；py -3 scripts/check_bootstrap.py 退出 0、36/36 通过；git_doctor 退出 0 / REMOTE_MATCH；git diff --check 通过。
- Known limitations：安装的是规划和评分参考，不能据此声明 M0/M1 完成。Docker/Compose、Foundry/Anvil、PostgreSQL 尚未找到；uv 待安装。
- Blockers：先前 BLOCKED_EXTERNAL_AUTH 已解除；当前没有需要用户介入的阻塞。
- Branch：feat/foundation-m0-m1。
- Commit SHA：基线 e9430d186d7c63ddc8e2da2d70231ccb4873c8b1；启动基线提交 0903f76；36 项参考测试通过。
- Push status：NOT_PUSHED。
- Decisions：以用户明确分支名为准；API 使用 BACKLOG/spec 的 /api/v1；M0 卡片编号以 BACKLOG 为准。
- Path migration：6 处旧项目路径和 2 处父目录/启动包示例已迁移；无业务绝对路径；无故意保留的旧引用；仅修改两份 Markdown。
- Next task：M0-02：隔离安装并锁定工具链、建立真实 workspace。
