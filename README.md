# web3-agent-reputation
Multi-source evidence based reputation evaluation platform for Web3 Agents.

面向链上凭证查询、核验与存证 Agent 的任务级证据评价平台。

main 已包含 M0/M1 和后续任务 1–10：三能力任务、四态归因、三维评分、充分度与关键风险、冻结证据包与独立复核、受控故障、HTTPS/MCP 免费只读适配、ERC-8004 身份关联和真实第三方评价闭环。任务 11 正式 v2 对照实验已完成独立 Review 并提交验收；任务 12 前端与任务 13 最终交付仍在进行。未完成最终回归和 required CI 前不发布正式 Release。执行计划见 [PLAN.md](PLAN.md)，实际运行、Review 与交付状态见 [STATUS.md](docs/implementation/STATUS.md)。

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

ERC-8004 注册身份、端点关联、执行者控制与本项目业务测评结论分别记录。基础演示使用本地测试链，不涉及真实资产。少量样本只生成部分评价，不降低 policy-v1 的 20/10/10 门槛；成功交易必须与当前任务独立关联。公共调用默认关闭，只允许明确授权的免费只读范围；真实 Akashi 历史验收为 4 PASS / 1 UNKNOWN，保持 PARTIAL、overall=null、executor UNKNOWN、UNANCHORED。该样本不证明长期表现或未知 hash 全链不存在。

评价包含服务可用性 A、功能声明一致性 B、交易行为可靠性 T；写入画像使用 `0.30A + 0.40B + 0.30T`，只读画像使用 `0.35A + 0.65B`，T 为 NOT_APPLICABLE。充分度 Q 是覆盖、样本量和时效的最低值；所有适用维度满足充分度、覆盖与归因门槛才输出综合分。已有确定关键冲突在 PARTIAL 中仍保留风险提示。完整公式、分母与边界见 [评价规则](docs/specs/EVALUATION.md)；技术评价不是主体诚信或未来安全保证。

## 当前可运行的工作空间

Windows PowerShell，从仓库根目录执行（工具安装只写入 Git 忽略的 runtime/tools）：

```powershell
. ./scripts/tools.ps1 -Install
uv sync --locked --all-packages
uv run --all-packages python scripts/init_local.py
uv run --all-packages python scripts/local_postgres.py init
uv run --all-packages python scripts/local_postgres.py start
uv run --all-packages reputation migrate
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web exec playwright install chromium
uv run --all-packages python scripts/check.py
uv run --package reputation-platform reputation doctor
```

doctor 会明确报告未就绪工具并返回非零；它不代表完整平台已启动。Python 使用 3.12（当前验证 3.12.4），Node 22.17.0，pnpm 10.12.4。运行环境与依赖版本见 configs/toolchain.json 和锁文件。

PostgreSQL 在项目 runtime 中运行，仅监听 127.0.0.1:55432；凭证自动随机生成并被 Git 忽略。Windows 原生 PostgreSQL 对中文路径存在启动编码问题，脚本在项目所在盘根目录创建 `web3-runtime` 目录联接（本机 `D:\web3-runtime`），指向同一 runtime，不复制或移动文件，也不创建额外盘符。已有同名路径指向其他目录时会拒绝启动，不覆盖它。停止数据库使用 `uv run --all-packages python scripts/local_postgres.py stop`。测试只创建并删除自身的 reputation_test_* 临时数据库，不清空开发数据库。仅离线单元检查可运行 `uv run --all-packages pytest tests/unit tests/reference`，不能作为完整数据库验收。

领域类型生成：`uv run --all-packages python scripts/generate_schemas.py`、`pnpm --dir apps/web generate:types`。类型检查：`uv run --all-packages mypy -p reputation_core -p reputation_platform -p reputation_verifier -p fixture_agents`。

完整基础检查：`uv run --all-packages python scripts/check.py`，包含真实数据库集成、Schema/TS 漂移、前端和 Foundry；缺少依赖或跳过测试会失败。`check_bootstrap.py` 只检启动参考，不能替代该命令。

API、独立 worker、前端、本地部署/seed/A/D 服务的启动命令见 [本地运行](docs/runbooks/LOCAL_RUNTIME.md)，完整现场顺序和多 runtime 配置见 [演示 runbook](docs/runbooks/DEMO_AND_RELEASE.md)。Docker 镜像已固定 digest；本机 WSL 导入故障与历史 Linux CI 结果分别记录在 STATUS，本次完整 Compose 演示仍须由更新后的 required CI 验证。全量 pytest 使用受控端口 9101/9102，先停止 demo A/D，测试完成后再启动。Linux 浏览器测试先执行 `pnpm --dir apps/web exec playwright install --with-deps chromium` 安装 Chromium 及系统依赖。

完成本地核验后运行 `uv run --env-file .env --all-packages python scripts/smoke_reports.py`，再运行 `uv run --env-file .env --all-packages python scripts/smoke_m1.py` 完成本地报告锚定和独立复核。独立 CLI 为 `uv run --all-packages reputation-verify <bundle.zip> [--rpc-url <trusted-rpc>]`；不提供 RPC 时链上状态为 `NOT_CHECKED`，离线通过只证明冻结包内部一致性。两份 smoke 报告的 overall_score_bp 均为 null。

免费第三方流程见 [公共只读评价](docs/runbooks/PUBLIC_READONLY_EVALUATION.md)。正式交付需按 [比赛交付检查](docs/runbooks/COMPETITION_DELIVERY.md) 核对官方规则、最终测试记录、许可与匿名要求。`scripts/package_delivery.py` 使用 `git archive` 导出指定 commit 的公共源码和 SHA-256/许可清单，排除本地未提交 runtime；生成包不代表已通过验收或已发布 Release。

## 正式对照实验

[Task 11 正式 v2 报告](docs/testing/experiments/task11/formal-20261012-three-repeats-v2/analysis/report.md) 来自 12 场景 × 3 次真实 PostgreSQL/HTTP Agent/Anvil/Worker 执行，共 36 任务。共同写任务上的已知错误 Recall 为在线检测 0、receipt 检测 0、完整任务核验 1；完整核验保留 6 PASS / 15 FAIL / 12 UNKNOWN / 3 N/A。Bundle 判定/原因复核一致性为 36/36，风险一致性为 33/33，另 3 份旧版 N/A 报告无风险评估。结果只适用于这些受控场景，不表示生产准确率。原始产物、精确源码快照、方法分母和离线复现命令见 [实验说明](docs/testing/experiments/task11/README.md)，独立审查见 [Review](docs/testing/experiments/task11/REVIEW.md)。
