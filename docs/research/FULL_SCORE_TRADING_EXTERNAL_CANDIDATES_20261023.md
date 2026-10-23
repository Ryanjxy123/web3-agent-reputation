# 外部真实交易 Agent：完整三维评价候选调查

调查日期：2026-10-23。范围为现有 Olas、Brain 之外的对象；仅做公开资料研究与少量只读可行性检查，不发起任务、认证签名、付费或交易，不新增生产适配器。

## 结论与优先级

本轮尚未找到两个能够立即取得完整 A/F/B 证据的外部交易 Agent，新增完整可评对象为 **0**。不能把平台目录可访问、注册了钱包或提供交易 SDK 解释为三个维度都可评分。

下一轮最值得核实的是 **ACP 中真实提供兑换/交易服务的对象**。其服务声明包含输入、交付结构、费用和 SLA，任务协议包含已创建、已付款、完成、拒绝、过期等状态，比只有成功交易列表更接近可界定的任务分母。但当前 v2 身份/任务读取需要签名认证；公开交易任务原文、实际执行账户和 Agent 自身服务入口仍须逐对象取得。

已直接核到 **Wasabot #1048** 的完整官方目录资料、钱包、报价/交付 Schema 和五个明确声明的只读资源。它是当前最具体的外部候选，但资源连接尚未成功，且还没有第二个满足同等条件的对象，不能据此启动 Wasabot 专用实现。

Giza 与 Almanak 有真实资产执行产品，但本轮只核到产品与开发资料，未取得可供本平台独立评价的多实例身份、公开入口、授权和历史闭环。AgentWallet 同名产品也必须分开看：一个是邀请制金融基础设施，另一个主要为 Solana devnet 钱包/托管框架；均不能按账户数计为真实第三方交易 Agent。

## 候选矩阵

下表中的“待核”不是 Agent 失败。A=服务可用性，F=功能声明一致性，B=交易行为可靠性；没有执行正式评分采样。

| 对象与具体身份 | 已有交易声明与入口 | A 可评性 | F 可评性 | B 可评性 | 当前判断 |
|---|---|---|---|---|---|
| **Wasabot / ACP #1048**；完整目录钱包 `0x5Dfc180212204Fff869d41FAA9f1b430D2036f5D`；ACP 合约 `0xa6C9BA866992cfD7fd6460ba912bfa405adA9df0` | Base 开/平杠杆仓、止盈止损、LP 存取；声明 `api.wasabi.xyz/v1/virtuals/acp/` 资源；官网 [wasa.bot](https://www.wasa.bot/) 的入口指向 ACP | 有明确资源 URL；本轮 markets/history 各单读连接错误，尚无成功业务响应，更未采齐十槽 | 官方 Schema 给 amount/symbol/leverage/direction 以及交付 positionId/transactionHash；尚缺真实任务输入与交付实例，未验证杠杆、方向和资产效果 | 有链和 ACP 合约线索；目录钱包不自动等于用户仓位执行账户，仍需 client→Wasabi account→position/交易绑定、历史权限与独立任务样本 | **优先补证候选，当前不可完整评分** |
| **Nox / ACP v2 UUID `019e4f32-23d3-78eb-80bc-9545cdc49328`** | [公开 Agent 页面](https://app.virtuals.io/acp/agent/019e4f32-23d3-78eb-80bc-9545cdc49328)声明 Base `token_swap`，KyberSwap/Virtuals 路由、输入本金、滑点、退款与 5 分钟 SLA；页面展示地址 `0xd655…4740` | 未找到可匿名核验的该实例独立业务入口；平台注册页不算 A | 兑换目标、输入输出、滑点具备共用建模价值；当前仅有声明，未取得这个 UUID 的真实原始任务和交易对应 | v2 身份/API 需签名认证；完整钱包和执行归属未核实，不能用旧同名钱包代替 | **声明候选，不计可测/已评覆盖** |
| **iCLONE / ACP v2 UUID `019eae06-96cd-77d0-8f8b-a6abb71f0cd7`** | [公开页面](https://app.virtuals.io/acp/agent/019eae06-96cd-77d0-8f8b-a6abb71f0cd7)声明 `swap_base`、`swap_arbitrum`、跨链兑换，经 LI.FI，要求资产地址/数量/recipient，30 分钟 SLA；展示地址 `0x44cc…6664` | 独立可调用业务入口未核到；官网读取遭 403，不据此扣 Agent 分 | 与 Nox 同属兑换语义候选；跨链结算不能直接套单链兑换判据，尚缺原任务和实际交付 | legacy 同名目录查询为零，v2 与 legacy 身份映射未核实；不能拼其它提供方的历史 | **第二个兑换声明对象，尚未证明与 Nox 同时可测** |
| **Giza Agent / Giza World**，产品入口 `agent.gizatech.xyz`、`world.gizatech.xyz`；本轮未取得具体公开实例 ID/钱包 | 自动稳定币配置、再平衡、复投与风险约束；官方 SDK/MCP 提供 portfolio/transactions 等工具 | SDK 需要 partner API key；MCP/OAuth 是平台接入机制，未得到实例公开端点 | 有具体投资约束，但没有某个真实实例当时的用户约束/决策/交易资料 | 有智能账户方案，未取得两个具体实例的历史授权和任务闭环；不使用 SDK 示例地址冒充真实用户 | **合作/凭证与实例资料前置，不优先写适配** |
| **Almanak hosted deployment**；本轮未取得可独立评价的公开 deployment ID/账户 | 平台将策略部署到 Safe/Zodiac Roles 权限范围；界面有部署状态与交易链接 | Dashboard 是用户部署管理入口，不等于公开 Agent 服务 API；未找到匿名多对象业务入口 | 策略 `config.yaml` 可表达经济约束，具体运行版本/配置未取得 | 多策略可能共享同链 Safe，须以 deployment 与角色范围区分任务，不能按 Safe 个数算 Agent；缺实际权限和运行历史 | **产品真实，但本轮没有完整可测实例** |
| **Bankr 托管 Agent/API**；入口 `api.bankr.bot/agent/prompt`、`/agent/job/{jobId}`；本轮无多个公开 Agent 实例身份 | 自然语言指令执行兑换、资金操作；SDK 另有交由用户钱包签名的 prepared actions | 需要 API key；只读 key 可调用读工具，不能据此声称交易业务已测 | 准备交易和已经执行是不同 API 路径，不能把 action/calldata 当链上完成 | 需要自己的钱包/权限和原始 job 交付；用户账户/子钱包不是天然独立公共服务 Agent | **保留候选入口，不计多对象覆盖** |
| **AgentWallet.ai**，`agentwallet.ai` | 钱包、卡、支付控制的金融基础设施 | 邀请制；Agent endpoints 需 `pak_` key，MCP 用 OAuth | 没有取得真实公开交易 Agent 的身份及任务 | 没有第三方交易实例的授权/历史闭环 | **基础设施，不是已发现的交易 Agent 群体** |
| **AgentWallet Protocol / YouthAIAgent/agentwallet**，`agentwallet.fun`；程序 ID `CEQLGCWkpUjbsh5kZujTaCkFB59EKxmnhsqydDzpt6r6` | 官方示例为 Solana devnet 钱包、转账、托管/escrow；不是已证明的公共交易服务群体 | 文档链接的 `/health`、`/openapi.json` 本轮各单读 404；不推断全产品已停止 | API 示例和自动创建 wallet 不能证明某个 Agent 执行业务；示例 ID/签名不算评价样本 | 需要组织注册、令牌、资金与真实实例资料；devnet 和主网覆盖分开统计 | **暂不优先；仓库已于 2026-08-17 归档** |

Wasabot 的身份和 Schema 已由官方无认证 API 原件直接核到；Nox/iCLONE 的 v2 页面声明来自官方目录的搜索索引，本轮实时网页抓取只取得 JavaScript 外壳。两者证据强度不同，不把搜索索引内容称作已下载的完整注册原件。其它产品只作为待调查入口，不记为已发现多个合格实例。

## ACP 的关键发现

### 1. 当前 SDK 与旧公共目录不是一个接入边界

官方 v2 SDK 的 `browseAgents`、`getAgentByWalletAddress`、`getJob` 均调用 `ensureAuthenticated()`；认证使用钱包签名换取 JWT。本轮没有签名或绕过认证。[API 客户端](https://github.com/Virtual-Protocol/acp-node-v2/blob/main/src/events/acpApiClient.ts)、[认证客户端](https://github.com/Virtual-Protocol/acp-node-v2/blob/main/src/events/acpHttpClient.ts)

旧 v1 SDK 有明确的无认证 `getAgent` 公共 GET；本轮沿该来源读取 Wasabot 资料并获 HTTP 200。这只能证明目录元数据可读，不代表 Agent 在线或已授权执行。[旧官方客户端](https://github.com/Virtual-Protocol/acp-node/blob/main/src/acpClient.ts)、[官方服务配置](https://github.com/Virtual-Protocol/acp-node/blob/main/src/configs/acpConfigs.ts)

本轮没有安装旧 SDK。旧 SDK 已停止维护，不能为取资料把它接回生产运行路径。[官方迁移提示](https://github.com/Virtual-Protocol/acp-node/releases)

### 2. 同名对象不可合并，历史指标不证明当前服务

无认证查询 `filters[name]=Nox` 返回 5 个旧记录：1588、17979、20971、22884、24886。记录 #1588 钱包为 `0xa42cAe963CaaA4218C8F045d153b2172f2459319`，描述是“Upgrading. Be back soon.”；五项均无 jobs/resources。它们均不能与 v2 UUID 展示的 `0xd655…4740` 直接合并。iCLONE 同名旧目录结果为零，也不证明 v2 对象不存在。

Wasabot 目录返回 `lastActiveAt=2026-06-02T19:10:28.686Z`；这是平台自报历史状态，不能转为当前在线。平台展示的既有 successRate、评分或 Jobs 数不进入本平台评分。

### 3. Wasabot 是有价值的真实候选，但还差什么

官方目录直接声明以下资源：

- `https://api.wasabi.xyz/v1/virtuals/acp/markets`
- `https://api.wasabi.xyz/v1/virtuals/acp/vaults`
- `https://api.wasabi.xyz/v1/virtuals/acp/tradeHistory/{{clientAddress}}`
- `https://api.wasabi.xyz/v1/virtuals/acp/positions/{{clientAddress}}`
- `https://api.wasabi.xyz/v1/virtuals/acp/lpStats/{{clientAddress}}`

其中 `clientAddress` 是实际客户参数，不能为了凑样本随机填地址，也不能假定 provider 钱包就是持仓客户。资源使用的用户仓位账户可能不同于目录钱包。

`open_position` 的原始输入要求 amount、symbol、leverage、direction；本金最少 10 USDC，报价 0.01、SLA 5 分钟，并标记 `requiredFunds=true`。交付 Schema 包含 `transactionHash`、`positionId`、资产地址、首付款、抵押数量等。因此，若后续取得真实公开输入、交付和已绑定账户，可以独立核对方向/抵押/仓位/交易效果；目前只是字段可行性，尚未取得样本闭环。

本轮读取 markets 和带 provider 地址的历史 URL 各发生一次 ConnectError，没有成功内容，故既不能判定业务效果，也不能判断其需要何种认证。历史 URL 的本次调用只证明连接结果，不证明 provider 地址是有效客户。该主机没有继续重试。

### 4. 为什么 ACP 值得继续，但现在还不该写规则

ACP 有可识别的 provider、client、jobId、期限、预算、交付与完成/拒绝/过期状态；执行任务同时涉及账户认证、链上任务创建、支付与可能的资产本金。原始 requirement/message 可能私密，链上支付成功仍不代表交易正确。[当前官方 SDK](https://github.com/Virtual-Protocol/acp-node-v2)

下一轮先核两个明确实例的公开历史链：注册资料→具体 offering→原始请求与交付→实际执行账户→全部相关尝试/结算。若只能读取平台统计或一个成功交易，维持缺项，不启动专用适配。

## 其它生态的真实约束

**Giza**：官方迁移说明明确 ARMA/Pulse 退役，2026-03-26 为迁移期限；当前对象应调查 Giza Agent，不能按两个旧品牌计活跃覆盖。新产品要求连接钱包、入金并确认交易。开发者仓库要求 partner API key；README 的创建账户示例不是公共运行实例。[迁移说明](https://www.gizatech.xyz/blog/giza-world-migration-guide)、[官方 SDK/MCP 仓库](https://github.com/gizatechxyz/giza-hub)

**Almanak**：官方说明用户保持 Safe 控制权，代理 EOA 经 Zodiac 作用域执行；自动运行需要付费 Autonomous Execution Service。一个链上的 Safe 可由多个策略共享，因此钱包/部署/策略/提供方须分开计数。旧 SDK v2 仓库可读不代表可以新部署，本轮不充值、部署或开通服务。[钱包与费用](https://platform.docs.almanak.co/wallets.html)、[部署流程](https://platform.docs.almanak.co/deploy.html)、[版本状态](https://platform.docs.almanak.co/sdk-generations.html)

**Bankr**：Agent API 需要用户 key，且读取信息、准备待签 action、从 Bankr 钱包实际执行各有不同边界。只读 key 不允许交易；其钱包管理 API 也不能自动当作被评价 Agent 的智能决策证据。[Agent 集成](https://docs.bankr.bot/faq/building-ai-agents/)、[动作与执行区别](https://docs.bankr.bot/agent-api/transaction-types/)、[Key 权限](https://docs.bankr.bot/security/developer-api/)

**AgentWallet 同名产品**：`.ai` 为邀请制金融平台，需凭证；`.fun` 官方仓库强调 Solana devnet 和注册组织后创建钱包，且已归档。不能把金融接口、示例合约程序或每个钱包算作独立公开交易 Agent。[AgentWallet.ai](https://agentwallet.ai/agent-payment-api/)、[AgentWallet Protocol 官方仓库](https://github.com/YouthAIAgent/agentwallet)

## 继续投入前的判定点

当前证据与后续动作分为三档：

| 档位 | 本轮已经证明的范围 | 对象与下一步条件 |
|---|---|---|
| 可免费匿名核验 | 官方公开说明、Wasabot完整目录/Schema、旧同名目录结果；尚无两个对象的完整任务闭环 | 保留这些资料，不把目录GET或全平台在线统计计入Agent A |
| 需只读授权或历史导出 | v2完整身份/任务消息、某部署策略与历史权限、原始请求与交易关联 | 只有提供方能同时交付至少两个具体实例的只读资料，才值得继续适配；认证签名仍需具体授权 |
| 需新任务、付款或资产操作 | ACP建Job/预算/输入本金、Giza入金激活、Almanak付费部署、Bankr交易权限 | 本轮没有执行；不能把此档当作已经有免费闭环的方案，也不建议在缺第二个可测对象时先花钱开通 |

1. 开发前先确认多个真实对象有可复用的业务规则或协议证据映射；每对象的 **A 实际声明服务入口、F 独立功能事实、B 身份权限/真实执行关联与独立任务** 须各自成立，不拼接不同对象的优点。三维可以来自同一Agent的不同已声明功能；F若核查询，报告不能称已验兑换正确性。
2. 优先保留单链明确兑换或明确仓位动作；跨链、私密策略、多账户路由先标缺项，不为了扩大声明覆盖先做万能适配。
3. 新认证钱包签名、账户注册、USDC Job 费用、资金本金和真实交易须形成具体方案再获取授权。用户把资产/签名纳入评价范围，不等于操作者可以任意开通或消费。
4. 若没有多个可测实例，本阶段输出可行性记录和阻塞原因，不为单对象开发专用适配；这不阻止现有共用规则为一个合格对象正常评分。认证接口、经授权的只读历史导出和同一提供方的多个真实实例均可接受，当前缺凭证不表示对象本质不可评。7F和7B按不同任务取样，不要求14笔交易；一次任务可包含多笔交易。

## 本轮真实检查收据

工程测试 NOT_RUN：只有研究与公开只读 GET，没有修改评分代码。

| 记录 | 实际结果 |
|---|---|
| `runtime/external-trading-feasibility-20261023T024440Z-cc793fb5/summary.json` | 3 次 GET、0 重试；Wasabot 官方资料 200，AgentWallet.fun 两个指定路径 404 |
| `runtime/acp-trader-resources-20261023T024544Z-3a83015a/summary.json` | 4 次 GET、0 重试；Nox 旧目录 200/5 项，iCLONE 旧目录 200/0 项；Wasabot 两资源各 ConnectError |

两组命令均正常退出（exit 0），含失败网络观察的原件、请求计划、SHA 与状态逐项保留。退出码不代表每个外部服务调用成功。共 7 次公开 GET，没有正式 A 采样、交易、签名、任务创建或费用。本轮未改 PLAN/STATUS 或生产代码。
