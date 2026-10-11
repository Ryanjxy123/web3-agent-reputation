# 本地基础运行

在仓库根目录执行；随机凭证只存 `.env` 和 `runtime/local-db.json`，不提交或打印。

Windows 原生基础环境（含中文路径验证）：

`scripts/local_postgres.py` 自动使用项目所在盘根目录的 `web3-runtime` 目录联接（本机 `D:\web3-runtime`）访问原 runtime；中文项目目录和文件保持原位，不再创建 R: 等虚拟盘符。目录联接需在数据库运行期间保留；同名路径指向其他目录时脚本拒绝使用，不覆盖已有文件。

若 Windows/Hyper-V 将默认端口列入排除范围，可在 `.env` 和启动服务的终端设置 `LOCAL_RPC_URL`、`FIXTURE_PORT_A`、`FIXTURE_PORT_D`（例如 `http://127.0.0.1:18545`、19101、19102）。deploy、seed、受控出口、smoke 与测试会共同读取这些值；Compose 内部网络仍使用默认端口。

```powershell
. ./scripts/tools.ps1 -Install
uv sync --locked --all-packages
uv run --all-packages python scripts/init_local.py
uv run --all-packages python scripts/local_postgres.py init
uv run --all-packages python scripts/local_postgres.py start
uv run --all-packages reputation migrate
uv run --env-file .env --all-packages uvicorn reputation_platform.api.app:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

另开终端运行 `uv run --env-file .env --all-packages reputation worker`。worker 必须加载与 API 相同的本地 RPC、runtime 和 fixture 端口配置。worker 已接入 ingest/evaluate/verify/report handler；领取、心跳和 fencing 使用 PostgreSQL。`/health/ready` 当前检查 PostgreSQL 迁移版本；本地链配置与实例在执行身份操作时核验，不能把基础 readiness 当完整链路就绪。注册仅创建未核验候选，不代表测试通过。

容器启动（需可用 Docker Linux 引擎）：

先完成上面的工具安装、`uv sync` 和 `init_local.py`。基础 Docker 流程不启动原生 PostgreSQL/API/Anvil；停止占用 8000、5173、8545 的原生演示服务。

```powershell
$env:LOCAL_RPC_URL = "http://127.0.0.1:8545"
$env:FIXTURE_PORT_A = "9101"
$env:FIXTURE_PORT_D = "9102"
$env:CODE_VERSION = (git rev-parse HEAD).Trim()
if (git status --porcelain) { $env:CODE_VERSION += "-dirty" }
docker compose config --quiet
docker compose build
docker compose up -d --wait anvil
. ./scripts/tools.ps1
forge build --root contracts
```

在已运行的 Compose Anvil 上部署、seed 并生成新容器配置：

```powershell
$env:FIXTURE_HOST_A = "fixture-a"
$env:FIXTURE_HOST_D = "fixture-d"
uv run --env-file .env --all-packages reputation deploy-local --runtime-dir runtime/compose-host
uv run --env-file .env --all-packages reputation seed --runtime-dir runtime/compose-host
uv run --all-packages python scripts/prepare_compose_runtime.py --source runtime/compose-host --output runtime/compose-chain
docker compose up -d --wait
docker compose ps
```

Compose uses an internal `anvil:8545` endpoint. The preparation script verifies the host Anvil genesis, deployed bytecode, seeded fixture hosts/ports, and publisher address before writing four read-only config files with that RPC URL. The host deployment and ledgers remain unchanged. API and worker share the named evidence volume at `/app/artifacts/evidence`; A/D each use a separate named ledger volume, so their read-only config mounts never receive SQLite writes. The runtime directory is ignored and must never be copied into a release bundle.

运行完整容器演示 smoke，操作者保留使用原始宿主目录及回环 RPC：

```powershell
$env:LOCAL_RUNTIME_DIR = Join-Path (Get-Location) 'runtime/compose-host'
uv run --env-file .env --all-packages python scripts/smoke_runtime.py
uv run --env-file .env --all-packages python scripts/smoke_verification.py
uv run --env-file .env --all-packages python scripts/smoke_reports.py
uv run --env-file .env --all-packages python scripts/smoke_m1.py
```

依次要求真实 A PASS、D 成功 receipt 但 `TASK_ID_MISMATCH` / `RECORD_HASH_MISMATCH`、稳定报告 ZIP、A/D 本地报告锚定、离线/受信 RPC 独立复核以及篡改拒绝。API 只挂载公共 deployment 配置，worker 额外挂载自己的 publisher 密钥，fixture 各只获得自身配置；setup owner/admin 密钥保留在宿主操作者目录。`CODE_VERSION` 必须匹配实际构建源码，dirty 版本不能当作已验收 Release。源码 ZIP 部署使用交付 manifest 的真实 commit，见 [比赛交付](COMPETITION_DELIVERY.md)。

`prepare_compose_runtime.py` 拒绝已有输出；后续链实例用新的 host/output 目录，并设置 `$env:COMPOSE_RUNTIME_DIR` 为新输出目录。Anvil 容器当前使用内存链，停止/重建会丢失链状态；数据库、证据和 fixture named volumes 默认保留。新一轮完整实例用新的 `$env:COMPOSE_PROJECT_NAME` 隔离这些卷，保留原目录和旧卷用于审计，不删除旧账本来修复实例冲突。

API `http://127.0.0.1:8000`，前端 `http://127.0.0.1:5173`，Anvil 使用 `LOCAL_RPC_URL`（默认 `http://127.0.0.1:8545`）。先停止占用同端口的原生进程。数据库不映射宿主端口；control/demo 两个内部网络；fixture 只进入 demo。需宿主入口的 API/web/Anvil 另接 ingress bridge（见 ADR 0003）。API 没有签名密钥，worker 不继承 operator token。公网业务出口没有启用。

停止使用 `docker compose down`，默认保留数据卷；不要为排错使用 `down -v`。原生数据库使用 `uv run --all-packages python scripts/local_postgres.py stop`。

本机 Docker Desktop 4.93.0 已按用户安装，但首次 WSL 导入报 `Wsl/ERROR_PATH_NOT_FOUND`，尚未获得本机 Compose 运行结果。没有重置或注销已有 WSL 发行版。原生 PostgreSQL/API/worker 已通过；历史 Linux CI run 37017699537 的旧版 Compose 构建/迁移/运行/HTTP/RPC smoke 已通过。本次完整 A/D/报告/anchor Compose 流程在本机为 NOT_RUN，须由更新后的 required CI 验证，不能沿用历史成功当作本次验收。

## M1 本地合约与受控服务

启动独立回环开发链：

```powershell
. ./scripts/tools.ps1
$anvilPort = if ($env:LOCAL_RPC_URL) { ([uri]$env:LOCAL_RPC_URL).Port } else { 8545 }
anvil --host 127.0.0.1 --port $anvilPort --chain-id 31337 --silent
```

另开终端，在仓库根目录：

```powershell
. ./scripts/tools.ps1
forge build --root contracts
uv run --env-file .env --all-packages reputation deploy-local
uv run --env-file .env --all-packages reputation seed
```

密钥与各服务账本位于忽略的 `runtime/local-chain`，不得提交、分享或配置公网 RPC。重复 deploy/seed 查询已部署实例和旧交易，不重复注册；链 reset 后命令拒绝旧配置，保留旧目录。新实例使用 `reputation deploy-local --runtime-dir runtime/local-chain-v2`，再用相同参数运行 `reputation seed`，并把服务 FIXTURE_CONFIG 指向该目录。不能用删除旧账本来“修复”重放。

分别在两个终端启动 A/D：

```powershell
. ./scripts/tools.ps1
$env:FIXTURE_CONFIG = Join-Path (Get-Location) 'runtime/local-chain/fixture-a.json'
$fixturePortA = if ($env:FIXTURE_PORT_A) { [int]$env:FIXTURE_PORT_A } else { 9101 }
uv run --env-file .env --all-packages uvicorn fixture_agents.service:create_app --factory --host 127.0.0.1 --port $fixturePortA --no-access-log
```

D 使用 `fixture-d.json`，并以同样方式从 `FIXTURE_PORT_D` 读取端口（默认 9102）。每服务默认一个进程，由独立 SQLite 账本持久化；平台不会读取异常模式。

`uv run --env-file .env --all-packages python scripts/smoke_agents.py` 验证真实 HTTP、A 匹配事件、D 无关成功事件。重启 A/D 后运行同命令加 `--recheck`，要求旧 request 返回原 txHash，无重复记录。该命令使用 synthetic snapshot，是协议 smoke；完整身份绑定、平台 worker、报告和复核按上面的完整 smoke 顺序运行。Compose fixture 使用内部网络，协议 smoke 的宿主直连方式用于原生运行。

## M1 快照与双签绑定

完成 deploy/seed，启动新版 API 和独立 worker 后运行：

```powershell
uv run --env-file .env --all-packages python scripts/smoke_identity.py
```

该本地操作者脚本从忽略的 `.env` 获取 token，从 `setup-secrets.json` 获取演示 owner/executor 密钥，在客户端分别签署两个角色的 EIP-712 消息。私钥不会发送给 API/worker。它依次调用注册、异步 refresh、人工确认映射、challenge、verify，输出 `IDENTITY_SMOKE_PASS`，公共结果保存为 `runtime/local-chain/identity-smoke.json`。A/D 的身份都应 VERIFIED；D 的任务正确性仍需后续独立断言，不能从绑定结果推断。

平台默认读取 `runtime/local-chain/deployment.json`；使用新实例目录时，为 API 和 worker 设置 `LOCAL_CHAIN_CONFIG` 为相应公共配置的绝对路径。`EVIDENCE_ROOT` 可指定脱敏证据目录，默认 `runtime/evidence`。API 和 worker 必须使用相同配置与证据目录；API 不读取私钥，worker 的本地 anchor publisher 仅读取 `PUBLISHER_SECRET_PATH` 指定的 evaluator 密钥，均不读取 setup owner/admin 密钥。操作者 smoke 用 `LOCAL_RUNTIME_DIR` 指定同一实例的宿主目录。

refresh 每次追加新快照，旧快照可读，但不用于新的声明确认或绑定；新版本需要重新确认和签名。双签仅支持本地 EOA，合约账户为 UNKNOWN。注册文件只接受受控结构；公网注册文件抓取尚未开启。

## M1 授权与任务发送

在新版 API、独立 worker、A/D 服务都启动后运行：

```powershell
uv run --env-file .env --all-packages python scripts/smoke_execution.py
```

脚本先重新执行 identity smoke 获得有效期内的绑定，然后为 A/D 各创建一次受限授权和一个功能槽位，等待独立 worker 保存候选交易，结果写入 `runtime/local-chain/execution-smoke.json`。`DISPATCH_SMOKE_PASS` 只证明调用和恢复管道跑通，不能当作 Agent 业务 PASS；独立断言与报告分别由下述 verification/reports smoke 核对。

新 API 支持 access-grants 创建/读取/撤销、带 Idempotency-Key 的 evaluations 创建、plan/observations/state 读取及 cancel。M1 grant 的方法、路径、能力、链和合约由服务器固定到最小受控范围；响应中返回完整授权。重复按钮沿用同一个 key；修改请求时使用新 key。一个 Agent 同时一个 active run，授权额度按已冻结槽位预留，不因取消退回。

执行与验证测试会启动独立 Agent 占用 `FIXTURE_PORT_A`/`FIXTURE_PORT_D`（默认 9101/9102），因此跑全量 pytest 前先停止 demo A/D，完成后按上面的 fixture-a/d 命令重启。测试不会自动杀掉端口占用者，也不会操作开发数据库；其 PostgreSQL/Anvil/Agent ledger 均隔离。其他终端可继续运行 API/worker。

## 独立业务核验

新版 API/worker 与 A/D 启动后运行 `uv run --env-file .env --all-packages python scripts/smoke_verification.py`。它会创建新快照、绑定和计划，等待独立 RPC 采集及纯规则核验；要求 A PASS、D receipt.success PASS 但 TASK_ID_MISMATCH/RECORD_HASH_MISMATCH，并输出 VERIFICATION_SMOKE_PASS。结果保存到忽略的 runtime/local-chain/verification-smoke.json。

核验接口为 GET /api/v1/evaluations/{run_id}/verification，未完成返回 404 NOT_VERIFIED。旧计划缺 target_code_hash 时不能追填，应另建新计划。当前核验结果不等于报告、存证或独立 bundle verifier 完成。

## 冻结报告与 ZIP 导出

新版 worker 在 verify 提交后自动排入 report 作业；旧的已核验 run 可通过认证 POST /api/v1/evaluations/{run_id}/report 入队。GET 同一路径读取报告，GET /api/v1/reports/{report_id}/bundle 导出 ZIP。没有客户端评分入口，所有统计来自冻结的任务证据。

运行 `uv run --env-file .env --all-packages python scripts/smoke_reports.py`：存在 verification-smoke.json 时复用最近的 A/D run，否则先执行真实核验 smoke。脚本等待报告 worker，校验 PARTIAL/overall=null 与 D 关键冲突，重复下载检查稳定字节，保存 report-a.zip、report-d.zip、report-smoke.json。脚本要求尚未发布的 NOT_REQUESTED 回执，紧接运行 `smoke_m1.py` 发布 A/D 并进行独立复核；已锚定报告不要重复运行要求未发布状态的 smoke。

每个发布者/Agent/链/合约同一时间只允许一个尚未接入链头的新冻结报告。已有未发布报告时应继续处理原报告；不要反复创建新 run 绕过 previous 约束。RPC 不可读会阻止安全冻结并保留平台错误；链上证据变更需新评价，旧报告不能改写。

报告文件、Schema 和原始证据从冻结 CAS 导出，不会因后续修改项目 Schema 文件而改变旧 ZIP。代码版本来自实际 Git SHA，未提交改动标 -dirty；无 Git 的部署需设置真实 CODE_VERSION。anchor_receipt 不在 report_core 摘要中。导出成功仅证明文件承诺已生成，不代表独立 verifier 或链上锚定已通过。
