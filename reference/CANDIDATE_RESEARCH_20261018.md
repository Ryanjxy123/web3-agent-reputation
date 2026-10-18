# 下一批公共候选资料调查

日期：2026-10-18。当前已完成 Brain 同一真实对象的本机平台闭环与两份历史报告，完整对象覆盖仍为 **1/10**；本文件调查未新增完整三维评分对象。Custos 两个匿名接口均 ReadTimeout，保留 UNKNOWN。Olas 已取得注册/服务桥映射和真实历史任务：首个未来问题不能判准确；随后按固定 cutoff 取得三条较早任务，绑定到同一已结算为 No 的 Omen 市场；首个 pilot 的输入/输出 CID 内容寻址亦已独立验证。下一步由新预测历史政策冻结抽样与指标，再补历史执行控制、接手窗口和注册时间证据。未读取旧项目源码、发起新预测任务、签名、充值或付费；本轮公开读取均为 background，不进入正式分母。

## 保留候选：Custos，作者 0xMaxyz

**身份与主网部署是作者记录，尚未独立核链。** [主网部署文件](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/deployments/5000.json)列出 Mantle mainnet、chainId 5000、agentId 128、部署块 96604858。[README 的注册表](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/README.md#deployed-addresses)指向规范 IdentityRegistry，因此待核实的完整标识为：

```text
agentRegistry = eip155:5000:0x8004A169FB4a3325136EB29fA0ceB6D2e539a432
agentId = 128
YieldVault = 0xc4dc4Bc6e7bF61300747b017C08Ae86b63F08d3F
AgentBenchmark = 0xf1feCfc87fe4613AbCcd6B591884Ce12f272cb87
```

**有明确的匿名只读业务实现。** [服务路由](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/agent/src/server.ts#L159)公开 `GET /snapshot`，返回市场/仓位状态及风险上下文；[历史路由](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/agent/src/server.ts#L272)公开普通 `GET /decisions`，返回缓存链上决策。两者无调用方凭证或付款检查。不要传 `refresh=1`、调用 resync、调用模型问答或付费 `/risk-score`。

[Caddyfile](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/Caddyfile)明确域名和代理路径，具体入口为 `https://trycustos.xyz/api/snapshot` 与 `https://trycustos.xyz/api/decisions`，均不需要业务参数。2026-10-18 真实匿名读取各一次，分别在 16172ms、15640ms 后 ReadTimeout，均未取得 HTTP 状态或响应体、未重试，结果为 UNKNOWN；不能据此判 Agent 业务 FAIL。原件目录 `runtime/candidate-check-20261018T053927Z-27b8ade9` 保留发送前 manifest 与 `custos-snapshot.observation.json` / `custos-decisions.observation.json`，没有响应原件。

**执行归属有设计，但仍缺实际样本。** [agent card](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/agent/src/identity/agentCard.ts#L38)将 `wallet` 明确定义为签署决策的 ALLOCATOR，另列 vault、benchmark 和 API；[部署文档](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/docs/deploy.md#0-prerequisites)要求执行者与 deployer 分开。部署文件里的 `0x77bD2F1cBcccdca1e63ca1B687E8b5d73710b0Ef` 只是 deployer，**不能当执行钱包**。

[decisionFeed 实现](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/agent/src/data/decisionFeed.ts#L227)从指定 vault 的 DecisionRecorded/Rebalanced/DeRisked 事件生成每条 `txHash`、`rationaleHash`、`decisionURI`。实际本轮未取得任何真实决策 txHash 或证据包；仓库 demo、单测和 fork 结果不算主网履约。feed 中部分风险标签由事件 kind 推导，outcome 默认零，缺块时间会回退当前时间，不能直接拿来当独立事实或收益成绩。

**可设计的独立判据：** 保留具体决策的原始输入、calldata、事件、固定区块状态和 decisionURI 字节；独立核算披露的资产变化、配置约束与摘要。snapshot 的 Ondo NAV、Aave/仓位状态须与相同历史状态对照；[snapshot 源码](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/agent/src/data/snapshot.ts)有 15–30 秒缓存，不支持调用者指定固定 block，不能直接拿另一时刻报价判错。优先历史披露/执行窄范围，不评价“最优收益”“提前避险”或资金安全。

**决定性缺口与下一步：** 先核实际注册 tokenURI、注册文件到 API/ALLOCATOR/vault 的绑定，再取得普通历史查询里至少一条真实任务及 decisionURI，最后核链和独立输入。当前 card 源码仍注释其为 Custos 自定义 shape、需映射标准 registration-v1；不能因部署 JSON 有 agentId 就认为标准身份链已闭合。未过这几关不扩框架、不批量模型分析、不计入十个完整评分对象。

## 优先调查线：Olas Mech，服务号与 ERC-8004 号通过桥映射核对

[官方客户端文档](https://stack.olas.network/mech-client/)给出 Gnosis 示例 serviceId **2182**、Mech `0xc05e7412439bd7e91730a6880e18d5d5873f632c`，同时明确 Olas serviceId 与 ERC-8004 agentId 是不同标识。初始 web 工具调查未能读取注册发现入口，未取得 HTTP 结论；该读取缺口随后已由受控 CLI 补齐，见后文。两个 ID 恰好同为 2182 现有官方声明依据，不能据此泛化其他实例。

[官方发现路由](https://github.com/valory-xyz/autonolas-frontend-mono/blob/5d7ba82f7784fd3d1018f425b9c94d1036072bee/apps/marketplace/pages/api/erc8004/%5Bnetwork%5D/ai-agents/%5BserviceId%5D.ts)从登记关系输出 `registrations`，可能为空；提供工具和 benchmark 链接不证明已经注册或免费。operator 域名声明也不足以代替执行控制证明。

[Mech 作者说明](https://github.com/valory-xyz/mech/blob/main/README.md#off-chain-requests)区分了两条路径：新任务需要签名和预存付款，不调用；现有任务的 `GET /fetch_offchain_info` 可返回 `response` 与 `content_cid`，但每个实例的公开 base URL 必须从其 metadata 解析，off-chain 默认关闭。IPFS 交付内容可与实际请求/交付事件、requestId、指定 Mech 和服务 Safe 联合核验；不能把抢单者交付算给最初指定但未交付的 Mech。

初始调查的注册与历史任务缺口已在下文部分补齐：免费取得一个真实请求/交付和概率输出，尚缺正式可复用的三维判据与足量样本。预测服务不能仅因交付概率 JSON 就判预测正确；需已结算事实及事先固定的判据。现阶段是已确认可免费读取原始历史证据的候选，**不是已完成三维评价对象**，不借用 Olas 的 Karma 或官方 benchmark 分数。

## 暂不推进：Giza / ARMA

[当前作者 SDK/MCP 仓库](https://github.com/gizatechxyz/giza-hub/blob/main/README.md)明确前提是 Giza partner API key，列出账户、组合、APR 和交易读取接口；[早期 giza-agents](https://github.com/gizatechxyz/giza-agents/blob/main/README.md)也要求用户登录。这些不构成匿名免费许可。本轮官方资料未核实 ARMA 的完整 ERC-8004 标识、匿名公共业务入口或某个已注册 Agent 对应的原始历史任务。用户智能账户、充值和账户所有交易不能归为同一公共 Agent 的输出。先保留缺项，不生成候选假分，也不要求用户开户或付费来凑覆盖。

## Olas 受控资料读取补记

2026-10-18，根代理先以固定白名单取得官方 [registration 入口](https://marketplace.olas.network/api/erc8004/gnosis/ai-agents/2182) HTTP 200，原件为 `runtime/candidate-check-20261018T055124Z-88e6eb13/olas-registration-2182.response.bin`。该文件声明 `agentId=2182`、`agentRegistry=eip155:100:0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`、`active=true`、名称 Valory Mech Predict。当时尚未核链；后续固定区块读取见下文。

随后只执行两次额外匿名资料 GET，无重试、模型、RPC、付款、签名或新任务：

| 资料 | 真实结果 | 原件 |
| --- | --- | --- |
| registration 指向的[固定 IPFS manifest](https://gateway.autonolas.tech/ipfs/f01701220dd974e01447d4b3fcc180e9320fb0bbd452ca374407c99a876e420a07be88c29) | HTTP 200，JSON | `runtime/candidate-check-20261018T055429Z-100ff385/olas-manifest-2182.response.bin` |
| registration 和 manifest 共同指向的[官方 analytics 文档](https://mech-analytics-api.autonolas.tech/v1/metrics/mech/100/0xc05e7412439bd7e91730a6880e18d5d5873f632c) | HTTP 200，4,232 字节 JSON，仅汇总数据 | `runtime/candidate-check-20261018T055513Z-4235751e/olas-analytics-2182.response.bin` |

各目录均有发送前 manifest、观测记录和响应摘要。HTTP 成功只表示资料采集成功，不作为正式可用性或功能样本。

manifest 的新事实：

- `url` 和 `operator.domain` 均指向 `https://c05e7412439bd7e91730a6880e18d5d5873f632c-100.mech.valory.xyz`，`operator.name=Valory`。这是实际配置的声明，不是域名/签名控制已独立核实；本轮没有访问此业务主机。
- `inputFormat`、`outputFormat` 均为 `ipfs-v0.1`。当前四个 tool 为 `factual_research`、`superforcaster`、`superforcaster_calibrated_full_search`、`superforcaster_full_search_olas_predict_r1_14b`，是同一注册实例的工具，不能算四个独立 Agent。
- 四者输入均为预测问题文本，输出 schema 要求 `requestId`、`prompt`、`result`；`result` 是 JSON 字符串，示例字段包括 `p_yes/p_no/confidence/info_utility`。schema 的示例值不是实际预测、历史任务或正确性证据。
- 没有给出具体既有 requestId、交付 CID、任务 txHash、服务 Safe/实例 EOA，亦没有明确缓存 TTL 或材料更新时间。域名中的 Mech 合约地址不是执行钱包证明。

analytics 返回 `mech_address`、`chain_id=100` 和四个时间窗口内各工具的数量与 accuracy 汇总，**没有**单任务 ID、原始问题、交付 CID、交易哈希、结算来源或执行钱包。该 accuracy 仅原样保留为第三方资料，不进入平台任何评分，也不能反推成功交易数或代理服务可用率。

以上为早期资料读取记录；随后已通过官方子图定位和可信 RPC 取得真实历史 request/交付，见下文。仍不提交签名任务、充值或调用任一付费预测工具。

## Olas 固定区块身份与真实历史 pilot

操作者 RPC 采用 `configs/trusted-gnosis.json` 中固定的 `https://rpc.gnosischain.com`，不使用 Agent metadata 的 RPC。[Gnosis 官方 RPC 文档](https://docs.gnosischain.com/tools/RPC%20Providers/)明确其为免费 starter，[主网资料](https://docs.gnosischain.com/about/networks/mainnet)确认 chainId 100。脚本 `scripts/probe_olas_history.py` 默认只列计划；发送须同时有 `--execute-public-readonly --proxy`，没有凭证、自动重试、自动重定向或模型调用。

首段 6 次 RPC 全部 HTTP200，冻结 head=48815751，N=head-64=48815687，块 hash=`0x7311c246d521d721727a156d9f5b96102828f6ebf270c028de3defb73ad4ebe5`。第二段复用 N，额外 6 次读取核对：

| 角色/字段 | 真实结果与范围 |
| --- | --- |
| ERC-8004 identity | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2182` 的 ownerOf/tokenURI 可读 |
| 注册 token owner | `0x6e8f740f23f07ce129daa59786926feca8c2d2f3`，官方 IdentityRegistryBridgerProxy，不能当执行钱包 |
| tokenURI | `https://marketplace.olas.network/erc8004/gnosis/ai-agents/2182`，实际 GET HTTP200；其文件 SHA256 与先前 `/api/erc8004/...` 原件同为 `743dee98217f51df7b2a835b8de8827b4ca712fdc1ebf047e264a21d3056e929` |
| Mech | `0xc05e7412439bd7e91730a6880e18d5d5873f632c` 有代码，`serviceId()` 返回 2182 |
| 服务注册表 | `serviceRegistry()` 返回官方 Gnosis ServiceRegistryL2 `0x9338b5153ae39bb89f50468e608ed9d764b755fd` |
| 服务 operator | `getOperator()` 返回服务 multisig `0xcca28b516a8c596742bf23d06324c638230705ae`；这是 N 时的状态读取，不是历史每时刻控制权证明 |
| 两种编号关系 | Bridger 的 `mapServiceIdAgentIds(2182)` 实读返回 2182；依靠桥映射建立关系，不因号码相同推断 |

[官方 Mech 合约](https://github.com/valory-xyz/autonolas-marketplace/blob/main/contracts/OlasMech.sol)的 `getOperator` 取 `mapServices(serviceId).multisig` 并要求 Deployed；[注册表官方配置](https://github.com/valory-xyz/autonolas-registries/blob/main/docs/configuration.json)列出对应部署；[Bridger 源码](https://github.com/valory-xyz/autonolas-registries/blob/main/contracts/8004/IdentityRegistryBridger.sol)给出服务/Agent 映射。当前注册状态已核实，注册发生时间、历史 operator 状态仍未补齐。

最初仅查该 Mech 的 `[48815488,48815687]` 200 块 Request/Deliver，结果为空；不据此扣分，也未扩大窗口盲扫。随后按[官方客户端的公开子图配置](https://github.com/valory-xyz/mech-client/blob/main/mech_client/configs/mechs.json)，向 `https://api.subgraph.autonolas.tech/api/proxy/marketplace-gnosis` 只发一次 `first:1` 查询，条件为 service 2182、该 Mech、blockNumber<=N，并按高度倒序；实体/字段来自[作者查询](https://github.com/valory-xyz/autonolas-frontend-mono/blob/main/apps/marketplace/common-util/graphql/service-activity.ts)和[官方 schema](https://github.com/valory-xyz/autonolas-subgraph/blob/main/subgraphs/marketplace/schema.graphql)。子图只用于定位，随后以 RPC 原件独立核对。

实际历史任务：

- requestId：`0xe9bf1e26682ad31b95a1820f15158c108031a71de5057d2804029ee852abda54`。
- 请求：块 48785013，UTC `2026-10-16T10:43:20Z`，tx `0x3a212a81f195a945b8eaf72d5aa73bf6315bc88e4c8da89af6faad3a32972769`。
- 交付：块 48785085，UTC `2026-10-16T10:49:20Z`，tx `0x6dd4408dca5a104140243fe57f4985b15bae1665e944835a8a3181c42ee0c4bd`，间隔 360 秒。
- 原优先 Mech 为 `0x818df8dcd43d716a7263798c99a2fc8e27010711`，实际 Deliver 发出者才是本候选 `0xc05e...632c`。交付事件中的 multisig 与 N 时 operator 相同；原请求者的钱包、提交交易 EOA、注册 Bridger 和服务 multisig 均分开保留，不互相替代。

两笔 tx、receipt、块头共 6 RPC 均 HTTP200，hash/height/index/状态与原始事件核对后确认同 requestId、输入/输出 digest。首次因“要求请求也直接指向本 Mech”未匹配而停止；该真实差异保留，随后改为明确的“实际交付者接手另一优先 Mech 的请求”pilot，离线复用原件，未重发 6 RPC。正式行为 PASS 仍须核对官方接手规则在历史状态和时间下成立，不能把错过窗口算给交付者或把交付成功移给原优先者。

[发布 ABI](https://github.com/valory-xyz/autonolas-marketplace/blob/main/abis/0.8.28/MechFixedPriceNative.json)的原始事件是 `Request(address indexed mech,bytes32 requestId,bytes data)` 与 `Deliver(address indexed mech,address indexed mechServiceMultisig,bytes32 requestId,uint256 deliveryRate,bytes data)`，requestId 位于 data。`RequestToMarketplace` 等子图实体名不能当事件签名。

请求 digest=`0x6c146974cc83aa17e93e10b5e149a74cd6e84f582c8c9f03d8073ab540e2d313`，交付 digest=`0x7125a0708b5dfa73c9a1adc387c63ceb1e275175c7339b62c683ea064c9799fb`。官方客户端使用 `f01701220<digest>` CID；交付文件为 requestId 的十进制名。输入 CID 根路径实际返回 301，未自动跟随；301 原文明确指同 CID 尾斜杠目录，作为新固定目标读取后，目录确实列出 `metadata.json`，再只补这个文件。没有猜测 URL 或重复既有请求。

真实输入 `metadata.json` 的 `tool=factual_research`，原问题要求估计：LIV Golf 在 **2026-10-20** 是否仍为美国新泽西破产法院官方 docket 中 Chapter 11 程序的债务人，`p_yes`/`p_no` 各是多少。该问句的前提也只是输入声明，不是平台核实的法律事实。`request_context` 包含 `type=omen`、market=`0xf4004bb9ff8ded28d9f75443a0c95de00f8a1bc1`、`market_close_at=2026-10-21T00:00:00Z`。

真实交付是 JSON，`schema_version=2.0`、requestId 与链事件匹配、`tool=factual_research`、`executed_at=2026-10-16T10:49:06.690131Z`。`result` 本身是 JSON **字符串**：`{"p_yes":0.7,"p_no":0.3,"confidence":0.25,"info_utility":0.05}`。`prompt` 为 36608 字符的多阶段文本，`metadata.params.source_content` 保存搜索资料和页面；列出的法院材料是一般 Chapter 11 介绍及信用记录说明，另有律师文章和西弗吉尼亚家事规则，未见能定位该问题本案的 docket/case 号或已结算裁决证据。当前为 10-18，问题目标日与市场关闭日尚未来到，**不能判该预测准确**，更不复用 analytics accuracy。

目录 CID 指 UnixFS/DAG，并非文件 SHA256。首次读取阶段仅保留摘要和目录列名；随后根代理已独立验证该首个 pilot 的两份 CAR：逐块 SHA256、链上目录 digest、目录 filename link、UnixFS 重组字节均匹配；输入 824 bytes、输出 54144 bytes，各含目录/文件两块，6 个篡改块/错路径/错文件控制全部拒绝，离线命令 exit0、网络 0。原件 `runtime/olas-car-probe-20261018T063639Z-f01d6fd2`，核验结果 `runtime/olas-car-verification-20261018T064124Z-f938e88c`，纯规则与协议范围见 [ADR0007](../docs/adr/0007-ipfs-content-authentication.md)。这只验证首个 pilot，不能自动视作后续三条任务的 CID 都已验证。根代理因分工消息交叠多取得一次相同 delivery CAR，原件 `runtime/olas-car-probe-20261018T063832Z-57648fd4` 保留；这次是冗余读取，不算必要新证据，之后未重复获取。

上述首个 RPC/历史 pilot 由本探针新增 23 次免费 HTTP（含 1 次 301；此前官方资料 GET 与后续阶段另记），无重试、签名、付款、新任务或正式评分。原件均追加：

| 阶段 | 原件目录 | 命令退出码/结果 |
| --- | --- | --- |
| 身份 6 RPC | `runtime/olas-history-probe-20261018T060841Z-ff48df5e` | 0 |
| URI/桥映射/200 块窗口 6 读取 | `runtime/olas-binding-probe-20261018T061400Z-0673d417` | 0，窗口无事件 |
| 官方 first:1 定位 | `runtime/olas-history-index-20261018T061645Z-ea784124` | 0 |
| 两 tx/receipt/header | `runtime/olas-task-probe-20261018T061850Z-df04b19f` | 1，原优先 Mech 不同，原件保留 |
| 离线更正归属并尝试输入根路径 | `runtime/olas-task-probe-20261018T062055Z-45b84462` | 1，301 未跟随，仅新增 1 HTTP |
| 明确目录路径及交付文件 | `runtime/olas-cid-path-20261018T062232Z-577318c4` | 0，仅新增 2 HTTP |
| 补 metadata.json、复用全部已取得原件 | `runtime/olas-task-probe-20261018T062422Z-51a9a197` | 0，仅新增 1 HTTP |

首段 dry 命令退出码 0：

```powershell
.venv/Scripts/python.exe scripts/probe_olas_history.py --source-run runtime/candidate-check-20261018T055124Z-88e6eb13
```

最后完成命令（本轮已执行，exit0，新增仅 metadata.json 一次读取）：

```powershell
.venv/Scripts/python.exe scripts/probe_olas_history.py --source-run runtime/candidate-check-20261018T055124Z-88e6eb13 --identity-run runtime/olas-history-probe-20261018T060841Z-ff48df5e --binding-run runtime/olas-binding-probe-20261018T061400Z-0673d417 --task-index-run runtime/olas-history-index-20261018T061645Z-ea784124 --resume-task-run runtime/olas-task-probe-20261018T061850Z-df04b19f --content-run runtime/olas-cid-path-20261018T062232Z-577318c4 --request-metadata-file --execute-public-readonly --proxy http://127.0.0.1:7897
```

随后已完成以下较早任务和市场结算可行性阶段；本阶段不冻结预测准确率评分政策，不把多工具或同提供方不同专业名凑成不同 Agent。

## 固定日期前三条任务与已结算 Omen 市场

选择规则在读取输出前确定：同 Mech/service，`blockTimestamp < 1790812800`（严格早于 `2026-10-01T00:00:00Z`），按时间倒序，仅 `first:3`，不按预测好坏、是否与结算相符筛选。[Olas schema](https://github.com/valory-xyz/autonolas-subgraph/blob/main/subgraphs/marketplace/schema.graphql)将时间定义为 BigInt，[Graph 官方 API](https://thegraph.com/docs/en/subgraphs/querying/graphql-api/)提供 `_lt`。一次查询确实取得三条，之后各输入 CID 目录、metadata.json 和输出文件均免费取得；没有模型调用或新预测任务。

三者问题相同，原问题询问：法国 Seine-Maritime 当地官方记录的 2026 年海岸移民船渡尝试数，截至 2026-10-04 是否达到 60 次。`request_context.type=omen`，market=`0x00f6727ebdd4b473419d950e9e017ee454ea464b`，关闭时间 `2026-10-05T00:00:00Z`。三个 requestId 不同，但同一市场只对应一个结算事实，不算三个独立结算或三个 Agent。

| 时间顺序槽位 | 交付块（索引） | tool | 原始 p_yes / p_no |
| --- | --- | --- | --- |
| 1，最新 | 48517637 | `superforcaster_full_search_olas_predict_r1_14b` | 0.20 / 0.80 |
| 2 | 48517625 | `factual_research` | 0.85 / 0.15 |
| 3 | 48517618 | `superforcaster_full_search_olas_predict_r1_14b` | 0.35 / 0.65 |

这些是真实原件的差异，不是人为扣分或批内排名。本阶段未给三条任务逐一核 tx/receipt/历史控制和 CAR，故仍是预先查看过的 pilot，后续正式抽样应排除本市场，不以结果好坏改变顺序。

市场结算采用固定 N=48815687 的可信 RPC 读取，[Gnosis 官方工具配置](https://github.com/gnosis/prediction-market-agent-tooling/blob/main/prediction_market_agent_tooling/markets/omen/omen_contracts.py)与 Olas 作者部署资料给出 CT/Reality/Proxy 地址。逐项已核：

1. FPMM `conditionalTokens()` 为 `0xceafdd6bc0bef976fdcd1112955828e00543c0ce`，`conditionIds(0)` 为 `0x9127fb9df64c245d6f797df7c466f6ec7c858b9ea94ea462e6b042d207de33d7`。
2. CT `getOutcomeSlotCount(condition)=2`，`payoutDenominator=1`，`payoutNumerators=[0,1]`；不是尚未报告的零分母，也不是 invalid 的均分向量。
3. [Olas 当前 trader 默认公开入口](https://github.com/valory-xyz/trader/blob/main/packages/valory/services/trader_pearl/service.yaml)为 `https://omen.subgraph.autonolas.tech`；单市场查询按[作者 schema](https://github.com/protofire/omen-subgraph/blob/master/schema.graphql)定位 condition 的 oracle、questionId 与题干。首次多查的 FPMM.oracle 字段被实际 schema 拒绝，保留错误原件；删去该无用字段后新查询成功，未重复已成功项。索引给出的地址/标签随后由链上哈希绑定核实，未直接当结算证明。
4. condition 的 oracle 为 `0xab16d643ba051c11962da645f74632d3130c81e2`，questionId=`0x5304ab9c4f34e54a3be4e7ee01fa875acf9d8869ad8f87476aea4e32fc5650ee`。本地重算 `keccak256(oracle[20] || questionId[32] || uint256(2))` 精确等于 FPMM 的真实 conditionId。
5. Proxy 的 `realitio()` 为 `0x79e32ae03fb27b07c89c0c568f80287c01ca2e57`，`conditionalTokens()` 为上述 CT。Reality 在 N 的 `isFinalized(questionId)=true`、`resultFor(questionId)=1`。
6. 真实题干 `question.data` 包含 U+241F 分隔的完整问题、`"Yes","No"`、类别和语言；`getOpeningTS=1791158400`。按[Reality 2.1 源码](https://github.com/RealityETH/reality-eth-monorepo/blob/master/packages/contracts/flat/RealityETH-2.1.sol)重算 `keccak256(uint256(templateId=2) || uint32(opening) || 原始UTF8 data)`，得 `0x97aaab84b54c98da72d880d14a3d2f38821938a793bd37807bdea43f6aca2c7c`，与链上 `getContentHash(questionId)` 一致。
7. `template_hashes(2)` 与官方 single-select 原模板的 Keccak 精确一致。模板将 data 第二段按原顺序渲染为 outcomes，故 index0=Yes、index1=No；Reality 答案 1 与 CT `[0,1]` 一致，结论为**该 Omen 市场在 N 已结算为 No**。

该结论评价的是可追溯的市场 oracle 结算，不等于平台独立核实法国地方政府实际统计；不能只因概率 JSON 合法就给功能 PASS。正式指标、同市场相关样本的处理和样本门槛仍待新政策冻结，不复用 LP 政策或前端写死文案。

| 独立阶段 | 原件目录 | 新请求数/退出码 |
| --- | --- | --- |
| 固定 cutoff 的 first:3 | `runtime/olas-history-index-20261018T062851Z-cb462c54` | 1 / 0 |
| 三 CID 目录与三输出 | `runtime/olas-earlier-content-20261018T063015Z-a9e5cb5c` | 6 / 0 |
| 目录明确列出的三 metadata | `runtime/olas-earlier-metadata-20261018T063055Z-ef0e82e7` | 3 / 0 |
| FPMM/CT 固定状态 | `runtime/olas-omen-state-20261018T063311Z-2c9aa697` | 6 / 0 |
| Omen schema 实际字段拒绝 | `runtime/olas-omen-index-20261018T063411Z-552d01c5` | 1 / 1 |
| 单市场有效绑定线索 | `runtime/olas-omen-index-20261018T063452Z-8961fc7f` | 1 / 0 |
| 首 pilot 两份 CAR | `runtime/olas-car-probe-20261018T063639Z-f01d6fd2` | 2 / 0 |
| Reality/Proxy/题干/模板固定状态 | `runtime/olas-omen-oracle-20261018T064105Z-fa0f87ee` | 7 / 0 |

该阶段本方共新增 27 次免费读取；根代理分工交叠的 1 次 CAR 已单独说明，不隐去、不作为必要证据。未重跑已通过的工程用例；CAR 离线必要验收由根代理完成。

## 正式适配可复用字段与剩余证据

生产适配应使用操作者静态 profile 表达 chain/registry/agentId、Mech、serviceRegistry、可信 RPC 与政策；当前 `probe_olas_history.py` 是固定 2182 的已批准 pilot，不能把其硬编码复制为每个对象的独立实现。通用原始字段为 requestId、chain/block/hash/tx/index/log、原优先 Mech、实际 delivery Mech、service multisig、input/output CID 与文件路径、原始 tool/prompt/概率、市场 condition/question/outcome，以及各自观测时间和证据 hash。`executed_at` 是提供方声明，链上窗口以块头时间为准；真实 JSON 的 requestId 可能为大整数，后续共享类型须以十进制字符串对外。

已有可复用纯函数包括 `decode_event(..., expected_mech=...)`（原请求与实际交付分开）、严格 ABI 字符串/地址解码；CID 验证已进入纯 core。声明、背景采集、功能测量与行为槽位仍需正式政策区分，同一任务不跨分母复用。

尚缺的历史归属与行为字段，不能用当前状态替代：

- 在请求/交付区块核 `Mech.serviceId/serviceRegistry/getOperator` 与 `ServiceRegistry.mapServices(serviceId)` 的 multisig/state；如需解释直接交易 EOA，再核 Safe 执行 calldata/事件及当时 owner/threshold，不能把请求者、交易提交者或注册 Bridger 当实际 Agent 执行者。
- [官方 Marketplace ABI/源码](https://github.com/valory-xyz/autonolas-marketplace/blob/main/abis/0.8.28/MechMarketplace.json)提供 `mapRequestIdInfos(bytes32)`，返回 `priorityMech,deliveryMech,requester,responseTimeout,deliveryRate,paymentType`；其中 `responseTimeout` 是绝对时间。`getRequestStatus(bytes32)` 为 0不存在/1优先期/2过期/3已交付，状态 3 本身不证明谁原本被指定。
- 另一 Mech 接手须 **block.timestamp > responseTimeout**，恰好相等仍在优先窗口；还须满足官方 `checkMech`、支付类型一致、报价上限与未交付规则。应在历史区块核 map、请求 calldata/事件、真实交付者、服务权限、费用约束与块时间，不能仅凭 360 秒或成功 receipt 判完整履约。
- 当前 `ownerOf`、tokenURI、桥映射只证明 N 的身份关系。注册/桥接先后应从公开索引定位 `Registered` / `ServiceAgentLinked` 等实际事件所在块，再可信 RPC 核事件与块头；不能把当前关联前推到所有历史任务，也不盲扫巨大区间。是否允许评价注册前历史须由正式政策明确。
- 较早三任务的逐条 RPC 与 CAR 尚未完成；首个 pilot 的 CAR 成功只证明方法可行。正式样本排除已看 pilot 市场，按既定时间顺序与可核验结算资格选择，不以预测好坏筛选。未适配、缺少历史状态或 oracle 不能绑定时保留 UNKNOWN/待资料，不人为扣分或生成完整分数。
