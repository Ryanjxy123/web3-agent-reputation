# 真实进度与会话交接

更新时间：2026-10-09；环境：用户 Windows 正式项目工作目录。

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
| M1-03 | DONE | 真实快照、声明 review、owner/executor 双 EIP-712 签名与单次 nonce |
| M1-04 | DONE | 授权、冻结意图、HTTP 发送与租约/crash reconcile 恢复 |
| M1-05 | DONE | 独立 RPC/纯断言，真实 A PASS、D 成功回执但 SEMANTIC_MISMATCH；CI b04a04a 通过 |
| M1-06 | DONE | 报告冻结、确定性 ZIP、并发/恢复/缺失/篡改拒绝、原生 A/D 报告 smoke 及166项全量回归通过 |
| M1-07 | DONE | PostgreSQL publisher nonce/outbox、签名后广播恢复、真实 EvaluationAnchor 发布、独立安全 ZIP verifier |
| M1-08 | DONE | 原生 API/worker/Anvil A/D 纵向演示；A/D bundle、A anchor、离线/在线 verifier、篡改拒绝 |
| FOLLOWUP-01 | DONE | 三能力模板与独立只读查询；具体状态及测试见 2026-10-09 任务记录 |
| FOLLOWUP-02 | DONE | 四态归因、标准 reason_code、原始响应证据及异常归因；具体状态及测试见 2026-10-09 任务记录 |
| FOLLOWUP-03 | DONE | 冻结 Evidence Bundle 逐任务重判、四态计数比较、历史格式兼容及独立 RPC 复查；最终 Review 修复已通过定向回归 |
| LOCAL-PG-JUNCTION | DONE | Windows PostgreSQL 改用 D:\web3-runtime 目录联接；R: 已移除，初始化、重启、数据完整性及13项定向测试通过 |

## 2026-10-09 / 本轮任务 1：三能力模板

- Implemented：共享 Task/Worker/Verifier 支持 get_tx_status、verify_record、anchor_record；查询固定块、指定参数及独立 RPC 对照；只读无执行绑定或业务广播；授权目标合约可独立选择，冻结代码 hash。
- Files changed：core models/record_verifier/reporting、platform application 与 EVM collector/record、受控 fixture、共享 Schema/OpenAPI/生成 TS、CAPABILITY_TASKS 与 ADR 0011。
- Tests：单元/reference 127 passed；真实 capabilities/reports/verification/execution 组合 35 passed / 0 skipped（339.59s）；固定块后写入不改变历史查询补测 1 passed（16.87s）。Ruff、mypy 52 files、52 Schema 与 diff check 通过；历史 M1 A/D bundle 离线复核 PASS。
- Review fixes：只读 report settlement、read profile 的 behavior=None、RPC null/null 不误作不存在、非 canonical/错误定位/确认不足不扣 Agent、历史块查询边界。
- Git：分支 feat/capabilities-task-replay，任务 1 提交 6f741c9；尚未 push。本轮完整稳定树检查与 CI 待全部 1–3 完成后执行。
- Limitations：每 run 一个能力槽位；当前复用既有 EVM ABI，未加第三方协议适配器。保留 M1 PARTIAL，未开发完整三维评分、前端或 ERC-8004。
- Next task：任务 2 四态结果与失败归因。

## 2026-10-09 / 本轮任务 2：四态与原因

- Implemented：复用 Outcome/Reason，新增证据驱动服务失败、业务失败、证据不一致和规则版本原因；新模板/断言规则为 v2，旧 v1 序列化兼容；预评审排除能力可 NOT_APPLICABLE，已声明支持不得排除。
- Tests：172 单元/reference passed / 0 skipped；任务归因纯单元 45 passed；真实 PostgreSQL/Anvil 归因、能力、核验、报告、执行组合 54 passed / 0 skipped（818.07s）；Ruff、mypy 52 files、52 Schema 通过。保留两条 Starlette/websockets 弃用警告。
- Review fixes：授权/派发/endpoint 不一致不能将 HTTP 500 算 Agent FAIL；畸形 HTTP status 和声明数组不能崩溃；Agent 服务错误不被后续 RPC 故障遮盖；链上可证实回滚使用 TX_REVERTED；派生响应与冻结原始 HTTP 不一致为 UNKNOWN；损坏 RPC 证据降为 UNKNOWN。补全 NOT_APPLICABLE 不派发、不读任务 RPC且可冻结/导出；早期 RPC UNKNOWN 可以按原判定冻结，后续链恢复不会重写原任务结果；M1 专属 suite 不接受排除的 anchor 能力。
- Compatibility：旧 v1 reason 与默认 wire serialization 保留；新增状态、原因、原始 HTTP envelope 和 rule_version 进入已有 Evidence Bundle/CAS；Schema/OpenAPI/TS 由共享类型生成。
- Limitations：非法 JSON 被安全出口拒绝，因无法保留可靠脱敏原文，保持 UNKNOWN。报告发布仍需可信链上下文；全任务独立复核在下一项实现。
- Git：阶段 2 Review 后提交 854610d，JSON null 边界补测提交 1d88cc7；尚未 push。

## 2026-10-09 / 本轮任务 3：证据驱动逐任务复核

- Implemented：ReportCore v1.1 冻结逐任务 outcome/reason/rule version 和四态计数；`task-replay-v1` 索引绑定计划槽位、原始输入、冻结输入及 Agent HTTP CAS。独立 Verifier 从这些输入调用现有纯规则逐项重判，重算断言、任务结果和四态计数，并重建报告统计/评分字段；不访问平台数据库/API、不重调 Agent。操作者可用 `--task-rpc-url` 另查任务链状态，失败只报告为平台 RPC UNKNOWN，不覆盖离线重判。
- Compatibility：`@2` + ReportCore 1.0 + 旧单任务索引仅作为本轮前已冻结报告的兼容格式；继续重判并返回计算计数，但明确输出 `task_count_comparison=NOT_AVAILABLE_LEGACY_REPORT`。新报告必须 `@2` + ReportCore 1.1 + `task-replay-v1`，否则以规则版本错配拒绝。当前 report builder 只支持每 run 单槽位；Verifier 拒绝多槽位 bundle，避免在未重建全报告统计时误报 PASS。
- Tests：Verifier/四态/报告契约单元组合 **74 passed / 0 skipped**；真实 PostgreSQL/Anvil A/D 报告导出、离线逐项复核及独立任务 RPC 复查 **2 passed / 0 skipped**（3 个其他报告用例 deselected）；旧 `runtime/local-chain` 与 `local-chain-v2` 的 A/D 四个真实 ZIP 也均离线复核通过，A 为 PASS，D 为 FAIL/SEMANTIC_MISMATCH。Ruff、Mypy 52 个源文件、54 份 Schema 检查通过。完整 `scripts/check.py` 和 GitHub CI 结果待稳定提交后运行/核实。
- Review fixes：补齐模板、ReportCore schema 与索引格式双向配对，拒绝移除 v1.1 任务摘要或降级索引；拒绝当前模型不支持的多槽位报告；NOT_APPLICABLE 跳过非必要链 RPC；损坏的原始 HTTP CAS 不再导致报告冻结异常崩溃，缺少匹配内容时明确拒绝冻结。修复一次 Ruff 导入排序。
- Final review：真实 NA 导出后复核首先复现 **1 failed**（CAS 去重复用原输入 ID）；已修复同 ID 来源兼容，并增加冻结 RPC 重判/未恢复错误/时间顺序、v2 结算原因及在线链身份一致性校验。相关单元组合 **101 passed / 0 skipped**（10.22s）；真实归因报告导出复核 **4 passed / 0 skipped**（14 个其他用例 deselected，119.61s），覆盖 FAIL、UNKNOWN、NOT_APPLICABLE 及 RPC 恢复后的原 UNKNOWN 保留。全量检查早期在 pytest 阶段因该 Review 问题主动中断，不记通过；修复稳定提交后重新运行。
- Limitations：旧格式报告没有冻结任务计数，无法声称与原报告计数比较；无可信 RPC 时结果证明冻结证据与版本化规则内部一致，不单独证明原始采集者诚实或当前链状态。在线复查是可选的，RPC 来源只接受操作者配置。本轮未实现三维评分、前端、ERC-8004 或第三方协议适配器。
- Git：分支 `feat/capabilities-task-replay`；任务 3 提交 b724f04；最终 Review 修复待提交，稳定树检查、PR 和 CI 状态待记录，尚未 push。
- Next task：FOLLOWUP-04/三维评分保持未开始；按用户要求本轮到任务 3 后停止，等待下一轮指令。

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
- CI：已核实上次提交 3019352 的 run 37028009864 为 success；8729af9 的旧 run 37027935606 被后续提交取消。本次 391d2c9 已推送，新 CI 结果待核实。
- Live evidence：原生 API/worker 已加载新实现，A/D 已恢复；smoke_verification 退出 0，IDENTITY_SMOKE_PASS、DISPATCH_SMOKE_PASS、VERIFICATION_SMOKE_PASS。runtime/local-chain/verification-smoke.json 保存实际 run 和断言；A PASS，D receipt.success PASS 但 request/hash 不符，最终 FAIL/SEMANTIC_MISMATCH。未从 fixture 标签生成结论。
- Compatibility：无 DB migration；旧计划缺 target_code_hash 时 UNKNOWN，不追填旧计划；新增 4 个共享核验模型及平台实例 domain salt 校验。新增断言与 TaskLink 继续 append-only/fencing。
- Known limitations：M1-06/07/08 报告、存证、独立 bundle verifier、完整 E2E 尚未完成。未降低 policy 门槛。Windows Docker WSL 与外部 OpenAPI 403 仍单列；本次未声称本机容器通过。
- Branch：feat/foundation-m0-m1；PR 授权规则 794c681、M1-05 实现 391d2c9 均已推送预期 origin；本验收状态另行提交。整项 M0+M1 尚未完成，尚未创建最终 PR。
- Next task：M1-06：从槽位/观测/独立断言派生统计，冻结 PARTIAL/overall=null 报告及无循环承诺的证据包。

## 2026-10-03 / M1-06

- Implemented：纯规则重新执行任务断言并派生互斥目的统计；复用原 policy-v1/scoring_reference，保持20/10/10与80%/60%门槛，mapping不因人工确认默认正确；PARTIAL/overall=null，D保留关键冲突建议。report worker 在冻结前再查链上证据与实际 Anchor head；短事务 fencing/advisory lock、同run幂等、前一报告未发布时拒绝竞争previous；CAS/manifest/ReportCore无循环承诺、稳定ZIP导出、真实源码版本。
- Files changed：core/reporting 与4个共享报告类型、application/reports、API/worker/verify入队、52份生成Schema/TS、smoke_reports、报告集成/manifest边界测试、ADR0009及运行文档。没有DB migration。
- Commands executed：ruff/mypy；Schema generate/check、TS generate；pytest报告定向及全量（FAIL_ON_SKIP=1）；前端build/test；forge test/ABI check；原生新版API/worker的smoke_reports。
- Tests：5项真实PG+Anvil报告集成通过（121.72s）；全量166 passed/0 skipped（591.52s）；mypy48 files、ruff、52 Schema、Vue2 tests/build、Foundry14 tests及ABI检查通过。覆盖A/D部分报告、完整文件承诺、固定JSON顺序与ZIP字节、真实密钥不出包、双作业仅一份revision且均成功、报告提交后作业ACK前中断恢复、旧lease拒绝、CAS修改/丢失拒绝。manifest另有8项循环和非可移植路径拒绝测试。
- Live evidence：smoke_reports退出0，runtime/local-chain/report-a.zip（131066 bytes）及report-d.zip（131661 bytes），各132成员；report-smoke.json记录真实report_id/hash。A为PARTIAL/INSUFFICIENT_EVIDENCE，D为PARTIAL/NOT_RECOMMENDED，两者overall=null、回执NOT_REQUESTED。源码存在未提交实现时正确标记-dirty，没有声称来自干净release。
- Runtime：原生API/worker已加载报告实现；全量测试期间A/D停止，完成后恢复。报告smoke复用已核验任务，不重新执行Agent写入。已冻结的本地A/D报告应在M1-07继续发布；不要新建竞争previous的未发布报告。
- Known limitations：发布outbox、真实锚定和独立ZIP verifier尚未实现；导出成功不等于独立复核通过。无Git部署需配置实际CODE_VERSION，完整Compose/E2E收尾归M1-08。本机Docker WSL与外部OpenAPI403仍单列。
- CI/Git：上一阶段b04a04a的run37033866824核实success；391d2c9旧run被后续提交取消。本次实现3f052d3已推送feat/foundation-m0-m1至预期origin，暂存diff/实际密钥/大小检查通过，新CI待核实。本验收状态另行提交；M1整体仍未完成。
- Next task：M1-07：持久签名/nonce后广播、unknown broadcast reconcile、独立安全ZIP与规则复算、可信配置下真实Anchor核验、篡改/换链测试。

## 2026-10-03 / LOCAL-PG-JUNCTION

- Implemented：按用户要求创建 `D:\web3-runtime` NTFS 目录联接，指向原中文项目的 runtime；local_postgres.py 自动创建/复用并验证同一目录，拒绝同名冲突和非 ASCII 入口。删除动态 subst 逻辑及未使用的 BIN 常量；原中文路径、文件、数据库凭证保持不变。
- Migration：切换前记录数据库 cluster system_identifier、26 张 public 表的行数和逐行内容 SHA-256；通过 pg_dump -Fc 保存 `runtime/backups/before-runtime-junction.dump`（135228 bytes，Git 忽略），pg_restore --list 验证可读。正常停库后通过目录联接重启；核对 R: 仍指向原 runtime 后移除该映射及 postgres-drive.json。移除 R: 后再次 stop/start/status 均退出 0，实际 postgres.exe/data_directory 均为 D:/web3-runtime 路径，未重新生成盘符。
- Commands/tests：用目录联接的 initdb 初始化唯一临时 cluster 成功并仅清理该临时目录；真实 psycopg SQL 连接/SELECT 1 通过；两次重启后的 cluster 标识及26张表全部行内容摘要均与切换前一致。`FAIL_ON_SKIP=1 .venv/Scripts/python.exe -m pytest -q tests/unit/test_local_postgres.py tests/integration/test_database.py tests/integration/test_api.py` 退出 0，13 passed/0 skipped（54.80s）。ruff check、ruff format --check 和 git diff --check 均退出 0。原有 Starlette/httpx、websockets 弃用提示仍存在。
- Files changed：scripts/local_postgres.py、tests/unit/test_local_postgres.py、README、LOCAL_RUNTIME、ADR0002、PLAN、STATUS。临时检查脚本和对比摘要保存在本次聊天 work 目录；备份仅在忽略的 runtime，未暂存凭证或数据。
- Git：从干净 2bcc6d6 创建本地短分支 `fix/postgres-runtime-junction`；本节与实现一起本地提交，实际 SHA 见 `git log -1`；NOT_PUSHED。用户此次授权为本地修复，未执行远程发布。
- Limitations/next task：目录联接在数据库运行期间保留；同盘另一个项目占用同名入口时会明确拒绝。此次仅验收本地 PostgreSQL 入口及相关 DB/API 测试，未重新运行全量链/前端/Compose 验收。下一业务任务仍为 M1-07，不变更原里程碑结果。

## 2026-10-03 / M1-07 + M1-08

- Implemented：`AnchorService` 通过 `anchor_jobs`/`signer_nonces` 持久化 nonce、signed transaction 和状态；广播异常按既有哈希 reconcile，回执追加到 `anchor_receipts`；新增报告/评价 anchor API 和 worker handler。`packages/verifier` 提供独立 `reputation-verify` CLI，安全读取 ZIP、核对全部 manifest/CAS、重放 `RecordVerificationInput`、重算断言/统计/评分，并在操作者 RPC 下核对链实例、交易、合约记录和确认深度。
- Tests：verifier path-traversal 单测通过；ruff、mypy、52 schema drift check 通过；冻结 `runtime/local-chain-v2` 上真实 PostgreSQL + Anvil + A/D 流程完成 identity、dispatch、verification、reports；`M1_ACCEPTANCE_PASS`：A/D 两个 bundle，A 真实 EvaluationAnchor CONFIRMED，离线 anchor `NOT_CHECKED`，可信 RPC online `CONFIRMED`，policy/blob tamper 拒绝。
- Live evidence：`runtime/local-chain-v2/report-a.zip`、`report-d.zip`、`report-smoke.json` 为忽略的本地运行产物；A/D 均 PARTIAL、overall=null，A 已发布。旧 `runtime/local-chain` 报告保留，未覆盖；新鲜链实例因旧 Anvil 已不可恢复而使用隔离 `local-chain-v2`，不把旧 bundle 描述为干净发行复现。
- Security：signed transaction、publisher secret、数据库凭据未进入 Git 或 bundle；verifier 不信任包内 RPC；无 RPC 不宣称链上成功；ZIP 拒绝路径穿越、重复/符号链接/高压缩比成员及未承诺文件。
- Limitations：本轮继续保留 Windows Docker WSL import 和 8004scan HTTP 403 单列；本地 M1 使用 Anvil，不代表公网最终性。M2 三能力完整评分未展开。
- Git：当前工作分支为 `feat/m1-07-m1-08`，包含之前保留的本地 PostgreSQL junction 提交；M1-07/M1-08 实现提交 `6c340b5`，状态提交、push、PR 和 required CI 仍待完成。
- Next task：M2（用户未授权扩展，本轮停止）。

## 2026-10-06 / WINDOWS-LOCAL-RUNTIME-SETUP

- Implemented：从私有 GitHub 仓库克隆 `main`；本机 Python、Node、pnpm、Foundry、PostgreSQL 与 solc 工具均安装在 Git 忽略的项目目录，不写系统 PATH、Python 注册表或全局包目录。
- Windows compatibility：本机 Hyper-V 排除 8534–9156 中的多个端口段，默认 8545/9101/9102 无法绑定。新增严格校验的 `LOCAL_RPC_URL`、`FIXTURE_PORT_A`、`FIXTURE_PORT_D` 覆盖；本机 `.env` 使用 18545/19101/19102，默认值和 Compose 内部端口不变。seed、注册元数据、受控 HTTP、测试和 smoke 共用相同配置；`smoke_agents.py` 同时尊重 `LOCAL_RUNTIME_DIR`。
- Runtime：PostgreSQL 17.11 运行于 127.0.0.1:55432；Anvil 运行于 127.0.0.1:18545，并每秒持久化到忽略的 `runtime/local-chain-v2/anvil-state.json`；API、worker、Vue、fixture A/D 已后台启动，PID 与日志位于 `runtime`。API/前端分别为 127.0.0.1:8000/5173。
- Tests：`uv run --env-file .env --all-packages python scripts/check.py` 退出 0；172 Python passed/0 failed、Ruff、mypy 52 files、52 Schema、生成 TS 无漂移、Vue build + 2 tests、Foundry 14 tests（含 256 fuzz）、3 ABI 全通过。仅保留既有 Starlette/httpx、websockets 弃用提示及受限 `.pytest_cache` 警告。
- Live acceptance：`LIVE_RUNTIME_PASS` 与 `PROTOCOL_SMOKE_PASS --recheck` 通过；此前同轮完成 `M1_ACCEPTANCE_PASS`，覆盖 A/D 真实调用、A PASS、D 成功回执但 SEMANTIC_MISMATCH、PARTIAL bundle、A anchor、离线/在线 verifier 和篡改拒绝。旧链运行产物保留在忽略的 runtime，未删除或伪装为当前链。
- Git：分支 `fix/windows-local-runtime-ports` 已推送；实现提交 `0855e03`、清理提交 `13db4fd`；PR #3：`https://github.com/Ryanjxy123/web3-agent-reputation/pull/3`。required checks 已触发，最终结果以 PR 页面为准。
- Next task：业务里程碑仍为 M2；本地环境任务完成，不扩大到公网或主网。
