# 本地基础运行

在仓库根目录执行；随机凭证只存 `.env` 和 `runtime/local-db.json`，不提交或打印。

Windows 原生基础环境（含中文路径验证）：

```powershell
. ./scripts/tools.ps1 -Install
uv sync --locked --all-packages
uv run --all-packages python scripts/init_local.py
uv run --all-packages python scripts/local_postgres.py init
uv run --all-packages python scripts/local_postgres.py start
uv run --all-packages reputation migrate
uv run --env-file .env --all-packages uvicorn reputation_platform.api.app:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

另开终端运行 `uv run --all-packages reputation worker`。worker 已接入 ingest handler；领取、心跳和 fencing 使用 PostgreSQL。`/health/ready` 当前检查 PostgreSQL 迁移版本；本地链配置与实例在执行身份操作时核验，不能把基础 readiness 当完整链路就绪。注册仅创建未核验候选，不代表测试通过。

容器启动（需可用 Docker Linux 引擎）：

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

API `http://127.0.0.1:8000`，前端 `http://127.0.0.1:5173`，Anvil `http://127.0.0.1:8545`。先停止占用同端口的原生进程。数据库不映射宿主端口；control/demo 两个内部网络；fixture 只进入 demo。需宿主入口的 API/web/Anvil 另接 ingress bridge（见 ADR 0003）。API 没有签名密钥，worker 不继承 operator token。公网业务出口没有启用。

停止使用 `docker compose down`，默认保留数据卷；不要为排错使用 `down -v`。原生数据库使用 `uv run --all-packages python scripts/local_postgres.py stop`。

本机 Docker Desktop 4.93.0 已按用户安装，但首次 WSL 导入报 `Wsl/ERROR_PATH_NOT_FOUND`，尚未获得本机 Compose 运行结果。没有重置或注销已有 WSL 发行版。原生 PostgreSQL/API/worker 已通过；Linux CI run 37017699537 的真实 Compose 构建/迁移/运行/HTTP/RPC smoke 已通过。两种环境的结果分别记录。

## M1 本地合约与受控服务

启动独立回环开发链：

```powershell
. ./scripts/tools.ps1
anvil --host 127.0.0.1 --port 8545 --chain-id 31337 --silent
```

另开终端，在仓库根目录：

```powershell
. ./scripts/tools.ps1
forge build --root contracts
uv run --all-packages reputation deploy-local
uv run --all-packages reputation seed
```

密钥与各服务账本位于忽略的 `runtime/local-chain`，不得提交、分享或配置公网 RPC。重复 deploy/seed 查询已部署实例和旧交易，不重复注册；链 reset 后命令拒绝旧配置，保留旧目录。新实例使用 `reputation deploy-local --runtime-dir runtime/local-chain-v2`，再用相同参数运行 `reputation seed`，并把服务 FIXTURE_CONFIG 指向该目录。不能用删除旧账本来“修复”重放。

分别在两个终端启动 A/D：

```powershell
. ./scripts/tools.ps1
$env:FIXTURE_CONFIG = Join-Path (Get-Location) 'runtime/local-chain/fixture-a.json'
uv run --all-packages uvicorn fixture_agents.service:create_app --factory --host 127.0.0.1 --port 9101 --no-access-log
```

D 使用 `fixture-d.json` 和端口 9102。每服务默认一个进程，由独立 SQLite 账本持久化；平台不会读取异常模式。

`uv run --all-packages python scripts/smoke_agents.py` 验证真实 HTTP、A 匹配事件、D 无关成功事件。重启 A/D 后运行同命令加 `--recheck`，要求旧 request 返回原 txHash，无重复记录。该命令使用 synthetic snapshot，是协议 smoke；完整身份绑定、平台 worker、报告和复核由 M1 后续任务提供。当前 Compose 验证仅覆盖基础服务，fixture 编排在纵向集成阶段接入。

## M1 快照与双签绑定

完成 deploy/seed，启动新版 API 和独立 worker 后运行：

```powershell
uv run --all-packages python scripts/smoke_identity.py
```

该本地操作者脚本从忽略的 `.env` 获取 token，从 `setup-secrets.json` 获取演示 owner/executor 密钥，在客户端分别签署两个角色的 EIP-712 消息。私钥不会发送给 API/worker。它依次调用注册、异步 refresh、人工确认映射、challenge、verify，输出 `IDENTITY_SMOKE_PASS`，公共结果保存为 `runtime/local-chain/identity-smoke.json`。A/D 的身份都应 VERIFIED；D 的任务正确性仍需后续独立断言，不能从绑定结果推断。

平台默认读取 `runtime/local-chain/deployment.json`；使用新实例目录时，为 API 和 worker 设置 `LOCAL_CHAIN_CONFIG` 为相应公共配置的绝对路径。`EVIDENCE_ROOT` 可指定脱敏证据目录，默认 `runtime/evidence`。API 和 worker 必须使用相同配置与证据目录，均不读取 setup/publisher 私钥文件。操作者 smoke 当前使用默认本地目录；其他实例需显式按 API 流程签署。

refresh 每次追加新快照，旧快照可读，但不用于新的声明确认或绑定；新版本需要重新确认和签名。双签仅支持本地 EOA，合约账户为 UNKNOWN。注册文件只接受受控结构；公网注册文件抓取尚未开启。
