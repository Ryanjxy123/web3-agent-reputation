# N9T2 Bridge：最低报价、账户激活与往返资金

2026-10-29，只读资格/成本核查。**保留为后续候选，本轮不付款、不在这份 15 分钟报价的窗口内抢先执行。** 按 root 本轮已核余额，6.630885 USDC 已超过当前 SMA 稳定币余额；后续如开展，需先以自有资产兑换补足，而本研究没有兑换、读取钱包或操作密钥。

## 本次唯一免费报价

目的地址是 root 本地生成并自控、尚未激活的 XRPL classic 地址 `rsmtoeu2mNTbvWbodgEWEpxijjnsDfHQ1R`。按官方 schema 请求 Base USDC→XRPL native XRP，省略 `source_amount` 获取该路线实时最低值，**没有伪造地址**。经 SafeHttpClient、proxy7897、pinDNS、进程 DoH resolver `1.0.0.1` 只 POST 一次，HTTP200、完整响应；没有 `/bridge/payment`、receipt poll、付款、签名或发送。

| 项目 | 原始报价值 |
| --- | --- |
| quote_id | `6ae1a6de642b0f916ed5287ff30ece6832a248d8046b831ad1ea79d5993be84e` |
| live minimum / transfer principal | **4.715946 USDC** |
| service fee | **1.45 XRP 等值，即 1.914939 USDC** |
| customer_input / 精确 payment | **6.630885 USDC = 6630885 raw** |
| quoted native XRP delivery | **3.370649 XRP** |
| payment network/token | Base8453，原生发行 USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`，6 decimals |
| payment pay_to | `0x9D910dBaA7615D8785BaB65Fad9DED88bd5739BF`；仅为本份官方报价指令，本研究未付款 |
| 创建 / 过期（UTC） | 2026-10-28 18:06:56 / 18:21:47 |

**1.45 XRP 是每笔桥接的服务费等值，不是最低本金，也不是另付 1.45 native XRP。** 此方向按源资产 USDC 收取，4.715946+1.914939=6.630885。商业桥的 quote 调用免费，不表示桥接免费；不要与付费 XRPL 数据 RPC、ACP 的独立 0.01 USDC job fee 混为一项。[N9T2 官方说明](https://x402.n9t2.com/llms.txt)

客户付款钱包提供这笔完整 USDC，并用自身 Base ETH 承担标准 ERC20 transfer 的 gas；报价未给这笔源交易 gas 金额。目的地址接收 XRP 时不提交交易，不另从新账户余额扣一次“接收 gas”；XRPL 的交易 Fee 由实际出款 Payment 的发送账户承担，其经济成本可能已反映在桥接报价中，仍以真实交付和链证据核实。

## 可以激活，不表示已经激活或可立即往返

当前已缓存 XRPL 官方文档载明 mainnet base reserve=1 XRP、每个有储备要求的对象另增 0.2 XRP。新账户接收足额 native XRP 可以建立账户；不需要 XRP trustline。本次提供方接受了该新地址并返回 `executable=true`，预计3.370649≥1，**理论上可激活并保留2.370649 XRP超储备余额**。但未收到 validated Payment 或观察 AccountRoot，实际激活仍为 UNKNOWN；接口“可执行”不能代替结算。[XRPL 官方 reserve](https://xrpl.org/docs/concepts/accounts/reserves)、[账户说明](https://xrpl.org/docs/concepts/accounts)

不应为先跑通单程，就把资金放进无法完成所选反向任务的新钱包。回程须同时留出账户储备、反向实际付款金额和发送该 XRP Payment 的网络费。仅有2.370649 XRP可花余额，不证明反向路线达标。

## 只用缓存资料的往返关系估计

此前2026-10-23的**已过期** XRP→Base USDC 原始 quote 为：反向最低本金3.568791 XRP + 服务费1.45 XRP = payment **5.018791 XRP**。它不是今天的最低承诺，只能说明资金结构。

令反向本金最低额为 `Pᵣ`，反向服务费为 `Fᵣ`，发送回程 XRP 的实际网络费为 `gᵣ`，需保留的 reserve 为 `R`。则首程实际到账至少应满足：

`received_XRP ≥ R + Pᵣ + Fᵣ + gᵣ`

代入缓存反向值，仅储备与回程款就需 **6.018791 XRP + gᵣ**；当前首程最低报价只给3.370649，因此还差 **2.648142 XRP + gᵣ**。储备1 XRP是保留本金，不是又一笔服务费。

若仅为规划粗估，暂假设首程“4.715946 USDC本金换3.370649 XRP”的平均比例不变，得到需要的首程本金约8.421017 USDC，加本次服务费1.914939，初始总款约 **10.34 USDC，另加源Base gas及回程XRP gas影响**。这不是可付款金额、当前路线最低额或执行预算：两个方向资料跨日期、市场及路由成本可变，也不能据此计算保证回收的USDC。正式往返必须重新取得两方向相容的有效 quote，再固定金额与判据。

两方向各一次的固定服务费结构为 **1.45+1.45=2.90 XRP等值**，另有路由成本和链gas。若仅用本次兑换关系做同一时点示意，两次服务费约3.829878 USDC；这个数不替代回程实际源资产收费，也不把账户储备当损失。

## 原件与停止点

- 本次 request-intent、observation、完整 body、summary 与结论：`runtime/acp-chain-routing-20261029/n9t2-live-review/activation-minimum-quote-20261029/`。
- 本次 body SHA256：`388621bc4ecc8e532a65a86e243562a5d3a619de29b71a2011f47e4610832a3e`。
- 历史反向原文：`runtime/virtuals-n9t2-free-quote-20261023T113456Z-ff1ff18d/quote.response.bin`；原始5.018791拆分仍保持。
- 官方资料缓存：`n9t2-live-review/current-primary/n9t2-llms.response.bin`、`xrpl-reserves.response.bin`、`xrpl-accounts.response.bin`。

接口已实际接受自有新地址，后续能力仍可评；本轮因稳定币余额及往返资本结构保留、停止付款，不据此宣称永久不可评。没有为此新建第二个钱包、追加 quote、签名、付款、链写或伪造txHash。
