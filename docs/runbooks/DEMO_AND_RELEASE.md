# 本地演示与交付运行

main 已实现 M0/M1 与后续任务 1–10。任务 11 正式 v2 对照实验已独立 Review 并提交验收；任务 12 前端完善与任务 13 最终验收仍在进行。以下使用已有真实 API、worker、PostgreSQL 和 Anvil 命令，运行证据见 [任务 11–13 验收记录](../testing/TASKS11_13_ACCEPTANCE.md)；失败退出码不能伪装成功。

## 1. 环境初始化与完整新成员路线
先执行 [LOCAL_RUNTIME.md](LOCAL_RUNTIME.md) 的初始化、原生 PostgreSQL、Anvil、合约部署/seed、API、worker、A/D 和前端启动。`scripts/init_local.py` 创建随机 token 并保留现有键；不要把 `.env.example` 的空键复制成 `.env` 后误认为已有随机凭证。API 使用 `uvicorn reputation_platform.api.app:create_app --factory`，worker 使用 `reputation worker`，前端使用 `pnpm --dir apps/web dev --port 5173`；没有 `reputation api` 或 `scripts/dev.ps1` 入口。

每个 Python 服务命令都使用 `uv run --env-file .env --all-packages ...`；API/worker 必须加载相同数据库、部署配置和 evidence 目录。`reputation doctor` 只检查工具/包，明确输出 `runtime_checks=NOT_RUN`，不能当作链实例或端口已验证。服务健康用 `smoke_runtime.py`，迁移失败不启动 worker。

## 2. 部署与seed幂等
部署配置保存 chain_id、genesis、deployment_instance_id、合约地址/代码摘要和部署交易/区块；复用前重新校验 bytecode/实例，而不只看本地文件存在。报告另记录实际源码版本；ABI 随锁定源码交付。
检测Anvil重置时停止使用旧地址，提示显式deploy/reseed；不把旧报告删除或说链上记录仍有效。
seed重复不会重复注册或业务写入；固定fixture标识与ledger状态有映射。随机任务输入不是所有run共享一个固定request。
seed不读取业务真实材料、不使用主网、不向公网发布Anvil默认私钥。

## 3. 最小演示
A与D都声明可存证。展示相同业务类型、不同随机request/input→A真实业务事件吻合→D receipt成功但request/摘要不符→查看逐项断言→导出报告→真实anchor→独立验证→修改副本后拒绝。
首轮样本少，显示 PARTIAL、overall=null 是 policy-v1 的预期行为。正式多槽位三能力评分和充分度已实现；现有 M1 smoke 仍只使用少样本，不能将它描述为满足 20/10/10 门槛的完整声誉。

```powershell
uv run --env-file .env --all-packages python scripts/smoke_runtime.py
uv run --env-file .env --all-packages python scripts/smoke_verification.py
uv run --env-file .env --all-packages python scripts/smoke_reports.py
uv run --env-file .env --all-packages python scripts/smoke_m1.py
```

`smoke_verification.py` 已调用 identity 与 execution smoke，无需另外重复运行。演示时从 smoke 结果读取实际 Agent/Run UUID，然后在前端查看身份、逐项断言、报告和证据；不手写演示数据。首次核验/报告失败时保留 runtime 和日志。

## 3.1 发布与独立复核

在 `smoke_reports.py` 生成两份未发布 bundle 后运行 `smoke_m1.py`。脚本将 A/D 报告分别排入本地 anchor 作业，worker 先持久化 nonce 和 signed transaction，再广播 `EvaluationAnchor.anchorReport`；随后做离线重算、可信 RPC 在线复核，并验证修改 bundle 会失败。D 的锚定只承诺原业务 FAIL 报告，不能把它改成 PASS。

独立复核命令：

```powershell
uv run --all-packages reputation-verify runtime/local-chain/report-a.zip
uv run --all-packages reputation-verify runtime/local-chain/report-a.zip --rpc-url http://127.0.0.1:8545
```

第一条命令只证明 bundle 内部一致性，anchor 为 `NOT_CHECKED`；第二条命令只使用操作者提供的 RPC，成功时报告 `CONFIRMED`。Verifier 不读取 ZIP 内的 RPC 地址。
A/D 是受控测试代理，不声称商业 Agent；公共 ERC-8004 身份与业务评价分开，历史回放单独标记。8004scan OpenAPI 的历史 HTTP 403 不等于已完成发现接入。

## 3.2 保留旧实例并重新演示

链 reset 后不得沿用旧部署文件或删除旧账本。新实例使用新 runtime，并在 API、worker 和 smoke 所有终端中设置以下变量，再重启 API/worker：

```powershell
$env:LOCAL_RUNTIME_DIR = Join-Path (Get-Location) 'runtime/local-chain-v2'
$env:LOCAL_CHAIN_CONFIG = Join-Path $env:LOCAL_RUNTIME_DIR 'deployment.json'
$env:PUBLISHER_SECRET_PATH = Join-Path $env:LOCAL_RUNTIME_DIR 'publisher-secret.json'
uv run --env-file .env --all-packages reputation deploy-local --runtime-dir runtime/local-chain-v2
uv run --env-file .env --all-packages reputation seed --runtime-dir runtime/local-chain-v2
```

A/D 终端分别将 `FIXTURE_CONFIG` 改为 `Join-Path $env:LOCAL_RUNTIME_DIR 'fixture-a.json'` / `'fixture-d.json'`，独立 verifier 使用 `runtime/local-chain-v2/report-a.zip`。`LOCAL_RUNTIME_DIR` 是 smoke 目录，`--runtime-dir` 是部署/seed 参数，`LOCAL_CHAIN_CONFIG` 是 API/worker 配置，不能只改其中一个。旧报告已发布时不要重新导出覆盖；后续轮次使用新的目录/实例名。

## 4. 完整演示与实验
受控故障覆盖正常、低可用性、夸大能力、任务不匹配、身份/版本/绑定异常和合法只读 NA。写入与只读画像分开；既有黄金算例和真实 fixture/Anvil 用于测试，不在现场硬编码分数。

公共流程按 [PUBLIC_READONLY_EVALUATION.md](PUBLIC_READONLY_EVALUATION.md) 单独启用，只允许免费、授权、低频、静态白名单 HTTPS/MCP 和可信 RPC 只读，不付款、不签名、不向主网写入。真实历史验收 4 PASS / 1 UNKNOWN、PARTIAL、overall=null、executor UNKNOWN、UNANCHORED 必须如实展示；公开 owner、历史 payer 和端点关联不能冒充 executor 绑定。网络或第三方不可用时保留失败/UNKNOWN，本地 A/D 核心演示不依赖公网。

任务 11 使用已验收的 [正式 v2 报告](../testing/experiments/task11/formal-20261012-three-repeats-v2/analysis/report.md)、[原始产物与复现说明](../testing/experiments/task11/README.md) 和 [独立 Review](../testing/experiments/task11/REVIEW.md)。现场打开图表与各任务行，说明共同写任务 Recall 为 0/0/1、UNKNOWN 为证据不足、receipt 对只读为 N/A，并展示任务匹配断言；不修改冻结结果或把受控场景比例说成生产准确率。任务 12 页面/交互状态以实际 API 与测试为准。

## 5. 备份与复現
备份PostgreSQL、evidence blobs、fixture ledger、受信部署配置；密钥另用受控安全方式，不放公开包。
报告包本身足以离线重算，但不能重建整个运行环境或证明链下真实调用；复現整个实验还需固定代码、容器/依赖锁、规则、数据集和运行配置。
本地链可重置；公开复核需受信外部链与最终性假设。恢复后由部署/身份流程重新核对 instance，不能沿用旧 chain 状态；doctor 的工具检查不能替代这一步。

## 6. 发布
clean主分支commit通过ACCEPTANCE后才tag；生成版本、变更、许可、完整性清单与已知问题。
竞赛提交目录与Git开发仓库分开，生成匿名副本时排除.git、用户路径、学校/队员/导师信息、remoteURL和屏幕账号，保留必要第三方许可来源；匿名细则以负责人重新核对官方要求为准。
不改写Git历史来匿名，不删除运行失败记录，不把规划当实际测试报告。

指定 commit 的源码打包、官方材料核查、许可清单和软件 Release gate 见 [COMPETITION_DELIVERY.md](COMPETITION_DELIVERY.md)。完成软件验收与 required CI 后按用户授权发布 Release，并披露赛事规则、匿名和第一方许可未核实的限制；正式赛事提交另核对官方清单。源码包不包含未提交 runtime，也不自动满足匿名或最终软件验收。
