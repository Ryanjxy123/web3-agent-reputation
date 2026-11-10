> 历史调查记录：2026-10-29用户已取消十对象目标。本轮四对象完成后停止新增实验，下文候选不再继续请求、付款或适配；当前状态以README和STATUS为准。

# 有限 MCP Registry 交易服务发现

本轮恰好 12 个公开请求：6 GET、6 MCP POST，无 RPC、钱包、密钥、付费、签名、提交或链写。所有请求经过 SafeHttpClient、显式 proxy7897、pinDNS 和进程级 DoH 1.0.0.1。原件与请求计划保存在 `runtime/mcp-registry-trading-discovery-20261029/`。本轮没有新增成交或完整评分对象。

| 服务与准确登记 | 实际结果 | 当前资格与共用协议路径 |
| --- | --- | --- |
| Quietwork：`dev.workers.quietworklabs.qw-swap/quietwork-swap@1.3.0`，remote `https://qw-swap.quietworklabs.workers.dev/mcp` | specific-version GET200；tools/list200，16 个工具。按真实 schema 发出一次 Base、USDC 0.1→WETH、sender/recipient 均为自有 SMA、slippageBps50 的 cow_build_order；HTTP200，但原生 `isError=true`、`token has no decimals(); not an ERC-20 on this chain?`，没有返回订单 | 准确注册及匿名声明读取可用；业务资格欠缺，不能因 HTTP200 称订单成功。其已声明 CoW quote/build/post/status 可复用通用 EIP712/UID/Trade 核验，appData 与费用须取它自己的实际原件；Kyber/0x 另可复用现有协议，但本轮没有这些方案，不猜响应映射。 |
| Cleave：`fi.cleave/swap@1.0.0`，remote `https://api.cleave.fi/mcp` | specific-version GET200。第一次 tools/list406 明确要求 Accept 同时支持 JSON 与 SSE；按该协议要求读取后200。一次明确 `readOnlyHint=true` 的 cleave_plan_swap 返回200、blocked=false，两个 unsigned CALL | **仅新增方案资格**。Base USDC100000 raw→WETH，声明最低42591278921154 raw，自有 SMA。精确 approve100000 给 `0xb08F28a3575805ee1E3729fc19Ab7E869CBAF563`，第二CALL同目标、value0、selector `0xab33b1ec`。尚缺 wrapper ABI/部署/内部路由/授权清理及独立净效果，不是已核可执行或成交。可复用 ERC20 exact-approval、固定块净效果、canonical receipt 和自有收款核验；新 selector 不能直接冒充已有 0x/Kyber。 |
| Paladin：`io.github.paladinfi/paladin-swap@0.1.0`，remote `https://swap.paladinfi.com/mcp` | specific-version GET200，remote tools/list 原件为 TimeoutException、无 body | 准确身份已找到；声明 schema、业务返回与协议都欠缺。本轮没有重试超时源、没有猜工具名或伪造业务调用。 |

三份数据型 `public-service-registration-proof-v1` 已按准确版本原件生成于 `identities/{quietwork,cleave,paladin}/registration-proof.json`，保留观察与正文的真实 SHA。它们证明的是具体官方 MCP Registry 命名空间/版本到 remote 的记录，不声称 ERC8004 链注册、独立运营信誉或真实履约。未运行新的评分 adapter 或登记核验测试。

Registry 的三次有界查询各仅一页100：swap 返回49、lifi12、defi53，均没有继续分页或广扫目录。lifi 页的 `xyz.tenzro/tenzro-lifi@0.1.0`、remote `https://lifi-mcp.tenzro.xyz/mcp` 是第三方 LI.FI wrapper 登记，不能移给第一方 `mcp.li.quest`；它本身是否当前真实可用仍缺业务原件。AgentSwap/ELSA 复用先前 phase11 原件：AgentSwap 检索无记录，ELSA 近名的骑行教练服务与交易 ELSA 无关。SafeRoute 本轮没有准确 MCP 命中，其既有 ACP 证明仍单独保留。这些是当前有限来源缺口，不是永久不可评价结论。

Cleave 的完整投影在 `cleave-plan-projection.json`：ERC20 approve 可独立标准解码；第二CALL前六个静态 word 与声明的代币、金额、最低值和自有地址相同，但没有 ABI 时只保存未验证 word 投影，recipient binding 仍 false。响应 validUntil=1793213836；word4=1793214976 的业务意义尚不能由猜测 ABI 确定。没有按旧60秒有效窗口发送任何调用，也没有复制上游文字指令执行。

官方版本原件对应 [Quietwork Registry](https://registry.modelcontextprotocol.io/v0.1/servers/dev.workers.quietworklabs.qw-swap%2Fquietwork-swap/versions/1.3.0)、[Cleave Registry](https://registry.modelcontextprotocol.io/v0.1/servers/fi.cleave%2Fswap/versions/1.0.0)、[Paladin Registry](https://registry.modelcontextprotocol.io/v0.1/servers/io.github.paladinfi%2Fpaladin-swap/versions/0.1.0)。优先后续定向核 Cleave 官方 wrapper；Quietwork 先核请求字段与服务器缺口，Paladin 保留声明缺源，不将三家写成三家均合格。
