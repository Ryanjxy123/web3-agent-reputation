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

另开终端运行 `uv run --all-packages reputation worker`。M0 worker 已验证领取、心跳和 fencing；业务 handler 在 M1 接入。`/health/ready` 检查 PostgreSQL 迁移版本；注册仅创建未核验候选，不代表测试通过。

容器启动（需可用 Docker Linux 引擎）：

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

API `http://127.0.0.1:8000`，前端 `http://127.0.0.1:5173`，Anvil `http://127.0.0.1:8545`。先停止占用同端口的原生进程。数据库不映射宿主端口；control/demo 两个内部网络；fixture 只进入 demo。API 没有签名密钥，worker 不继承 operator token。公网出口没有启用。

停止使用 `docker compose down`，默认保留数据卷；不要为排错使用 `down -v`。原生数据库使用 `uv run --all-packages python scripts/local_postgres.py stop`。

本机 Docker Desktop 4.93.0 已按用户安装，但首次 WSL 导入报 `Wsl/ERROR_PATH_NOT_FOUND`，尚未获得本机 Compose 运行结果。没有重置或注销已有 WSL 发行版。原生 PostgreSQL/API/worker 测试与 Compose 配置解析已通过；不能把配置通过当容器已启动。
