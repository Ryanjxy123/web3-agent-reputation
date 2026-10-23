# 小额实交易：真实Agent评价可行性

日期：2026-10-23。当前task_id：`NOX_CONTROLLED_FIRST_JOB`，主线`NOX_ICLONE_BUYER_FUNDING_PREFLIGHT`，延续`SMALL_BUDGET_TRANSACTION_FEASIBILITY`。

用户取消对外材料请求，改自己参与小额真实交易。最新明确“预算先别管”，原30元暂不作为研究/准备的硬门槛；实际费用继续记录，具体充值与签名前说明金额、用途及权限。用户报告已花10元买币；owner登录、普通买方和DENY_ALL signer已准备，Base余额为0。协议登录与unsigned建单预检已成功，明确标记本次gas赞助；尚未签账户委托/UserOp、充值、建链上任务或新增评分。先完成两个真实外部Agent各一次闭环。

## 必须保持的边界

- **禁止发币是竞赛红线**：不部署/发行代币、不做Agent代币化、token launch，不发行项目币/声誉币，不把报告铸成NFT，也不为扩覆盖新发身份NFT。第三方CLI即使提供`tokenize`或链上身份mint，也不使用；接入若强制这些动作则排除。
- Nox虽同时声明Virtuals bonding路径，本次不得进入新币发行/首发或代币化流程；若未来现货试单成立，只选预先核实的既有资产和普通兑换路径。不能因为服务名叫swap就略过真实调用检查。
- 研究现有Agent对既有资产的业务操作，不通过我们直接调用DEX、自己部署两个样例或复制钱包地址伪装第三方履约。
- 原30元包含本金及全部成本的调查保留参考，已由最新“预算先别管”取代硬阻断；资金周转、服务费、gas、兑换和入金退出等费用仍如实核算，具体资金动作给用户确认。
- 先确认两个真实外部对象各能闭合一次任务，再确定共用判据和正式取样。原A10槽/至少8可判、7F及另一组7B不变；这是任务分配，不是必需14笔交易。只有查询F不能宣称兑换正确性已通过。

## 官方资料核查结果

| 路线 | 现有依据 | 本次预算与证据判断 |
| --- | --- | --- |
| Nox v2，`019e4f32-23d3-78eb-80bc-9545cdc49328` | [本轮官方详情API](https://api.acp.virtuals.io/agents/019e4f32-23d3-78eb-80bc-9545cdc49328)实际匿名GET200：Base `token_swap`、`priceType=fixed`、`priceValue=0.05`、`requiredFunds=true`、5分钟SLA；输入JSON Schema和交易hash/输出资产/原始单位数量的交付Schema齐全 | 固定服务标价已核实，但最低实际本金未公布，当前接单、实际交付及全部费用待核；要求金额>0不等于任意微额可执行 |
| iCLONE v2，`019eae06-96cd-77d0-8f8b-a6abb71f0cd7` | [本轮官方详情API](https://api.acp.virtuals.io/agents/019eae06-96cd-77d0-8f8b-a6abb71f0cd7)实际匿名GET200：`swap_base`、固定0.05、`requiredFunds=true`、30分钟SLA；输入要求和交付模板已取得 | 最低本金及全部费用尚未确认；其requirements/deliverable为字符串模板而非严格JSON Schema，需根据真实任务响应核实，不能声称已完成接口适配 |
| Wasabot #1048 | [官方身份页](https://app.virtuals.io/acp/agent-details/1048)；前轮API原件明确`open_position`最低10USDC | 杠杆业务不选；其它存取款能力也未证明多对象闭环，不因标价0.01就先开仓 |
| Zyfai个人Safe | [支持资产与最低余额](https://docs.zyf.ai/docs/sdk/supported-assets)给出Base/Arbitrum每账户10USDC最低额；[再平衡频率](https://docs.zyf.ai/docs/sdk/api/get-rebalance-frequency)及[规则](https://docs.zyf.ai/docs/product/intelligence/monitoring)显示低额低频且不保证发生操作 | 不适合30元含本金的两个对象试验。两个Safe也不自动等于不同公共Agent；不使用新发身份NFT来扩覆盖 |

费用只做条件下界：若Nox/iCLONE最终每任务报价均0.05USDC、各7F+7B全部采用付费兑换，两对象的服务标价合计`2×14×0.05=1.40USDC`。**这不是完整成本报价**，尚未包括独立A取样、DEX费、滑点、gas、入金退出成本及所需本金，因此不能据此承诺30元足够。若F可核另一项已声明的免费功能，可减少付费任务，但必须准确限定F覆盖，不为省钱改评分含义。

## 本轮真实预检与登录状态

固定官方客户端为`@virtuals-protocol/acp-cli@1.0.40`，NPM gitHead=`fbb7884480b7c757f8e77ab9ef1be46ac1c9a5be`，实际依赖SDK=`0.1.15`，官方API常量为`https://api.acp.virtuals.io`。工具仅安装在Git忽略的`runtime/nox-iclone-preflight-20261023/client/`，关闭安装脚本，未增加生产依赖。真实Node版本为24.13.0，使用显式7897代理及`NODE_USE_ENV_PROXY=1`；不沿用旧Node版本假设。

官方源码有重要边界：默认交互`agent create`可在signer设置后自动注册ERC-8004身份，不能使用；CLI `browse`也会要求signer，不能为了读资料授予它。经本轮真实GET验证，两实例详情API本身允许匿名读取，不需要登录或签名。SDK的认证前置不能直接推断后台所有详情都受保护，前轮“没有登录就取不到详情”的判断已由新证据修正。

已获得的规则：

- Nox输入为`fromContractAddress/amount/toContractAddress`；`amount`是人类单位，`slippageBps`用基点，默认300。本轮未接受其3%默认值。交付要求`txHash/tokenOut/amountOut`，输出数量是原始单位；请求本身没有显式recipient，须从真实任务/资金指令和回执绑定接收账户。
- iCLONE输入为小写`token_in/token_out`地址、`amount_in`人类单位和`recipient`；可选`slippage`为百分数。交付模板包含`tx_hash/amount_in/recipient`，未承诺输出数量字段，须独立查真实资产变化。
- 两者都要求另付本金；“固定0.05”不包括fundRequest中的资本。未创建job，尚无本人的完整budget和待签calls，不能给出30元全包结论。
- offering详情自身未明示币种，后经发布CLI/SDK核定：本次Base ACP服务费使用原生USDC，当前CLI不能改为USDT；任务预算由`AssetToken.usdc`构造，费币是部署级配置。requiredFunds本金是独立token/amount，可与服务费不同，但Schema接地址不等于该资产实际可执行。NOX/ICLONE `tokenAddress`是提供方项目币，无需购买。
- 两个精确UUID未出现在本轮各一次在线过滤语义搜索的top5结果中，返回结果还存在2999年的活动时间占位；这不能证明它们离线或在线。详情历史活动时间也不替代当前响应。没有反复搜索或通过付费任务盲探。
- Nox没有声明resource；iCLONE多数resource直接指向LI.FI、Coingecko等第三方。读取源站只能帮助报价/独立核验，不计iCLONE的服务可用性。

已审的官方split登录仅GET登录地址、之后交换owner会话；不创建Agent、邮箱、signer、身份NFT或交易。最初的`pending`不能证明用户没有登录：用户截图已显示授权成功，进一步诊断发现官方CLI会吞掉全部请求异常；原请求真实HTTP400、错误分类为invalid request。仅更换一次授权链接后，用户完成授权，token交换HTTP200，CLI明确返回`authenticated`。**当前登录已成功；没有充值、交易签名或资金动作。** 会话链接与凭证只留本地，不写入本文。

随后官方`agent list --page 1 --page-size 10 --json`实际HTTP200、`data=[]`，没有已有买方Agent钱包。用户随后指定优先欧易C2C/Web3路线，并报告已花10元买币；不能把owner登录钱包直接当CLI可下单的买方钱包。

登录后已确认可用的只读命令是`agent list --page 1 --page-size 10 --json`：使用owner会话GET本人Agent列表，不要求signer；JSON分支不会写Agent缓存。只输出身份、钱包和链等必要字段，完整响应和会话留本地。未过期会话为纯GET，CLI在会话过期时可能刷新token；不把它描述成交易签名。

**没有发现两家的独立预报价命令。** `create-job`会真正写链，不能拿它当免费报价探测；平台`trade --dry-run`也不是这两家Agent的报价。iCLONE声明的LI.FI quote可在取得真实买方钱包后作免费路由预估，但不包含Agent全部费用、接单承诺或退款条件，也不能替使用Kyber的Nox报价。若完整报价只能在创建任务后取得，须先明确该前置写入的gas、权限及可能损耗，再告诉用户，不能为取得报价悄悄发交易。

实际资金签名前还必须核对：服务费结算资产和精确金额、输入资产与本金、资金目标与输出接收账户、滑点和期限、预期最少输出、全部gas/入金/退出成本。`fund --amount`不代表本金与总费用上限；服务费与本金使用不同批准目标，禁止无限授权。显式保留买方evaluator，避免交付后跳过核验自动结算；服务费退款与本金escrow退款是不同路径，不把提供方退款声明当本金可自动取回的证明。新账户或任何待签calls若包含身份mint、tokenize或新资产发行即停止该路线。

上游小额可行性已实读两次SafeHttpClient GET，均HTTP200：Base现有USDC→WETH、输入1USDC。Kyber返回约0.00041687449 WETH、gas估计0.00414美元；LI.FI返回约0.00041598571 WETH、0.5%滑点时最低0.00041390578 WETH，gas估计0.0039美元、已包含的LI.FI费用0.0025USDC。报价只对应采集时点，LI.FI使用其公开provider钱包作为估算from/to，并非本人的实际任务；两个结果均不包含ACP任务交易、批准、智能账户、入金退出成本或两家Agent服务端条件，不作为Agent可用性或履约样本。没有签署或提交返回的交易数据。原件在`runtime/nox-iclone-preflight-20261023/upstream-route-estimates/`；参数含义见[Kyber官方API](https://api-docs.kyberswap.com/aggregator-api.html)与[LI.FI官方报价API](https://docs.li.fi/api-reference/get-a-quote-for-a-token-transfer)。

买方采用发布版JSON/no-signer create，平台记录、后端钱包和邮箱创建后即返回，客户端未进入自动ERC8004；普通交互create不使用。不能从客户端推出所有后台行为，故以实际回读身份字段为准。signer采用DENY_ALL，目标allowlist不等于金额上限，首次custom policy可能回退ACP_ONLY，不改策略绕过人工审批。

用户明确批准后普通JSON买方已创建，record/email均201，回读GET200且ERC8004AgentId/virtualAgentId均null、chains=[]，未调用mint/tokenize。随后经单独批准生成本地密钥并POST signer201；用户已官网批准，单次status=completed，实际policy读回DENY_ALL。Base固定块52975410的ETH/USDC均0、account code=0。私有原件为`buyer-*.private.json`和`buyer-funding-snapshot/`；不发布邮箱或秘密。

普通JSON create和首次signer准备分别被自动审批在CreateProcess前拒绝，均未执行。用户随后分别明确批准创建普通买方、生成密钥和提交逐笔审批请求，才重试同一已审路径并完成实际回读，未用其它接口绕过；不与create默认向导连用。

用户明确批准仅签`acp-auth:时间戳`协议登录消息及只读预检。CLI `wallet sign-message`会先启动SSE并额外登录签名，因此使用隔离SDK脚本。07:44UTC真实403/`APPROVAL_REQUIRED`，DENY_ALL在本账户连登录消息也要求人工审批，以实际结果取代消息免审批推断。用户官网批准后，从生产前端实际定义的owner GET `/wallets/approvals/{id}`读回200/approved，离线验签通过；恢复不需SSE或新签名。但首消息在排查期间过期，auth400明确`Message expired or invalid timestamp`。用户再次核对并批准新时间戳的同类登录消息后，GET200、离线验签、auth200、unsigned prepare200均成功，agent token存官方keychain，未输出或发布。原失败和成功收据分别留在`auth-prepare-2026-10-23T07-44-10.780Z.private/`、`resume-auth-prepare-2026-10-23T07-54-52.160Z.private/`、`resume-auth-prepare-2026-10-23T07-58-34.972Z.private/`；保留实际exit1与成功exit0。

官网只读审批GET的来源是[生产API模块](https://app.virtuals.io/assets/acb.api-D-OD_zxo.js)、[共享用户认证](https://app.virtuals.io/assets/user.api-4LAYrqSY.js)与[审批页](https://app.virtuals.io/assets/ApproveTransactionPage-BJbxJt2Q.js)，原件保存在`runtime/acp-approval-public-source-20261023T074716Z/`。不是猜测接口、重放签名请求或放开DENY_ALL。

## 建单预检结果与下一项权限

默认prepare返回两项尚未签署的请求：EIP-7702账户委托和本次UserOp执行签名；后者虽然标为`personal_sign`，也不是`acp-auth`登录消息。原始UserOp已离线解码、重编码逐字节核验：只有一次`execute`调用ACP的Nox `createJob`，provider/evaluator/FundTransfer hook及builder后缀与请求一致、原生value=0；没有资产转账、兑换、ERC20 approve或mint。

后台默认delegate为`0x77021100bD87b7008E5E1989d0eB38555d0d0000`（Alchemy v1.1.0），固定SDK0.1.15的签名常量为`0x69007702764179f14F51cdce752f4f775d74E139`（v1.0.0）。[官方部署表](https://www.alchemy.com/docs/wallets/smart-contracts/deployed-addresses)与[7702说明](https://www.alchemy.com/docs/wallets/transactions/using-eip-7702)确认两者来源与可显式选择版本；不能据此认定跨版本混签兼容。按官方`capabilities.eip7702Auth={delegation:ModularAccountV2,version:v1.0.0}`仅另作unsigned prepare。首次TLS建立前ECONNRESET，唯一重试HTTP201成功，delegate与SDK常量一致，`feePayment.sponsored=true`，返回的7702/UserOp均保持未签名。实际账户未委托、未广播。原件`version-pinned-prepare-2026-10-23T08-05-08.438Z.private/`。

本次赞助标记仅对应建单预检，不是已执行免费凭证，更不能推出fund、真实兑换和完成结算均免费。`maxAmount`为返回的估计字段，不当作实际扣款。当前不安排额外买ETH，也不给全包成本承诺。

指定版本的新payload再次按实际内容离线核对，命令exit0，结果为同目录`audit.json`：请求/响应SHA固定；外层execute、内层createJob、builder后缀与新到期时间逐字节匹配；7702的chain/delegate/nonce及授权hash、UserOp hash、personal_sign hash均独立重算匹配。没有调用网络或签名函数，不替代之后实际广播时的新鲜payload核验。

只读预检已完成；用户最新明确批准`NOX_CONTROLLED_FIRST_JOB`：Base专用买方采用Alchemy v1.0.0、仅Nox建单并发送1USDC→WETH/0.5%滑点需求取条款，不充值/付款/兑换。两项官网逐笔审批尚未申请，后续按批准范围准备新鲜payload；7702使专用买方账户采用指定智能账户代码，委托会持续到替换/撤销，并不只覆盖本次任务；UserOp则只执行核明的Nox建单。二者超出原登录签名许可，现已另获上述授权，但尚未实际签署。执行时先准备新鲜待签payload，人工审批并建单取真实条款；本金、付款、兑换与后续结算另核，不在本步自动执行。禁止发币/身份铸造保持不变。

## 当前优先：欧易入金与钱包辅助

用户已要求优先考虑欧易；将其作为可能的资金入口、钱包与记录查看工具，不更换Nox/iCLONE评价对象，不启动新的单对象评测适配。

- [欧易C2C官方FAQ](https://www.okx.com/zh-hans/help/what-is-p2p-trading-cn)写明平台交易费为零、人民币最低10元起；实际广告商限额、价格、本人资格及支付费用仍以账户所见为准。因此30元未被这项公开最低额直接排除，但不是全包可行结论。[C2C限额与安全保护](https://www.okx.com/zh-hans/help/c2c-buying-limit-and-security-protection-guide)另说明部分订单存在T+N提币限制，买到不等于可立即投入试单。
- [官方区别说明](https://www.okx.com/en-us/help/understanding-the-link-between-okx-and-web3-wallets)：交易所账户和自托管Web3钱包分别管理资产。欧易曾公告开放[USDC-Base](https://www.okx.com/en-us/help/okx-to-support-usdc-base)与[Base ETH](https://www.okx.com/en-us/help/okx-to-support-base-network)；钱包支持[Base 8453](https://web3.okx.com/onchainos/dev-docs/wallet/supported-networks)。公告不替代本人当前提币页。
- 优先核“可用资金→Base原生USDC→已确认的ACP买方钱包”的直接路径；若可直接提到正确买方地址，可省去先入Web3钱包再转出的中间一笔。需要本人钱包作收款或人工操作时再使用OKX Web3；它不能自动替代CLI要求的买方UUID/Privy钱包。USDT、原生USDC、桥接资产和链不能混同，不能靠选择网络把USDT变成USDC。
- **用户现已确认本人账户USDC提币可选Base**；此前无Base的清单属于USDT，不能拿来排除USDC。页面显示0.02USDC与约0.0199美元，暂记录为同一金额的两种显示、不重复计费，也不当作最低提币额。最低额尚未知，不要求为查信息先买币；用户已花10元计入记录。无需套用其它地区费用，不请求交易所API Key或私钥。
- 买方ACP调用的gas支付由后台prepare结果决定，本地源码既不证明默认免费赞助，也未要求先持有ETH；paymaster可能用USDC等付gas，不能把出现paymaster当免费。当前不安排额外购ETH，待实际签名前核gas支付方、代币扣款和总额。服务方兑换gas仍另核。
- 欧易可以帮助查看txHash；正式报告仍由可信RPC核任务→Agent执行→实际收款/资产变化。C2C收付款及本人钱包操作不计作Nox/iCLONE履约，也不发布私人支付信息。OKX OnchainOS/Agent Trade Kit是工具，不能据框架名称新增一个已评分公共Agent。

海外卡路线降为备用：[Coinbase当前文档](https://docs.cdp.coinbase.com/onramp/onramp-overview)标明旧Hosted Guest Checkout于2026-06-30停用，[Headless替代](https://docs.cdp.coinbase.com/onramp/headless-onramp/overview)有地区及应用条件，不用旧FAQ的游客费率承诺现在可付。[Crossmint Onramp](https://docs.crossmint.com/onramp/overview)支持Base USDC与银行卡，但适用地区、此卡受理、最低额及ACP最终手续费未核齐；虚拟卡发卡地区不替代实际居住资格。没有创建支付会话、尝试扣款或要求变更实名地区。

实际证据位于`runtime/nox-iclone-preflight-20261023/`（版本/原件、两个详情、两次在线搜索）及`runtime/acp-cli-source-audit-20261023T032723Z/`、`runtime/acp-two-provider-schema-research-20261023/`（固定源码）。一次试单仅能形成一个任务的证据，不冒充足量三维分。

## 自己使用服务能补什么

[官方ACP CLI](https://github.com/Virtual-Protocol/acp-cli)说明了浏览器OAuth、买方身份/钱包、服务发现、job状态及消息历史、需求和交付记录。我们作为真实客户，有机会保留原始要求、报价、资金请求、交付及完成/拒绝等状态，再通过RPC独立核真实执行。当前尚未验证这些具体provider的实际交付是否足以闭合。

CLI的普通账户/钱包、市场任务、链上身份注册和tokenize是不同能力，不能按默认全流程启用；只考虑必要客户端能力并逐项核实是否触及红线。其自带`trade`只是平台交易路由，不等于聘请Nox或iCLONE，不能拿来给这两个provider计分。支持testnet配置也不说明这些真实实例在测试网上接单。

现有平台只具查询/历史采集器，没有已验收的真实写任务采集器。本轮不预建自动签名器；若后续试单可行，先在官方入口由用户保留签名前任务要求并完成必要确认，平台负责采证与独立核验。多个对象闭环后才做最小通用适配。

## 下一步需要先核实的事实

1. owner/协议登录、普通买方、DENY_ALL signer及SDK匹配版本的unsigned建单预检已完成；账户委托与仅建单权限现已明确批准，下一步按官网逐笔审批后取得真实条款、本人欧易最低提币额/费用/锁定和后续全成本。详情和Schema不重采，不通过身份mint或放开权限解决接入问题。
2. 能否取得自己任务的原始要求、交付和执行账户/业务交易hash；Agent服务可用性是否有合法、可重复实测的入口。只有目录在线仍不足。
3. 取得每对象一单的具体报价及全部费用、资金流向、接收账户、期限和约束，再给用户明确充值与签名步骤；原30元不再阻断准备，但不以未知报价让用户先付款。
4. 两对象的低额任务证据闭合后，固定同一业务规则、独立样本和剩余预算，再决定完整评价。遇未知执行路径或费用超额停止依赖动作并说明，不为出分改门槛。

本轮为可行性研究和方向更新，生产代码、既有证据和评分未改，工程测试NOT_RUN。对外申请状态已改为取消、未发送。实际资金执行清单尚未形成，不声称已具备完整评分条件。
