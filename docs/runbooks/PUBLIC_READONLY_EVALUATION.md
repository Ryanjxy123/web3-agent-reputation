# 正式公共只读评价复现

此 runbook 对应 [ADR 0021](../adr/0021-public-readonly-evaluation.md) 和
`scripts/public_readonly_evaluation_smoke.py`。它运行五个真实的 Akashi 免费
`verify_record` 查询：四个 HTTP 查询（历史正例、重复可用性、随机 hash、非法
hash）和一个 MCP 历史正例。它不会调用 `/anchor`、签名、付款或向 Base 主网写入。

## 前置条件

- 使用本地 PostgreSQL；脚本会创建一个唯一数据库并保留它和 CAS 证据以便复核。
  `DATABASE_URL` 的主机必须是 `localhost`、`127.0.0.1`、`::1` 或 Compose 的
  `postgres`。
- 准备本地 Anvil 配置，默认 RPC 是 `.env.example` 中的
  `LOCAL_RPC_URL=http://127.0.0.1:8545`。部署实例、chain id、合约地址和 ABI
  必须来自当前本地 Anvil；不要把主网 RPC 或私钥放入 Bundle。此流程的报告摘要
  默认不请求 anchor，Verifier 对本地 publication 只报告 `UNANCHORED`。
- 设置至少 32 个字符的本地 `OPERATOR_TOKEN`，并显式打开
  `PUBLIC_READONLY_ENABLED=1`。公网默认关闭；完成后恢复为 `0`。
- 工作树、依赖和 DNS/TLS 配置应已按项目 runbook 初始化。输出目录必须是新的，
  脚本拒绝覆盖已有目录。

## 运行

```powershell
. .\scripts\tools.ps1
$env:PUBLIC_READONLY_ENABLED = "1"
$env:OPERATOR_TOKEN = "<local-random-token>"
$env:DATABASE_URL = "postgresql://<user>:<password>@127.0.0.1:5432/<db>"
$env:LOCAL_RPC_URL = "http://127.0.0.1:8545"
uv run --all-packages python scripts/public_readonly_evaluation_smoke.py `
  --allow-public-readonly `
  --output runtime/task10-public-readonly-$(Get-Date -Format yyyyMMdd-HHmmss) `
  --operator-dns-over-tls
```

`--operator-dns-over-tls` 使用固定的 `dns.google` DoT resolver，并把 DNS 审计原件
保存到输出目录；不传时使用系统 DNS，但仍执行私网、重定向、TLS、响应大小和付款
检查。每个 grant 只允许固定 endpoint、`verify_record`、串行请求和至少 1000ms
间隔，生命周期为一小时；evaluation API 随后创建固定五槽计划。撤销或过期会在
每次 socket 前重新检查并停止后续调用。

成功输出必须包含 `acceptance.json`、`public-readonly-bundle.zip`、CAS `blobs/`、
`network-audit.json` 和每阶段 `progress.json`。脚本会检查五个槽位、无付款、无签名、
无主网写入、`executor_outcome=UNKNOWN`，以及 `ReportCore 1.6.0` 的
`PARTIAL`/`overall_score_bp=null`。这些结果来自实际 Worker 和公开端点；单元测试
中的 MockTransport 或历史 CAS 回放不能代替本命令的真实运行。

## 独立复核与解释

```powershell
uv run --all-packages reputation-verify runtime/task10-public-readonly-<timestamp>/public-readonly-bundle.zip
```

不提供 `--rpc-url` 时，Verifier 只重新读取 Bundle 中的 CAS 原件，复算任务、断言、
统计、充分度、风险和评分，并检查重新计算的外层哈希；链上状态显示
`NOT_CHECKED`。Verifier 不读取 Bundle 内的 RPC 地址，也不会发起新的第三方请求。
这证明证据承诺和确定性判断可复核，不证明采集者诚实、历史 HTTP 响应真实性或实时
主网状态。只有在另行提供操作者信任的 RPC 时才做在线 anchor 检查；本公共只读流程
默认不 anchor。

失败时保留输出目录中的所有 CAS、进度和审计文件；不要删除或重写失败记录来制造
成功。若请求已发出但响应未持久化，恢复路径会冻结 `UNKNOWN/DISPATCH_UNCERTAIN`
并保留已保存原件，不自动重试补样本。样本未覆盖 policy-v1 的充分度门槛时，保持
`PARTIAL` 和空综合分；注册身份、端点关联、执行者控制和业务判断在报告中分别展示，
不能把公开注册的 owner、历史 payer 或任何占位地址当作 executor。
