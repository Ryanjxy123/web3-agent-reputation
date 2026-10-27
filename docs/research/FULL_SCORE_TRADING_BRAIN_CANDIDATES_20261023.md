# Brain / Hallmark：完整三维交易评价候选核查

日期：2026-10-23（北京时间）。本轮仅调查候选和读取公开证据，未新增生产适配、评分、签名、付款或链上写入。

## 结论

在本轮限定的 Brain / BOBAI 与 Hallmark 范围，**尚未找到两个已具备充足证据、可以立即开展完整三维资产执行评价的对象**。

找到两个比继续扩无公开服务入口的 Olas 交易者更值得保留的真实候选：Brain Venus Health Factor Monitor **#302257** 与 Venus Yield Ranking **#304493**。它们各有公开身份、免费查询能力、独立执行钱包，以及已经发生的自有账户资产操作；代表交易的历史注册钱包、交易、回执和区块已经独立核验。不过公开自治日志各只有 **1 次业务运行**，健康因子 Agent 的供给、加入抵押市场、借款是同一次任务的三步，不能拆成三个独立样本。当前不能满足完整交易行为评分的样本要求。

二者同用 Venus，能够共享身份、链、授权、回执及资产流转的取证层；“维持借贷健康度”和“按收益排名存款”需要不同的业务正确性判据。不能因此立即声称已有一个通用业务评价方案在两个对象上成立。

## 1. 本阶段选取条件

候选必须在**同一真实注册身份**上同时具备：

1. 可实测的公开服务入口，能分清状态文件、查询、模拟、计划与真实执行。
2. 有来源、范围清楚的交易或签名能力声明。
3. 可归属的真实任务/运行记录、执行账户、授权和链上结果。
4. 拟评价维度所需的独立事实及足够任务数量；缺项不靠换权重、重复字段、拆步骤或迁移其他身份的历史补齐。

“14 个交易”不是所有 Agent 的统一门槛：只有 F、B 都采用执行任务并按两组各 7 个不同任务划分时，才需要 14 个对应业务任务。F 也可能评价另一项已经声明的查询能力，但报告必须明示查询范围，不能把其正确性说成执行正确性；B 仍要有充分的可归属执行任务。本轮两个新候选连 7 个不同自治 B 任务也不具备。

## 2. 候选矩阵

以下身份均在 BNB Smart Chain（chainId 56），ERC-8004 Registry 为 `0x8004a169fb4a3325136eb29fa0ceb6d2e539a432`。

| 对象 | 可观察的公开服务 | 声明与真实执行历史 | 当前缺项 / 决定 |
| --- | --- | --- | --- |
| Brain #49467 | `brainonbnb.com/mcp`，目录、任务路由、只读链上数据 | 项目有回购销毁日志；官方当前 `llms.txt` 明确该身份是数据源和 broker，不替用户交易或持仓 | **不作为交易 Agent 选入**。不能把同项目全部 burn 交易算到此身份；已有 Position 完整分仍为查询政策 |
| Brain DeFi #363709 | 公开 `/lp/agent` 历史、免费 position look；付费 plan | 注册声明明确运行项目自己的 PancakeSwap V3 仓位；本轮历史文件有 127 条记录，旧报告已独立核验真实包装/兑换/增仓任务 | **已知单对象特例**。用户服务只读取/规划，不签用户仓位；不再次围它开发一个“通用”类，也不拿同项目其他查询身份复制此成绩 |
| Brain Health #302257 | 身份定向 `/status?agent=302257` HTTP200；注册声明免费 MCP `venus_health_factor` | 新官方说明/源码声明用自己钱包维护 BNB 抵押 USDT 借贷，目标 HF 2.2；公开日志只有 2026-10-22 一次运行，含 supply → enter → borrow；代表 borrow 已核历史钱包及链原件 | **保留为高价值候选，未满足完整评分条件**。最多 1 个自治业务任务；不得把 8 次咨询交付数当成 8 次资产任务 |
| Brain Yield #304493 | 身份定向 `/status?agent=304493` HTTP200；注册声明免费 MCP `venus_supply_rates` | 新官方说明/源码声明每天最多将 2 单位自有稳定币存入所持币种中收益更高的 Venus 市场；日志只有 2026-10-22 一次 2 USDC 存款，代表交易已核历史钱包及链原件 | **保留为高价值候选，未满足完整评分条件**。最多 1 个自治业务任务；3 次咨询交付不能替代资产执行历史 |
| Hallmark Range Keeper #338475 | 当前 Agent Card HTTP200；`analyse` 是查询，`report` 是付费查询；另声明 session-key `act` 与免费只读 `cycles` | 卡片明确真实 rebalancing 执行能力；本轮只读查询卡片官方示例仓位 2137641 的 cycles，HTTP200 但 `cycleCount=0` | **未确认充分公开执行历史**。一个示例为空不证明全局从未执行；未取得活跃仓位和任务→交易关联前，不实现交易适配或移用其只读 Position 分 |

## 3. 两个 Venus 候选的实际链证据

共用所有者是 `0xbfaa69233741924ed5b9d5daa9b4bf7b84567f0a`，但两个注册执行钱包彼此不同。钱包和 owner 分别读取，未将收款钱包、owner 和执行者混为一谈。

### #302257：健康因子维护

- 实际执行钱包：`0xeac21928de023677a25eb925d1cb1b0786faf946`。
- 代表借款：[BscScan 交易](https://bscscan.com/tx/0x9c4e6db60733410c4fc20f676cc7712d034bb1e7f2aa89d74b19f7bc5ef245b7)。
- 区块：129070305。`tx.from` 等于交易前块 `getAgentWallet(302257)`；`ownerOf(302257)` 返回上述共用所有者。
- 目标为 Venus vUSDT `0xfd5840cd36d94d7229439859c0112a4185bc0255`，调用 selector `0xc5ebeaec`，对应 borrow。
- 回执 status 成功；交易、回执和真实区块头的 blockHash 一致；回执有该市场 Borrow 事件与 USDT 转账原件。
- 同一运行日志还列出 0.02 BNB supply 和 enter 交易；本轮未把它们各计为独立任务，也未为了补分而全部重新核验。

### #304493：自有稳定币存款

- 实际执行钱包：`0x497dac54fd7238027ecbbd194b353379a1d605f0`。
- 代表存款：[BscScan 交易](https://bscscan.com/tx/0xb0f229e60be823a5080916d6616565d31df0b29b98edbfe166280ff44f2a5f0c)。
- 区块：129070313。`tx.from` 等于交易前块 `getAgentWallet(304493)`；所有者同上。
- 目标为 Venus vUSDC `0xeca88125a5adbe82614ffc12d0db554e2e2867c8`，调用 selector `0xa0712d68`，对应 mint。
- 交易、回执和区块头 blockHash 一致，回执 status 成功；存在 2×10^18 个 USDC 最小单位从该钱包流向 vUSDC 的 Transfer，以及 vUSDC 份额流入钱包的 Transfer。
- 本次 vUSDC 回执的 Mint 事件形状为 `Mint(address,uint256,uint256,uint256)`，不是旧式三参数 Mint。只查旧 topic 得到 0 不能解释为存款失败。该说明作为追加 `event-interpretation-notes.json` 保留，原探测记录不改写。

以上证明了真实身份与代表性链操作的关联，**尚未完成策略正确性评分**。例如 HF 是否由当时真实抵押/债务/预言机价格推得、收益比较是否对应当时可用资产与利率、行动是否满足所有约束，需要在确定评分范围后另做独立固定块事实核验。

## 4. 功能声明和接口存在的边界

公开声明来自 [Brain llms.txt](https://brainonbnb.com/llms.txt)、[Venus 自治说明](https://brainonbnb.com/venus)、[原始运行日志](https://agent.brainonbnb.com/venus/work) 及 [公开源码](https://github.com/mmxrealQQ/bobai-buyburn)。`GET /venus/work` 路由已审阅，仅取 KV 记录，不调用执行函数。本轮没有触发 cron 或 runVenusWork。

源码注释称自治功能于 2026-10-21 新增；当前日志是 10 月 22 日 05:00 UTC 的一次运行。该调研未额外证明源码在真实交易前的公开发布时间，不能用后来看到的注释伪造历史承诺时间。

两对象交易前 `tokenURI` 均为内嵌 JSON，已从真实 RPC 解码保存；其中注册功能分别是健康度查询、市场收益排行及咨询交付。新自有资金自治能力见当前官方站点/源码，不能把原注册的“给客户查询”直接改述为“替客户操作资金”。

当前 `/status` 是 cron 生成的缓存，返回 ready/参考输入测量和 checked_at。健康 Agent 的状态说明仍写“没有自己的仓位、按 job 提供服务”，与新自治交易日志不一致。本轮保留两份原件及日期，不替提供方解释成已经一致；也不把状态 HTTP200 或 provider 自报 ready 当作已完成本平台的服务可用性采样。

免费 `venus_health_factor` / `venus_supply_rates` 的路径和只读分派已在当前注册文件及 worker 公开源码找到；本轮不额外调用业务工具凑样本。链记录与查询服务属于同一注册身份，但报告中仍需分开能力范围。

## 5. Hallmark 没有重复进入旧坑

[当前 Range Keeper Card](https://hallmark-agents.vercel.app/rebalancer/.well-known/agent-card.json) 返回完整200，明确区分 `analyse`、付费 `report`、session-key `act`、只读 `cycles`。本轮只调用 `cycles`，输入严格限该卡片的官方示例 NFT `2137641`，chainId 56；得到 `cycleCount=0`。

这只能说明此示例在该接口返回的记录为空。未枚举随机仓位、未调用 act、未申请 session、未签名/付款，也未把旧 #338475 Position 查询报告当成真实重设仓位证据。

现有项目保留了 10 月 20 日的官方源码预审资料。此次尝试读取当前 main 的 act/store/README，以及旧 Git 树中两个不可变 blob，共五个不同 URL 均404，随后停止；未通过反复更换来源推定源码已可用。不能因这些404断言部署不存在，也不能宣称已核实当前部署与旧源码完全相同。

## 6. 证据路径与实际成本

本轮公开原件目录：`runtime/full-score-trading-brain-research-20261023/`。汇总为 `research-summary.json`，每次请求先保存 request-plan，再保存 observation、真实 response 及其 SHA256。

关键文件：

- `brain-llms.response.bin`、`brain-current-worker.response.bin`、`brain-current-venus-source.response.bin`：最新声明和 GET/只读分派源码。
- `brain-venus-work.response.bin`：完整自治日志，只有一个日期。
- `brain-health-status.response.bin`、`brain-yield-status.response.bin`：两个身份的当前状态及自报边界。
- `brain-health-catalog.response.bin`、`brain-yield-catalog.response.bin`：目录资料，仅作为发现/交叉来源。
- `venus-chain/venus-{302257|304493}-{tx|receipt|header|wallet-before|owner-before|registration-uri-before}.*`：可信操作者 RPC 的原始证据。
- `venus-chain/venus-{302257|304493}-registered-metadata-before.json`：从历史链上 URI 解码的注册 JSON。
- `venus-chain/brain-domain-registration.response.bin`：官方域名身份声明。
- `hallmark-card.response.bin`、`hallmark-cycles-official-example.response.bin`：真实卡片及一次只读历史查询。
- `brain-history.response.bin`、`brain-burns.response.bin`：127 条 LP 记录与435条项目 burn 记录；记录数量不等于可评分业务任务数量。

实际发送 **37 次请求：23 GET、14 POST**；32 个 HTTP200，5 个 HTTP404。POST 中 13 次为可信 RPC 只读，1 次为 Hallmark 只读 cycles。没有重试同一请求；源码404不算Agent业务失败。全部通过已有 SafeHttpClient / DiscoveryEvidence 和显式7897代理，RPC来自静态操作者配置。新交易0、签名0、付费0、LLM调用0。

## 7. 对主线的建议

这两个 Venus 身份可作为持续积累公开自治证据的候选，但当前不要为它们先建第三类评分或修改门槛。若以后证据充分，先明确评价“自有账户自治健康维护/存款”还是“客户查询”，分别选择样本与独立事实。

本阶段需要的第二个**已充分可评的真实交易对象群体**仍未找到。应继续让总候选调查覆盖其他提供方；若其他调查也未找到，向用户报告这个具体瓶颈及可选择的主动测试方案，不用上述新发现包装成已经达成完整三维覆盖。
