# 真实进度与会话交接

更新时间：2026-10-02；环境：用户 Windows 正式项目工作目录。

| Task ID | Status | 实施结果 |
|---|---|---|
| M0-01 | DONE | 已克隆私有仓库、保留 main 历史、创建功能分支、安全安装启动基线并合并 README；36 项参考测试通过 |
| M0-02 | DONE | 四包 uv workspace、真实锁、Vue 构建、Foundry 编译与测试通过 |
| M0-03 | DONE | 共享 DTO、33 份生成契约、TS 类型、确定性哈希及校验测试通过 |
| M0-04 | DONE | 真实 PostgreSQL 迁移、只追加约束、幂等存储、租约/fencing 和并发测试通过 |
| M0-05 | DONE | 认证 API、网络出口、worker 租约、原生运行及 Linux Compose 实测通过；Windows Docker 引擎仍受 WSL 导入问题影响 |
| M0-06 | DONE | 本地完整检查和远端 foundation-quality / foundation-compose 均通过，无关键测试跳过 |
| M0-07 | PARTIAL_EXTERNAL_BLOCKED | ERC-8004 真实 commit/ABI/许可与规范字节已锁；8004scan OpenAPI HTTP 403，不阻塞本地 M1 |
| M1-01 | DONE | 三个自研合约、生成 ABI、14 项 Foundry 测试（含 256 次 fuzz）通过 |
| M1-02 | DONE | 三合约真实部署、双 seed、持久 A/D、9 项真实 Anvil 测试及原生服务重启后的 HTTP 幂等复查通过 |
| M1-03..08 | NOT_STARTED | 身份绑定、业务 worker、报告、存证和独立复核尚未实现 |

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

## 2026-10-02 / M0-05 实现与原生验收

- Implemented：随机本地凭证、恒定时间 bearer 认证、结构化错误与 request ID；真实 DB readiness/候选注册/查询；共享输出 DTO 和真实路由 OpenAPI/TS；精确受控出口、无代理/跳转、大小/深度/压缩限制；独立 worker 的心跳、失租取消、有限重试；隔离 Compose 网络和 digest 固定镜像。
- Files changed：api、worker、network、init_local、Dockerfile/compose/env.example、schema generator/生成契约、worker/API/network tests、LOCAL_RUNTIME runbook、工具链记录。
- Commands executed：pytest -q；ruff check；mypy 四包；generate_schemas / --check；pnpm generate:types/build/test；真实 uvicorn HTTP live/ready；docker compose config --quiet；buildx imagetools inspect 四个基础镜像。
- Tests：107 passed；ruff 通过；mypy 25 files 通过；35 份契约无漂移；Vue build/typecheck、2 tests 通过；真实 HTTP health 通过；Compose 配置解析通过。Starlette TestClient 提示 httpx 将弃用，当前测试通过，无隐藏跳过。
- Known limitations：M0 worker 只有经过集成测试的调度器，M1 业务 handlers 尚未接入；本地 Docker 引擎尚未启动，不能宣称容器验收通过。公网 HTTP 禁用。
- Blocker：Docker Desktop per-user 安装成功，WSL import-in-place 报 Wsl/ERROR_PATH_NOT_FOUND；VHD 文件存在且原有发行版可运行。未修改/注销用户发行版；继续原生验证与 Linux CI，不以此阻断独立开发。
- Branch：feat/foundation-m0-m1；M0-04 commit 5f67ac8，已推送；本任务待提交。
- Next task：M0-06 CI，完成容器构建/启动验证；M0 总体仍待验收。

## 2026-10-02 / M0-06

- Implemented：foundation-quality 与 foundation-compose 两个固定 CI check；actions 固定真实 commit，contents:read，不注入生产凭证；完整 check.py、真实 HTTP/RPC smoke、禁止跳过测试的 CI gate。
- Files changed：.github/workflows/ci.yml、scripts/check.py、scripts/smoke_runtime.py、tests/conftest.py。
- Commands executed：uv run --all-packages python scripts/check.py（退出 0）。
- Tests：107 Python passed / 0 skipped；ruff、mypy 25 files、35 schema、生成 TS 无漂移；Vue build 和 2 tests；Foundry 1 passed / 0 skipped。
- Known limitations：远端 Actions/Compose 尚待执行；本机 WSL 引擎问题独立记录，未将 mock 视为容器验收。
- Branch：feat/foundation-m0-m1；M0-05 commit 6ceb06a；当前任务待提交/推送。
- Next task：检查真实 CI，修复失败；M0-07 固定可取得的上游资料。

## 2026-10-02 / M0-07

- Implemented：读取官方 master 当前 commit b9e466c250744a7e06b13dff9d3c2844ed64f825；保存原始 Identity ABI、含 CC0 声明的 README 和官方 EIP 页面；真实字节数/SHA-256/来源登记；外部接入仍 disabled。
- Files changed：configs/upstream-lock.json、third_party/erc8004、tests/unit/test_upstream.py。
- Commands executed：gh api repo/commits/tree；官方 raw/EIP/OpenAPI HTTP GET；pytest 上游字节/接口/禁用状态校验；ruff。
- Tests：1 passed；ruff 通过。远端 ecaf110 的 foundation-quality 已通过，Compose smoke 正在运行。
- Known limitations / Blockers：8004scan OpenAPI HTTP 403 → BLOCKED_DOWNLOAD；没有生成假 hash/文件。没有公网 RPC 部署核验，usable=false。上游无独立 LICENSE 文件，实际许可声明在已保留 README。
- Branch：feat/foundation-m0-m1；M0-06 ecaf110 已成功推送；当前任务待提交。
- Next task：收尾 M0 CI 运行验证，然后 M1-01 三个真实演示合约。

## M0 运行回归与修复

- Windows 原生 `python scripts/smoke_runtime.py` 退出 0：API DB readiness、Vue 代理、未认证 POST=401、真实 Anvil chainId=31337 全通过。
- CI ecaf110 / f2df4ca 的 quality 均通过；Compose 构建/迁移/API 内部健康通过，但宿主入口失败，未隐藏失败。
- 定位：只连接 internal bridge 时未生成 published ports。新增仅 API/web/Anvil 的 ingress bridge，仍绑定 127.0.0.1；数据库/worker/fixture 保持内部，ADR 0003 说明信任边界。
- 同时修复非 ASCII bearer token 导致 compare_digest 异常的边界；3 项真实 API 集成测试通过。
- 上游原始文件设置 -text/-diff，防止 Windows checkout 改换行后破坏 SHA-256；源文件空白属于原文，未为 lint 修改原始字节。
- 当前修改容器验证待重跑；此前提交 f2df4ca 已推送。

## M0 验收完成

- GitHub Actions run 37017699537（commit ecb8ba5）：foundation-quality=success，foundation-compose=success；容器真实构建、迁移、宿主 API/web proxy/认证/Anvil smoke、独立 worker CLI 均通过。
- Windows 原生平台健康链路已通过；Windows Docker Desktop 的 WSL import 错误仍是已知环境限制，未声称本机 Docker 成功。可使用原生本地开发链完成 M1。
- 最后契约回归：AgentView 来源与数据库/SnapshotCore 共用 controlled/public_registry/replay，真实 API 测试覆盖受控来源；45 项 API+契约测试与前端 build 通过。
- M0-07 外部 OpenAPI 403 不阻塞 M1，所有公网接入继续禁用。
- Next task：M1-01：自研 Registry、RecordRegistry、EvaluationAnchor 及真实 Foundry 正反测试；不扩大 M2。

## 2026-10-02 / M1-01

- Implemented：owner/revision/instance 身份合约；executor+request 去重业务记录；明确 admin/evaluator 权限、前向 hash/序号、历史报告幂等发布；编译生成 ABI 和 CI 漂移校验；删除无业务引用的 ProtocolVersion 探针。
- Files changed：contracts/src/test/abi、generate_abis.py、check.py、ADR 0004。
- Commands executed：forge fmt/build/test -vv；针对构造失败测试执行 -vvvv 检查路径；generate_abis / --check；ruff。
- Tests：14 Foundry passed、0 failed/0 skipped；记录不可覆写 fuzz 256 runs；真实编译 ABI 校验通过。构造 revert 会结束整个测试，已拆独立用例以确保后续零字段/超长 URI 路径实际执行。
- Known limitations：尚未部署/seed；不能据此声称 A/D 或 M1 闭环已通过。测试中的 gas 是执行该测试的实测，不是生产调用基准。
- Full regression：scripts/check.py 退出 0；109 Python passed、mypy/ruff/35 Schema/TS 无漂移、Vue 2 passed/build、Foundry 14 passed、编译 ABI 无漂移。
- Branch：feat/foundation-m0-m1；M0 最终提交 f7981d2、M1-01 提交 48429f8 均已推送预期 origin；工作树干净。
- Next task：M1-02 本地部署、幂等 seed 与持久任务 Agent。

## 2026-10-02 / M1-02

- Implemented：受限本地部署与签名 setup outbox；六个独立随机角色；幂等 seed、真实 D 无关成功交易；受控 HTTP v1 服务；独立 SQLite 意图/nonce/signed bytes 账本、恢复和重放；共享公共部署/协议 DTO 与生成契约。
- Files changed：application/local_deploy/local_seed、CLI deploy-local/seed、fixture_agents/service、core/runtime DTO、生成 schemas/TS、smoke_agents.py、9 项链集成测试、ADR 0005 和运行说明。
- Commands executed：真实 reputation deploy-local、seed 两次；独立 uvicorn A:9101/D:9102；smoke_agents；停止并重启两个服务后 smoke_agents --recheck；pytest -q；ruff/mypy；Schema check；Vue build。
- Tests：118 Python passed（新增 9 项真实 Anvil：角色分离/重复 seed/HTTP 幂等/磁盘重开/签名后退出/广播后退出/nonce 并发/D 反例/真实 reset）；mypy 30 files、ruff、39 Schema、Vue typecheck/build 通过。保留 TestClient/websockets 弃用警告，无隐藏 skip。
- Live evidence：runtime/local-chain/protocol-smoke.json 保存真实 request/hash/tx/event；A 匹配、D receipt=1 但 request/hash 不匹配。服务重启后的原请求返回相同 txHash，A 仅 1 条相应事件，D 对当前任务 0 条事件。
- Known limitations：当前是 synthetic snapshot 的协议 smoke；不能称完整平台绑定/worker/报告/复核已完成。M1 fixture Compose 编排归纵向集成收尾，基础 Compose 已验证。私钥/账本/证据均在忽略 runtime，未提交。
- Branch：feat/foundation-m0-m1；实现提交 b8684a0 已推送；上一个 CI 29e4425 为 success，新代码 CI run 37021958255 已启动，结果待核实。
- Blockers：无当前实现阻塞；本机 Docker WSL 问题、8004scan 403 继续单列。
- Next task：M1-03 真实注册快照、人工映射确认与 owner/executor 双 EIP-712 签名绑定。

## 2026-10-02 / M1-03

- Implemented：固定真实区块的 demo reader；异步 ingest 快照；人工声明版本确认；随机单次 nonce 与 owner/executor 双 EIP-712 验证；当前身份核对/旧快照拒绝/合约账户 UNKNOWN；脱敏后 CAS 证据；API 与独立 worker 静态接入。
- Files changed：core binding/DTO、identity service/demo reader/evidence store、API/worker、生成 Schema/OpenAPI/TS、smoke_identity、ADR 0006 与运行说明。
- Commands executed：真实 PostgreSQL + Anvil pytest；ruff/mypy；Schema generate/check + TS generate；Vue build/test；forge test/ABI check；重启原生 API、独立 worker 进程运行 smoke_identity。
- Tests：135 Python passed（新增 16 身份链/数据库集成用例及 1 脱敏存储测试）、14 Foundry passed/0 skipped、2 Vue passed、40 Schema 验证、mypy 37 files、ruff、Vue typecheck/build 与 ABI 检查退出 0。首轮发现全零签名抛 BadSignature，已修复且回归通过。保留两项上游弃用警告。
- Live evidence：runtime/local-chain/identity-smoke.json 保存 A/D 真实 snapshot、review、binding 和 job 引用；两者 VERIFIED。签名发生在操作者脚本，API/worker 不读取 owner/executor 私钥。D 身份通过不表示 D 业务正确，后续需独立业务断言。
- Recovery/security：同 nonce 并发只有一个成功；提交快照后退出重领保留同一 snapshot_id；竞争 refresh 返回 SNAPSHOT_CONFLICT；已刷新旧版本不能新签；错误 Agent/endpoint/nonce/domain/role/signer/expired challenge 拒绝；敏感元数据拒绝且不保存。
- Compatibility：无需 DB migration；DTO 新增可选结果引用和挑战类型；JSON Schema/OpenAPI/TS 同源生成。未开启公网注册抓取。
- CI：前一提交 2119c0e 的 run 37022077859 已核实 success；本次 eea511a 的 run 37024611634 已启动，结果待核实。
- Known limitations：health readiness 当前仅检查 DB/migration；链配置/实例在身份操作时核验。M1 评价执行、报告、发布、独立复核及完整 Compose E2E 尚未完成。Windows Docker WSL 和外部 OpenAPI 403 仍单列。
- Branch：feat/foundation-m0-m1；M1-03 实现提交 eea511a 已推送预期 origin；本验收状态单独更新。
- Next task：M1-04 授权边界、预持久化任务计划、执行/重启 reconciliation；不降低评分门槛。

## 2026-10-02 / M1-04

- Implemented：最小受控 grant 与撤权；payload-bound Idempotency-Key；当前 snapshot/review/EOA binding 及授权窗口检查；一次 functional slot 的 CSPRNG 请求/合成数据/expected facts/初始 dispatch/job 原子保存；计划及发送前链见证；真实 HTTP 执行、固定路径查询、可信 RPC 记录恢复；仅明确未接受时原 id/payload 有限重投。
- Recovery/security：append-only attempts/observations/dispatch events；每次请求前授权与 lease fencing；跨 run 间隔、每 Agent active run 1、全局 evaluate 有效租约 2；取消未发送任务、已发送继续核对；撤权后禁止 Agent HTTP，仅可信 RPC 恢复；平台 RPC 失败保留 UNKNOWN，未实现健康窗口证明前不扣 Agent 超时分。
- Files changed：evaluation/execution service、RPC record reconciliation、API/worker/jobs、共享 DTO 及生成契约、smoke_execution、11 个新增用例、ADR 0007/运行说明。
- Commands executed：pytest 全量（FAIL_ON_SKIP=1）；ruff/mypy；44 Schema generate/check 与 TS generate；Vue build/test；Foundry/ABI check；重启原生 API/worker/A，执行真实 smoke_execution（包含重新绑定）。
- Tests：146 Python passed/0 skipped、14 Foundry passed、2 Vue passed、mypy 41 files、ruff、44 Schema、前端 build 与 ABI 校验通过。完整 pytest 282.45s。关键用例启动独立 worker，在真实 HTTP 返回后 os._exit(86)，新 worker 只 GET 原 request，链上仅一条记录；旧 lease 写回拒绝。另覆盖发送前退出、并发同 key、配额、取消/撤权、RPC 拒绝连接等。
- Live evidence：runtime/local-chain/execution-smoke.json 保存 A/D 的实际 run/grant/plan/observations，含各自候选 txHash；输出 IDENTITY_SMOKE_PASS 与 DISPATCH_SMOKE_PASS。候选尚未独立验证，因此两个 run 均不声称业务通过。
- Compatibility：无 DB migration；CaseSlot 新增可选 synthetic_input（有值则校验摘要），RunPlan 新增 planning_evidence_refs，EvaluationRun 增加 cancel_requested；Schema/OpenAPI/TS 已生成。全量 pytest 使用端口 9101，已在 runbook 明确停止/恢复 demo A。
- CI：M1-03 最新 ef5fede 的 run 37024686970 已核实 success；eea511a 的旧 run 因后续提交取消，并非失败。本次新代码 CI 待推送核实。
- Known limitations：独立业务断言/评分/报告/发布/复核和完整 M1 Compose E2E 尚未完成；当前 run 处于 VERIFYING，未有业务断言的 settled slot 仍记 unknown。Windows Docker WSL、外部 OpenAPI 403 继续单列。
- Branch：feat/foundation-m0-m1；M1-04 实现 8729af9 已推送预期 origin；CI run 37027935606 已启动、结果待核实。本验收状态单独更新。
- Next task：M1-05：保存可信 RPC 的 tx/receipt/block/log，并独立验证 request/hash/executor/target/instance/deadline/finality；必须得到 A PASS 与 D 无关成功交易 FAIL。

## 2026-10-03 / M1-05

- Implemented：受信 RPC 原始结果采集、共享回放输入、纯任务关联断言、追加式 TaskLink/断言和 verify worker 作业；目标字节码摘要及紧邻发送前链头校验；GET verification API；独立进程 smoke 脚本。
- Files changed：core/models/verification、record_verifier、adapters/evm/collector、application/verification、API/worker/execution/planner、48 份生成 Schema/TS、test_verification、smoke_verification、ADR 0008/运行说明。
- Commands executed：pytest -q -x（FAIL_ON_SKIP=1）；pytest -q -x tests/integration/test_verification.py；ruff/mypy；generate_schemas/generate:types；前端 build/test；forge test/ABI check；独立原生 API/worker/A/D 的 smoke_verification。
- Tests：定向首轮 6 passed / 1 failed，修正测试对正常 Agent 重复请求返回真实 revert 的错误预期后，预写成功交易另行独立采集并验证窗口。全量首轮 152 passed / 1 setup error（Agent 启动超过 30s）；只把进程启动等待调为 90s，业务窗口保持 60s，重跑 153 passed/0 skipped（414.60s）。补充独立回放校验平台实例 domain salt 后，相关 7 项测试再通过（156.72s），含真实 RPC 拒绝连接、另一 Anvil、不存在交易、错误执行者/目标的真实成功交易。ruff/mypy 45 files、48 Schema、前端 build/2 tests、Foundry 14 tests/ABI 校验通过。
- CI：已核实上次提交 3019352 的 run 37028009864 为 success；8729af9 的旧 run 37027935606 被后续提交取消。本次未提交/推送。
- Live evidence：原生 API/worker 已加载新实现，A/D 已恢复；smoke_verification 退出 0，IDENTITY_SMOKE_PASS、DISPATCH_SMOKE_PASS、VERIFICATION_SMOKE_PASS。runtime/local-chain/verification-smoke.json 保存实际 run 和断言；A PASS，D receipt.success PASS 但 request/hash 不符，最终 FAIL/SEMANTIC_MISMATCH。未从 fixture 标签生成结论。
- Compatibility：无 DB migration；旧计划缺 target_code_hash 时 UNKNOWN，不追填旧计划；新增 4 个共享核验模型及平台实例 domain salt 校验。新增断言与 TaskLink 继续 append-only/fencing。
- Known limitations：M1-06/07/08 报告、存证、独立 bundle verifier、完整 E2E 尚未完成。未降低 policy 门槛。Windows Docker WSL 与外部 OpenAPI 403 仍单列；本次未声称本机容器通过。
- Branch：feat/foundation-m0-m1；PR 授权规则已独立提交 794c681；M1-05 实现待提交/推送。
- Next task：M1-06：从槽位/观测/独立断言派生统计，冻结 PARTIAL/overall=null 报告及无循环承诺的证据包。
