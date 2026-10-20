# PancakeSwap V3 仓位读取 Checker v1

Checker `query.pancakeswap-v3-position` / `v1` 扩展 `service-contract-v1` 的来源校验，不改变原有 A 十槽、F 七个互异确定任务、B 七个互异确定任务、F/B 互斥及 30/40/30 权重。旧 `query.erc20-transfer-record/v1` 及其报告独立保留。

## 判据和任务

固定 BSC 56、PancakeSwap V3 NonfungiblePositionManager `0x46a15b0b27311cedf172ab29e4f4766fbe7f4364`，factory `0x0bfbcf9fa4f9c56b0f40a671ad40e0805a091865`。地址沿用已有 LP 核验及官方合约地址资料；独立 RPC 仅来自 `configs/generic-rpc.json`，不使用 Agent 提供的 RPC 或 pool 地址。

一次 positionId 查询为一个任务，任务键只由 Checker、链、NPM 和规范十进制 positionId 构成。更换端点、请求 ID、协议、字段或重复调用不会创造新任务。最多七个不同 ID，调用前冻结身份、发现原件、任务配置、适配器、零费用和请求预算；同一配置可供不同提供方各自独立评价。

执行计划先于独立 RPC 和业务请求。新采集 chain/head，使用 head 减 64 的确认块，核对 header、NPM/factory 非空代码、NPM.factory、positions 和 ownerOf。复用 `reputation_core.disclosure._position` 的严格 ABI 校验，包括数值位宽、规范 int24、非零有序 token 对和费率。参考有效且 owner 非零才允许对应业务调用。

只比较 positionId、token0/token1、fee、tickLower/tickUpper；Hallmark 输出中的 subject/position ID 与 chain 也必须与任务一致。规范业务事实与完整独立参考相同为 PASS，矛盾为 FAIL。网络、权限、付费要求、限流、未适配结果、RPC 错误、已 burn 仓位或缺少可用参考为 UNKNOWN，不记作 Agent 错误。文件缺失、SHA、身份、请求、端点、任务或重建报告被改动属于完整性错误，拒绝发布。

NFT 的 token 对、fee 和范围不可修改，适合以先验确认状态核验。liquidity、owner、pool 当前 tick、in-range、费用、价格和价值为动态字段，本版本均不评分。Hallmark 顶层 blockNumber 是单独并行查询，不能证明全部底层读取固定于此块；Brain measured_at 也不证明原子快照。不评价策略、收益建议、服务最新性或 Agent 的链上执行归属，不产生 B。

## 经审阅的协议适配器

适配器负责精确服务、Schema、输入和输出映射，核心判据不含 Agent ID 分支。

- Brain on BNB：认证登记的 `https://brainonbnb.com/mcp`，MCP 初始化、通知及工具发现通过后，只允许 `pancakeswap_position_look({"position":"<ID>"})`。当前 Schema 只有 position/address 两个 string 且禁止额外字段；不发送 address。源码调用链为 MCP → `/lp/look` → NFT/owner/factory/pool 读取；collect 仅 viem simulateContract/eth_call，不签名或广播。工具说明和实际响应均声明免费；返回的 tip、付款和计划链接不跟随。
- Hallmark：认证登记的 `https://hallmark-agents.vercel.app/a2a/rebalancer` 及当前 Card，只有无 pricing、无鉴权的 `analyse` 适配。只允许 A2A `message/send` 的 data part：skill=analyse，input={chainId:56,tokenId:"<ID>"}。不传 wallet、session、payment 等。公开源码的路由、invoke 和 analyse 只走 public client 的合约读取及本地确定叙述，不调用 ctx.execute/session/store；report、act、cycles、x402 和其他技能不在许可范围。

安全审阅原件：`runtime/cross-provider-checker-20261020/brain-source-review/REVIEW.md`、`hallmark-source-preflight/`。Brain 四个不可变 Git blob 和 Hallmark 十五个不可变 blob 的 Git SHA 已核验。它们提供精确白名单的审阅依据，不证明线上部署与公开源码逐字相等，也不授权未来新增技能。同名工具或 readOnlyHint 不能单独获得许可；Schema 变化、错误注册、收费或鉴权声明均拒绝匹配。IPFS 文档缺少内容认证时不匹配。

## 预算、来源重建和发布

业务阶段最多 28 个逻辑请求、七次业务调用、单次最长 45 秒、1 MiB 响应、零重试、零付款/签名/链写入/外部委托；整个通用接入至多 64 个逻辑请求。DNS/TLS/IP 固定、SSRF、代理及 RPC 白名单沿用现有网络控制。401/402/403/429 及顶层 JSON-RPC quota/rate-limit 错误保留主机停止记录，不换服务规避。派生参考无法构造时保留明确未发送记录，不伪造未知块请求。

Collector 与来源 Verifier 使用同一重建函数，从注册证明的完整依赖、当前发现原件、预冻执行计划、每个请求计划/观测/原始响应和静态 RPC 重新派生全部样本及能力元数据。正式发布逐字比较重建的身份、能力、样本、任务键与时间，不信任 Checker 自报 PASS、Agent 自报证明或两个服务之间答案相同。

存在少量真实 PASS 不代表 F 达到七个确定任务。证据不足保持 PARTIAL 和 null；无 B 不补零，不重分配权重，不产生完整综合分。常驻 Worker 保持 public-off；45 秒超时只能显式用于指定身份的 `--once` 评价。单次 Worker 前后核对队列和常驻进程，避免将其他作业当成本轮目标。
