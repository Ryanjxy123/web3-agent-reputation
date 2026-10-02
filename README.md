# web3-agent-reputation
Multi-source evidence based reputation evaluation platform for Web3 Agents.

面向链上凭证查询、核验与存证 Agent 的任务级证据评价平台。

当前正在实现 M0/M1，尚不是已部署应用。执行计划见 [PLAN.md](PLAN.md)，真实进度见 [STATUS.md](docs/implementation/STATUS.md)。

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
