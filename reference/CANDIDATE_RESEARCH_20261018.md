# 下一批公共候选资料调查

日期：2026-10-18。先读过 CANDIDATES.md，未读取旧项目、调用 Agent 业务/RPC、创建任务、签名或付费。以下只记录官方文档和作者源码事实，不是测评结果。本轮新增完整三维就绪对象 **0**；优先继续核实 Custos，不将 Brain 的专业身份算作不同提供方。

## 优先线索：Custos，作者 0xMaxyz

**身份与主网部署是作者记录，尚未独立核链。** [主网部署文件](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/deployments/5000.json)列出 Mantle mainnet、chainId 5000、agentId 128、部署块 96604858。[README 的注册表](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/README.md#deployed-addresses)指向规范 IdentityRegistry，因此待核实的完整标识为：

```text
agentRegistry = eip155:5000:0x8004A169FB4a3325136EB29fA0ceB6D2e539a432
agentId = 128
YieldVault = 0xc4dc4Bc6e7bF61300747b017C08Ae86b63F08d3F
AgentBenchmark = 0xf1feCfc87fe4613AbCcd6B591884Ce12f272cb87
```

**有明确的匿名只读业务实现。** [服务路由](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/agent/src/server.ts#L159)公开 `GET /snapshot`，返回市场/仓位状态及风险上下文；[历史路由](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/agent/src/server.ts#L272)公开普通 `GET /decisions`，返回缓存链上决策。两者无调用方凭证或付款检查。不要传 `refresh=1`、调用 resync、调用模型问答或付费 `/risk-score`。

[Caddyfile](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/Caddyfile)明确域名和代理路径，故可供后续白名单审查的具体入口为 `https://trycustos.xyz/api/snapshot` 与 `https://trycustos.xyz/api/decisions`；均不需要业务参数。这是源码推导的部署入口，尚未业务请求验收。web 工具读取主页返回工具不可访问，没有取得 HTTP 状态，未重试，不能据此判服务失败。

**执行归属有设计，但仍缺实际样本。** [agent card](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/agent/src/identity/agentCard.ts#L38)将 `wallet` 明确定义为签署决策的 ALLOCATOR，另列 vault、benchmark 和 API；[部署文档](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/docs/deploy.md#0-prerequisites)要求执行者与 deployer 分开。部署文件里的 `0x77bD2F1cBcccdca1e63ca1B687E8b5d73710b0Ef` 只是 deployer，**不能当执行钱包**。

[decisionFeed 实现](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/agent/src/data/decisionFeed.ts#L227)从指定 vault 的 DecisionRecorded/Rebalanced/DeRisked 事件生成每条 `txHash`、`rationaleHash`、`decisionURI`。实际本轮未取得任何真实决策 txHash 或证据包；仓库 demo、单测和 fork 结果不算主网履约。feed 中部分风险标签由事件 kind 推导，outcome 默认零，缺块时间会回退当前时间，不能直接拿来当独立事实或收益成绩。

**可设计的独立判据：** 保留具体决策的原始输入、calldata、事件、固定区块状态和 decisionURI 字节；独立核算披露的资产变化、配置约束与摘要。snapshot 的 Ondo NAV、Aave/仓位状态须与相同历史状态对照；[snapshot 源码](https://github.com/0xMaxyz/Custos/blob/45a97e065f5d48f1875251a2b9f632d6b1a9fd4a/agent/src/data/snapshot.ts)有 15–30 秒缓存，不支持调用者指定固定 block，不能直接拿另一时刻报价判错。优先历史披露/执行窄范围，不评价“最优收益”“提前避险”或资金安全。

**决定性缺口与下一步：** 先核实际注册 tokenURI、注册文件到 API/ALLOCATOR/vault 的绑定，再取得普通历史查询里至少一条真实任务及 decisionURI，最后核链和独立输入。当前 card 源码仍注释其为 Custos 自定义 shape、需映射标准 registration-v1；不能因部署 JSON 有 agentId 就认为标准身份链已闭合。未过这几关不扩框架、不批量模型分析、不计入十个完整评分对象。

## 备选调查线：Olas Mech，不能把服务号当 ERC-8004 号

[官方客户端文档](https://stack.olas.network/mech-client/)给出 Gnosis 示例 serviceId **2182**、Mech `0xc05e7412439bd7e91730a6880e18d5d5873f632c`，同时明确 Olas serviceId 与 ERC-8004 agentId 是不同标识。注册发现入口为 `https://marketplace.olas.network/api/erc8004/gnosis/ai-agents/2182`；本轮 web 工具无法读取，无 HTTP 结论，未重试，完整注册 ID 仍未核实。

[官方发现路由](https://github.com/valory-xyz/autonolas-frontend-mono/blob/5d7ba82f7784fd3d1018f425b9c94d1036072bee/apps/marketplace/pages/api/erc8004/%5Bnetwork%5D/ai-agents/%5BserviceId%5D.ts)从登记关系输出 `registrations`，可能为空；提供工具和 benchmark 链接不证明已经注册或免费。operator 域名声明也不足以代替执行控制证明。

[Mech 作者说明](https://github.com/valory-xyz/mech/blob/main/README.md#off-chain-requests)区分了两条路径：新任务需要签名和预存付款，不调用；现有任务的 `GET /fetch_offchain_info` 可返回 `response` 与 `content_cid`，但每个实例的公开 base URL 必须从其 metadata 解析，off-chain 默认关闭。IPFS 交付内容可与实际请求/交付事件、requestId、指定 Mech 和服务 Safe 联合核验；不能把抢单者交付算给最初指定但未交付的 Mech。

目前未取得该实例的完整注册号、可匿名读的实际 base URL、真实 requestId/交付 CID 和可独立判真的工具输入。预测服务也不能仅因交付概率 JSON 就判预测正确；需已结算事实及事先固定的判据。现阶段是历史任务调查线，**不是已确认免费可测对象**，不借用 Olas 的 Karma 或官方 benchmark 分数。

## 暂不推进：Giza / ARMA

[当前作者 SDK/MCP 仓库](https://github.com/gizatechxyz/giza-hub/blob/main/README.md)明确前提是 Giza partner API key，列出账户、组合、APR 和交易读取接口；[早期 giza-agents](https://github.com/gizatechxyz/giza-agents/blob/main/README.md)也要求用户登录。这些不构成匿名免费许可。本轮官方资料未核实 ARMA 的完整 ERC-8004 标识、匿名公共业务入口或某个已注册 Agent 对应的原始历史任务。用户智能账户、充值和账户所有交易不能归为同一公共 Agent 的输出。先保留缺项，不生成候选假分，也不要求用户开户或付费来凑覆盖。
