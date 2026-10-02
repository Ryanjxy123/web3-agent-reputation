# 真实进度与会话交接

更新时间：2026-10-02；环境：用户 Windows 正式项目工作目录。

| Task ID | Status | 实施结果 |
|---|---|---|
| M0-01 | DONE | 已克隆私有仓库、保留 main 历史、创建功能分支、安全安装启动基线并合并 README；36 项参考测试通过 |
| M0-02 | DONE | 四包 uv workspace、真实锁、Vue 构建、Foundry 编译与测试通过 |
| M0-03 | DONE | 共享 DTO、33 份生成契约、TS 类型、确定性哈希及校验测试通过 |
| M0-04 | DONE | 真实 PostgreSQL 迁移、只追加约束、幂等存储、租约/fencing 和并发测试通过 |
| M0-05..06 | NOT_STARTED | API、安全编排、CI 尚未完成 |
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

## 2026-10-02 / M0-02

- Implemented：四个可安装 Python 包及依赖方向；uv.lock、pnpm-lock.yaml 实际解析；Vue 平台连接页；Foundry 工作区及协议版本；项目级工具安装脚本和 doctor 命令。
- Files changed：根 pyproject/.python-version/uv.lock；四包 pyproject；CLI；apps/web；contracts；scripts/tools.ps1；configs/toolchain.json；workspace tests；ADR 0002。评分参考只将歧义变量重命名，公式不变。
- Commands executed：隔离 venv 安装 uv 0.9.3；官方 Foundry 1.8.4 下载并验证 SHA-256；uv lock；uv sync --locked --all-packages；独立空环境再次 sync；四包 import；pytest；ruff；mypy；pnpm install --frozen-lockfile/build/test；forge build/test。
- Tests：空环境锁定安装与四包 import 通过；pytest 38 passed；ruff 通过；mypy 4 source files 通过；Vue typecheck/build 通过、2 tests passed；Solc 0.8.30 build 通过、Foundry 1 passed。
- Known limitations：当前合约测试只证明工作区可运行，不是 M1 合约验收。API/DB/worker/复核器尚未实现；Docker/Compose 尚未安装，容器镜像锁和运行验证归 M0-05；PostgreSQL 官方便携包下载中。
- Blockers：无用户阻塞；Docker 条件待 M0-05 处理。
- Branch：feat/foundation-m0-m1。
- Commit SHA：仓库基线 0903f76；路径迁移 e72b039；本任务待提交，下一任务记录实值。
- Push status：NOT_PUSHED；将在基础检查通过后推当前功能分支。
- Next task：M0-03 共享领域契约、Schema 和生成类型。

## 2026-10-02 / M0-03

- Implemented：身份/快照/声明/双签绑定/grant/run/slot/observation/assertion/task-link/report/receipt；严格地址、uint256 字符串、UTC 毫秒时间、整数基点；四态及原因码；静态协议注册表和 ports；JCS 与 Ethereum Keccak 公用函数；API 输入契约；由 DTO 生成 JSON Schema/OpenAPI components/TS。
- Files changed：core/models、evidence.py、ports.py、registry.py；schemas/generated；scripts/generate_schemas.py；web generated types；domain 示例；tests/unit/test_contracts.py。
- Commands executed：pytest -q；ruff check；mypy；generate_schemas / --check；pnpm generate:types；pnpm build。
- Tests：79 passed；ruff 通过；mypy 8 source files 通过；33 份 Schema 验证和重新生成无漂移；TS 类型检查及 Vue build 通过。初次新增测试导入了不存在的 evaluate，已修正为实际 evaluate_from_stats，完整重跑通过。
- Known limitations：OpenAPI 此时只有类型，没有声称路由已实现；M1 task DTO 只执行 anchor_record；其他能力的完整任务适配属于 M2。哈希一致性不代表链上真实性。
- Blockers：无。PostgreSQL 17.11 便携二进制已成功运行 --version；数据库迁移和队列尚待 M0-04。
- Branch：feat/foundation-m0-m1。
- Commit SHA：M0-02 a0a0ed1；当前任务提交待生成。
- Push status：a0a0ed1 已成功推送 origin/feat/foundation-m0-m1；未推 main。
- Next task：M0-04：真实 PostgreSQL 模型、迁移、租约与 fencing 验收。

## 2026-10-02 / M0-04

- Implemented：SQLAlchemy 关系表与 JSONB 文档；Alembic 单一冻结迁移；FK/唯一/check 约束；append-only 触发器与 run plan 不可变；原子保存 plan/slot/job；SKIP LOCKED、租约、单调 token、heartbeat、重试上限、带 fencing 的事务写回。
- Files changed：platform/infrastructure/db、migrations、alembic.ini、CLI migrate、local_postgres.py、tools.ps1、真实 DB 测试、共享测试工厂和 py.typed 标记。参考测试仅格式整理，评分参考只显式收窄已判定值的类型。
- Commands executed：initdb；pg_ctl start；alembic upgrade head/current/check；空测试库 downgrade base → upgrade head；reputation migrate；pytest；ruff；mypy；check_bootstrap。
- Tests：87 passed（包括 8 个真实 PostgreSQL 集成测试）；mypy 19 source files 通过；ruff 通过；reference 36/36 通过；Alembic head=6aa7efd8cbc4，无模型漂移。
- Known limitations：队列层恢复已验证；跨 HTTP/链的业务恢复仍需 M1。开发数据库管理员可关闭触发器，这属于信任边界。Compose 尚未验证，M0 不能整体标完成。
- Windows fix：原生 initdb 在中文绝对路径下出现 UTF8 错误；脚本动态选择空闲盘符映射至同一 runtime 目录（当前 R:），未复制/移动项目。重试初始化成功。数据库仅 loopback:55432，UTC 会话；随机凭证只在被忽略文件。
- Failures resolved：新增测试导入路径修复为 pytest pythonpath；已有参考测试格式问题已整理；mypy 改用包名检查并添加 py.typed，修复 Optional Fraction 收窄，不改变规则。
- Branch：feat/foundation-m0-m1。
- Commit SHA：M0-03 f2ba3ac；当前任务待提交。
- Push status：远端已到 a0a0ed1；后续提交待推送。
- Blockers：无用户阻塞。WSL 2.7.3 可用，正在下载签名官方 Docker Desktop，准备 M0-05 per-user 安装和 Compose 验证。
- Next task：M0-05 安全网络、认证 API/worker 与本地编排。
