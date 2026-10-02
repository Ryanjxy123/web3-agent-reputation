# web3-agent-reputation
Multi-source evidence based reputation evaluation platform for Web3 Agents.

面向链上凭证查询、核验与存证 Agent 的任务级证据评价平台。

当前 M0 已通过，M1 已有本地真实任务核验与部分报告；存证、独立 ZIP 复核及完整端到端验收仍在实现。执行计划见 [PLAN.md](PLAN.md)，真实进度见 [STATUS.md](docs/implementation/STATUS.md)。

## 已有检查

从仓库根目录执行：

```powershell
python scripts/check_bootstrap.py
python scripts/git_doctor.py
```

前者验证评分参考、配置和算例；后者只读检查 Git。通过这些检查不代表 API、数据库、合约或端到端验收通过。

## 开发入口

阅读 [AGENTS.md](AGENTS.md)、[任务卡](docs/implementation/BACKLOG.md)、[Windows/Git runbook](docs/runbooks/WINDOWS_AND_GIT.md)。其他规格见 [文档导航](docs/README.md)。

## 产品边界

ERC-8004 身份、8004scan 发现与本项目测评结论分开记录。基础版使用本地测试链，不涉及真实资产。少量样本只生成部分评价，不降低 policy-v1 的 20/10/10 门槛；成功交易必须与当前任务独立关联。技术评价不是主体诚信或未来安全保证。

## 当前可运行的工作空间

Windows PowerShell，从仓库根目录执行（工具安装只写入 Git 忽略的 runtime/tools）：

```powershell
. ./scripts/tools.ps1 -Install
uv sync --locked --all-packages
uv run --all-packages python scripts/local_postgres.py init
uv run --all-packages python scripts/local_postgres.py start
uv run --all-packages reputation migrate
uv run --all-packages pytest
uv run ruff check packages services fixtures/agents tests/unit
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web build
pnpm --dir apps/web test
forge build --root contracts
forge test --root contracts
uv run --package reputation-platform reputation doctor
```

doctor 会明确报告未就绪工具并返回非零；它不代表完整平台已启动。Python 使用 3.12（当前验证 3.12.4），Node 22.17.0，pnpm 10.12.4。运行环境与依赖版本见 configs/toolchain.json 和锁文件。

PostgreSQL 在项目 runtime 中运行，仅监听 127.0.0.1:55432；凭证自动随机生成并被 Git 忽略。Windows 原生 PostgreSQL 对中文路径存在启动编码问题，脚本将同一 runtime 动态映射到空闲盘符，不复制项目。运行期间保留该映射；停止数据库使用 `uv run --all-packages python scripts/local_postgres.py stop`。测试只创建并删除自身的 reputation_test_* 临时数据库，不清空开发数据库。仅离线单元检查可运行 `uv run --all-packages pytest tests/unit tests/reference`，不能作为完整数据库验收。

领域类型生成：`uv run --all-packages python scripts/generate_schemas.py`、`pnpm --dir apps/web generate:types`。类型检查：`uv run --all-packages mypy -p reputation_core -p reputation_platform -p reputation_verifier -p fixture_agents`。

完整基础检查：`uv run --all-packages python scripts/check.py`，包含真实数据库集成、Schema/TS 漂移、前端和 Foundry；缺少依赖或跳过测试会失败。`check_bootstrap.py` 只检启动参考，不能替代该命令。

API、独立 worker、Vue 连接页以及本地部署/seed/A/D 服务的启动命令见 [本地运行](docs/runbooks/LOCAL_RUNTIME.md)。Docker 镜像已固定 digest；本机 WSL 导入故障和 Linux CI 实测结果分别记录在 STATUS，不能互相冒充。已有合约、持久 A/D、快照双签、授权与发送恢复、独立业务断言及不可变 PARTIAL 报告 ZIP；存证和独立复核仍待完成，各阶段 smoke 不是完整 M1 验收。全量 pytest 使用受控端口 9101/9102，先停止 demo A/D，测试完成后再启动。

完成本地核验后运行 `uv run --all-packages python scripts/smoke_reports.py`，通过 API/worker 为最近的 A/D 任务生成或读取冻结报告，ZIP 保存到忽略的 runtime/local-chain。两份报告的 overall_score_bp 均为 null；未发布时回执为 NOT_REQUESTED，不能称链上存证已完成。
