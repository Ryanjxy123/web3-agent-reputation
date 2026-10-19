# 独立提供方候选补查：delu 与 Clicks

日期：2026-10-18。本独立补查只阅读公开注册目录、作者源码与文档，未发业务或 RPC 请求。主任务随后已完成两身份的 7 次可信 Base 注册读取、Clicks 注册 JSON/MCP 文档的两次 GET，以及三次匿名 MCP 请求；分账预览遇到上游限额后停止。没有签名、付费或链上写入，也没有本补查新增模型调用或工程测试。两项均为后续核实线索，**新增完整评分对象为 0**。

原件：目录 `runtime/candidate-check-20261018T062321Z-d8029c93/`；注册实读 `runtime/base-registration-probe-20261018T062514Z-7cb4f595/`；Clicks 两份 HTTPS 文档 `runtime/candidate-check-20261018T062616Z-11c298de/`。后两批均退出 0。注册在 Base 固定块 **52757623** 读取，下述 owner 与 tokenURI 已由实读核实；目录衍生字段仍不作链事实。

## delu：有一条明确的历史交换声明，身份到交易尚未闭合

### 身份与资料出处

- 完整身份：`eip155:8453:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:30004`，即 Base #30004。已保存的 `catalog-delu.response.bin` 为 HTTP 200 原件；可信 Base 固定块 ownerOf/tokenURI 已读取成功。
- 目录记录 owner 为 `0xed2ceca9de162c4f2337d7c1ab44ee9c427709da`，creator 为 `0x6ffa1e00509d8b625c2f061d7db07893b37199bc`。`agent_wallet` 的字段来源是 `hardcoded`，原始 `agentWallet` 为空，不能用目录补值确定执行者。
- 链上 tokenURI 与目录中的 data URI 一致：描述是链上基础设施开发，`services=[]`，未列交易仪表盘或交易服务；ownerOf 也与目录 owner 一致。作者 [交易项目 README](https://github.com/deluagent/delu-agent/blob/835dc7372a074ba341fb8e9394878fab0044e4b9/README.md) 则自称同一 #30004、列出该 owner 钱包及仪表盘；这是作者提供的关联线索，尚非注册文件中的服务绑定。
- GitHub 当前 `main` 返回的 commit：交易仓库 `835dc7372a074ba341fb8e9394878fab0044e4b9`；网站仓库 `99bca8f86956a54ceaf9a2ec1cf3bcdee944177f`。没有运行或安装其代码。

### 可读原件、输入与输出

作者公开的 [trade_journal.jsonl](https://github.com/deluagent/delu-agent/blob/835dc7372a074ba341fb8e9394878fab0044e4b9/data/trade_journal.jsonl) 首条包含：Base、MOLT、买入、USDC 金额 `11.88`、代币合约 `0xb695559b26bb2c9703ef1935c37aeae9526bab07`、声称收到 `415414.84` 枚、时间 `2026-03-21T18:19:28.586Z`，交易线索：

`0xf7ffe9fb01996e309f0fd8731f1388938d6fbf310905eef827ad56fe2cffde70`

网站公开静态文件 [public/data/status.json](https://github.com/deluagent/delu-site/blob/99bca8f86956a54ceaf9a2ec1cf3bcdee944177f/public/data/status.json) 的 `reasoningTraces[0]` 还有上述交易对应的自然语言输入：兑换 11.88 USDC 为指定合约代币，并设置 5% stop loss；输出声称收到 `415,414.84 MOLT`。这是可用于独立核对的任务线索，不是本平台已核验的交换或止损成功。

匿名只读路径由作者 [网站 GET 路由](https://github.com/deluagent/delu-site/blob/99bca8f86956a54ceaf9a2ec1cf3bcdee944177f/app/api/status/route.ts) 明确实现：`https://deluagent.vercel.app/api/status`；静态文件可从 `https://deluagent.vercel.app/data/status.json` 读取。GET 无钱包、签名或支付要求。源码还提供本地 `/status`，没有据此假设存在另一个公网地址。**本轮未访问这两个业务路径。**

### 关键缺口与判据

1. 尚未取得交易/回执，不能确认钱包是实际 sender、智能账户 controller、交换 recipient，还是仅资金来源。Bankr 中继执行时更不能要求外层 `from` 必须等于钱包后就草率下结论。先明确账户授权及路由关系，再核对 USDC 流出、目标代币流入、事件发出合约、时间、精度、交易状态与确认数。
2. 不能把交易中的一次买入成功当作后续 5% 止损已设置或履行。后一项需要订单/委托原件及对应退出交易；目前缺失。
3. [网站 GET 源码](https://github.com/deluagent/delu-site/blob/99bca8f86956a54ceaf9a2ec1cf3bcdee944177f/app/api/status/route.ts) 最终分支明确返回 mock，且生成当前 `updatedAt`。中间分支也有固定市场值。HTTP 200 与新时间不足以证明后台还在运行。
4. 当前仓库静态快照更新时间为 `2026-04-17T10:29:58.141Z`，钱包总值为 0、positions/cycleHistory 为空，只保留一条 reasoning trace。journal 的大多数其余行缺 txHash，不能用无关联交易补齐任务数；`positions.json` 也不是逐次真实回执。

当前状态：**待身份/执行归属核验、待足量原始任务**。可考虑“历史兑换披露与执行”范围；不能评价整套策略、收益或实时状态。

## Clicks Protocol：注册关联较明确，远程只读查询与仓库新功能要分开

### 身份、合约与版本

- 完整身份：`eip155:8453:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:45074`。目录原件 `catalog-clicks.response.bin` 为 HTTP 200，owner/creator 均为 `0xf873bb73e10d24cd3cf9bbed917f5e2d07da8b80`；固定块 ownerOf 独立确认该 owner。tokenURI 明确指向 `https://clicksprotocol.xyz/.well-known/agent-registration.json`。
- 注册交易线索为 `0x76123d72379d35251c35747cbb8f43e09893d57501d9f4ba0f4e75d4aec296d6`。实际 HTTPS GET、目录原始文件与作者 [注册 JSON](https://github.com/clicks-protocol/clicks-protocol/blob/f6924036c15469b303d98666ccfc304adc6cd1f9/landing-v3/public/.well-known/agent-registration.json) 相符：`services` 使用 `type/url`，`agentRegistry` 是裸地址并另给 chainId。因此目录 `services={}` 及解析 warning **不能推出没有服务**。
- 作者 [部署清单](https://github.com/clicks-protocol/clicks-protocol/blob/f6924036c15469b303d98666ccfc304adc6cd1f9/deployments/base.json) 与注册文件给出 Base SplitterV4 `0xB7E0016d543bD443ED2A6f23d5008400255bf3C8`、ClicksRegistry `0x23bb0Ea69b2BD2e527D5DbA6093155A6E1D0C0a3`、YieldRouter `0x053167a233d18E05Bc65a8d5F3F8808782a3EECD`。
- 当前读取 commit 为 `f6924036c15469b303d98666ccfc304adc6cd1f9`。Safe 合约 owner、协议 operator、ACP 钱包是不同角色，不能把 Safe、deployer 或收款地址一概当作 Agent 的任务执行者。

### 匿名远程调用的实际源码边界

作者 [HTTP Worker](https://github.com/clicks-protocol/clicks-protocol/blob/f6924036c15469b303d98666ccfc304adc6cd1f9/mcp-http/src/index.ts) 是无鉴权的只读 JSON-RPC，入口 `https://mcp.clicksprotocol.xyz/mcp`。GET 根路径提供服务说明；`POST /mcp` 支持 `initialize`、`tools/list` 与 `tools/call`。源码中的远程工具是四项：

| 工具 | arguments | 业务输出/独立核对方向 |
| --- | --- | --- |
| `clicks_get_agent_info` | `agent_address: string` | 注册状态、operator、已存本金、yield百分比、USDC余额，对照明确合约的 view |
| `clicks_simulate_split` | `amount: string`（USDC十进制）、`agent_address: string` | `payment_usdc/liquid_usdc/to_yield_usdc`；按6位精度与 Splitter 的 simulateSplit 对照，无真实资金转移 |
| `clicks_get_yield_info` | `{}` | 当前协议、APY、总余额与费用；部分 RPC 错误会被转成 unavailable 或 `0.0`，不能把这些0直接当真实链状态 |
| `clicks_get_referral_stats` | `agent_address: string` | referrals、earned、claimable、链和bonus，对照Referral只读状态 |

具体只读请求形状（尚未执行）：

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"clicks_simulate_split","arguments":{"amount":"1.234567","agent_address":"0xf873BB73e10D24cD3CF9bBed917F5E2d07dA8B80"}}}
```

这些路由代码不收取支付、不要求私钥；实际 GET 的 `/mcp/server.json` 为 HTTP 200，声明远程地址确为上述 MCP、文档版本 1.0.3、npm 包 0.3.2，私钥仅写操作需要。npm/stdio 服务与远程 HTTP Worker 的代码不同，不能拿仓库 16 工具声明当远程已提供。作者 [当前状态](https://github.com/clicks-protocol/clicks-protocol/blob/f6924036c15469b303d98666ccfc304adc6cd1f9/STATUS.md) 明确 Receipt V2、安全状态机和五个 receipt 只读工具仍属 repository-stage；未据此发现可匿名查询真实 receipt 的远程路径。

随后根代理只执行了三次固定匿名只读请求，原件为 `runtime/candidate-check-20261018T062845Z-66a748a3/`，命令退出 0。`initialize` 为 HTTP200、server 0.1.0/protocol 2025-03-26；`tools/list` 为 HTTP200，实际四工具与上述源码吻合。`clicks_simulate_split` 使用金额 `1.234567` 和 operator 地址，虽然 HTTP200，但业务响应 `result.isError=true`，内容为上游 1rpc 的用量限制，没有取得分账结果。因此仅确认协议与发现连通，业务检查仍 UNKNOWN；所有观测用途为 background，不进入正式评分。本轮不再请求该MCP业务，不重试、不绕过上游限制。

### 历史证据与决定性缺项

- `0x5aec2067384c68421c4964682fec5e5c8e987a44e69b22460eaabdaa213f9578` 曾被摘要称为 first Schema-V1 attestation；但作者 [seed-attestations.json](https://github.com/clicks-protocol/clicks-protocol/blob/f6924036c15469b303d98666ccfc304adc6cd1f9/config/seed-attestations.json) 明确目标是 **Agent #1**，由 Clicks operator 发出中性 bootstrap feedback。它不是 #45074 的成功交易、第三方评价或真实结算任务。
- 作者 [attestor schema](https://github.com/clicks-protocol/clicks-protocol/blob/f6924036c15469b303d98666ccfc304adc6cd1f9/strategy/ATTESTOR-SCHEMA-V1.md) 定义别人如何给分，不是任务输入输出原件；不复制其 value 当平台分。
- 已发现 `/api/public/proof.txt` 与 `/api/public/metrics` 的源码线索，但内容是聚合统计，不提供逐任务 request/receipt/tx 原件；不把 TVL、payment count 当完成任务证据。
- HTTP Worker 的链读取固定为 `latest`，工具输入不接受 blockTag、输出不返回查询区块。当前无法声称有同一固定块的严格对照。应先确认动态字段能否取得可锚定输入；不向接口发送它未支持的 block 字段后宣称问题解决。
- 缺少可归属于 #45074 的足量真实结算任务：需业务输入/授权/receipt 到实际调用者、目标合约、PaymentReceived/USDC流及区块的关联。协议任意用户调用合约产生的交易不自动计为这个 Agent 的履约。

当前状态：**待远程发现、待固定块判据、待真实业务历史**。可优先验证分账预览等有限功能，但无法据此提供完整交易行为分。

## 最少的下一步受控实读

按依赖顺序逐项判断继续，不开始完整采样：

1. **delu 先查首条历史，不测实时仪表盘。** 复用已核实注册和固定快照，保留当前源码/静态任务原件；只新增上述 MOLT 交易、回执和对应区块读取。先解决身份与 sender/controller/recipient 的归属，再决定是否扩大任务。若只有这一条且其余无 task-to-tx 关系，保留缺样本状态。
2. **Clicks 远程发现已完成，业务遇限额后停止。** 已复用三份原件确认协议连通与四工具；不再执行上述发现或分账请求。上游限额未解决前保留 UNKNOWN，不调用写工具或开立任务。
3. **Clicks 再查判据。** 复用固定块注册；可信 Base RPC 只新增 Splitter 代码与相应 view。若无法把返回值锚定同一输入/区块，记录 UNKNOWN，并先找作者已经公开的原始结算 receipt 与交易列表。不要全链扫日志或用 bootstrap feedback 凑履约任务。

补查未找到第三个满足完整条件的对象，因此没有增加一个仅有标签的占位候选。另发现 Echo / AgentPass（作者声明 Base #32176），但公开资料主要是本地认证 demo、无已核实公网服务及足量历史任务，未列为本轮优先对象。本文不改变现有政策、对象计数或主线范围。

## 四候选离线准入补记

Custos、Olas、delu、Clicks 的当前事实已由 `configs/candidate-reviews-20261018.json` 记录，每对象恰好六项检查，复用现有共享类型、准入规则和中文渲染器。证据只引用已经保留的公开观测与响应，逐文件摘要进入通用 `inputs(path, sha256)` manifest；缺少本地原件的作者声明只列官方源码来源，不伪挂其他响应作为证明。

执行 `.venv/Scripts/python.exe scripts/build_expansion_admission.py configs/candidate-reviews-20261018.json` **退出 0**，生成 `runtime/admission-report-20261018T063130Z-e7ee947b/`：4 个候选、0 个完整准入、复用 31 条真实观测、新增外网请求 0、声誉分数 0。本步骤没有接触数据库、运行工程测试或提交；主任务可随后导入目录，不能把新增目录数当完整评分数。
