# 四聚合来源的路由归属与最小解码资料

本阶段仅整理官方公开入口与已有原件。状态为 **AWAITING_ACTUAL_INNER_TARGET**：尚未收到本轮 OPENOCEAN / OKX / KYBERSWAP 报价中的实际内部地址、selector 与固定区块，不提前适配全部路由，不将文档候选地址加入执行许可。

## 已确认的官方入口

| 请求 source | Base 官方地址线索 | ABI / 已验证源码入口 | 当前可复用范围 |
| --- | --- | --- | --- |
| ZEROX | AllowanceHolder `0x0000000000001ff3684f28c67538d4d072c22734`；Settler 随官方部署注册表变化 | [0x 官方源码与部署说明](https://github.com/0xProject/0x-settler) | 现有 AllowanceHolder `exec` / Settler `execute` 与已列出的 action；不由历史 Settler 地址推断本轮部署 |
| OPENOCEAN | `0x6352a56caadc4f1e25cd6c75970fa768a3304e64` | [官方部署表](https://docs.openocean.finance/docs/contracts)、[官方 ExchangeV2 源码](https://github.com/openocean-finance/OpenOceanExchangeV2) | 已确认文档归属；等待实际 target/selector 后只核命中版本 |
| OKX | 文档当前 exact-in router `0x67d03631fe51b741c0c00c4e16eb662ac84381df`；approval 合约另为 `0x57df6092665eb6058de53939612413ff4b09114e` | [官方合约及 ABI 入口](https://web3.okx.com/onchainos/dev-docs/trade/dex-smart-contract)、[官方 ABI 目录](https://github.com/okxlabs/Web3-DEX-Router-EVM-V1/tree/main/DexRouterabi) | 已确认文档归属；exact-out 文档地址 `0x77449ff075c0a385796da0762bcb46fd5cc884c6` 为另一入口，不用于本轮 exact-input 适配假设 |
| KYBERSWAP | MetaAggregationRouterV2 `0x6131b5fae19ea4f9d964eac0408e4408b66337b5`；另有 KSAggregationRouterV3 `0x6868d319c8c9a78f7d39dc3602c5c917315132d7` | [已有 commit 固定的 Kyber 官方部署表](https://github.com/KyberNetwork/kyberswap-documentation/blob/869880b7643e28fbb6e94bb74026ab29d2e0db3d/developer-guide/aggregator-api/contracts.md)、[V2 已验证源码](https://basescan.org/address/0x6131B5fae19EA4f9D964eAc0408E4408b66337b5#code) | 优先复用已有 V2 `swap` ABI；不能将 V3 地址与 V2 结构互换 |

OKX 官方文档明确区分交易 router 与批准地址，并提醒部署表和 API 返回可能不同步。因此上表是核验线索，实际 calldata 的 target 必须逐个对上部署与固定块代码证据。OpenOcean 官方部署表和官方源码仓库均列出相同 Base 地址。没有调用任何报价 API 或付费业务接口。

## 本机可直接复用的材料

- `runtime/protocol-verified-20261028-hydrex/`：代理与实现的 explorer 原件、`contract-abi.json`、`implementation-abi.json`、`source-contracts__router__HydrexMultiRouter.sol`、`explorer-runtime-code.json`。已保留代理 `0x599bfa1039c9e22603f15642b711d56be62071f4` 与实现 `0x2e5e3d3fbfb77df85b3535fbefa09d61a8320aac`。该 explorer 摘要中的 `independent_rpc_matched=false` 原样保留，不改写为本轮链上匹配。
- `runtime/protocol-verified-20261028-kyber/`：`basescan-abi.json`、已验证 V2 Solidity、commit 固定的官方部署表及 `review-receipt.json`。已有函数 `swap((address,address,bytes,(address,address,address[],uint256[],address[],uint256[],address,uint256,uint256,uint256,bytes),bytes))`，selector `0xe21fd0e9`。旧审阅记录提到 flags 的 `0x200` 未归入当时已知 mask；不能仅因 ABI 可解码就假定全部 flags 的执行语义已覆盖。
- 现有纯解码模块 `services/platform/src/reputation_platform/unsigned_swap_protocol.py` 已处理三种协议结构，Hydrex 包装层 selector 为 `0x68128618`。本阶段不修改该模块。
- 上述关键文件的本地 SHA256 与记录范围见 `runtime/protocol-routing-review-20261028/existing-artifacts.json`；地址线索与待核状态见同目录 `router-bindings.json`。

## 收到实际内部调用后的最小核验

1. 从同一冻结任务的原始服务交付中提取外层及内部 target、selector、完整 calldata、chain_id；保存原件摘要。`source` / `origin` 字符串只是服务数据，不能单独证明路由归属。
2. 仅为实际 target 取得对应官方部署记录及已验证 ABI / 源码，固定仓库 commit 或原件 SHA256。解码后重新编码必须与原 calldata 一致；不明 selector 或不支持的动作保留为未适配。
3. 在操作者可信 RPC 的同一个固定区块保留 `eth_getCode(target, tag)`、区块号与区块哈希；若是代理，另保留实际实现槽与实现代码。将代码字节的 **Keccak-256** 与已验证 deployed-runtime 比对，并记录编译器、metadata、immutable/link reference；不能用网页源码文本的 SHA256 充当 runtime hash。新 target 的这部分证据本阶段均 **NOT_RUN**。
4. 按协议核输入/输出资产、整数数量、授权 spender、真正收款人、最低输出及最早有效期限。Hydrex 内部收款人应是包装合约，外层收款人才是本次任务指定账户；输出协议费及 referral 从净到账约束中分开核对。
5. 只扩展实际命中且源码足以解释的结构。OKX 的 packed token / receiver / fee bits 需按命中 ABI 版本展开；Kyber 的 executor、approveTarget、flags、receiver 与 permit 分别核；0x 需同时核 AllowanceHolder 和实际 Settler 的官方部署归属，不能把 approval 地址当执行目标。

ABI 与部署绑定通过后，固定块完整模拟仍是 F 证据；只有经确认的真实交易、回执、事件及前后资产/授权状态满足同一任务才构成 B。缺少适配或部署证据记 UNKNOWN/未适配，不自动判提供方 FAIL。本阶段只执行公开文档 GET 和本地材料读取，没有钱包、签名、广播、付款、业务服务探测或新 RPC 调用。

## 当前待输入

等待负责人提供本轮实际返回的 `task_id / source / wrapper target / inner target / selector / calldata 原件路径 / 固定区块`。收到后仅追加命中地址的公开绑定与原件，不继续无目标抓取其它版本。
