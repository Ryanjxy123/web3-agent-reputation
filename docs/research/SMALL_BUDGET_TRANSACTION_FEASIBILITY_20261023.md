# 30元预算：真实Agent交易评价可行性

日期：2026-10-23。当前task_id：`NOX_ICLONE_AUTHENTICATED_QUOTE_PREFLIGHT`，延续`SMALL_BUDGET_TRANSACTION_FEASIBILITY`。

用户已取消对外材料申请，改研究自己作为客户参与真实交易，总预算30元人民币连本金一起。**当前没有开户、签名、充值、付款、发交易或新增评分。** 自己下任务有机会取得此前缺的原始要求、交付和完整任务状态，但付费不保证三维证据足量或业务正确。

## 必须保持的边界

- **禁止发币是竞赛红线**：不部署/发行代币、不做Agent代币化、token launch，不发行项目币/声誉币，不把报告铸成NFT，也不为扩覆盖新发身份NFT。第三方CLI即使提供`tokenize`或链上身份mint，也不使用；接入若强制这些动作则排除。
- Nox虽同时声明Virtuals bonding路径，本次不得进入新币发行/首发或代币化流程；若未来现货试单成立，只选预先核实的既有资产和普通兑换路径。不能因为服务名叫swap就略过真实调用检查。
- 研究现有Agent对既有资产的业务操作，不通过我们直接调用DEX、自己部署两个样例或复制钱包地址伪装第三方履约。
- 首轮总投入上限30元，包含本金、服务费、gas、DEX费用/滑点和入金/退出等成本；不是每对象30元。本金能否周转取决于实际交付和损耗，不按保证可退资金计算。
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
- 当前offering及详情未明示服务费结算币种，须核真实任务或可信链配置；不能直接把0.05写成已确认的USDC价格。详情里的NOX/ICLONE `tokenAddress`是提供方既有项目币，不是已确认的收费币，也不需要为评价购买它们。
- 两个精确UUID未出现在本轮各一次在线过滤语义搜索的top5结果中，返回结果还存在2999年的活动时间占位；这不能证明它们离线或在线。详情历史活动时间也不替代当前响应。没有反复搜索或通过付费任务盲探。
- Nox没有声明resource；iCLONE多数resource直接指向LI.FI、Coingecko等第三方。读取源站只能帮助报价/独立核验，不计iCLONE的服务可用性。

已审的官方split登录仅GET登录地址、之后交换owner会话；不创建Agent、邮箱、signer、身份NFT或交易。登录地址已通过对话交给用户，单次`configure complete`真实返回`pending`。**当前等待用户完成登录；无充值、签名或资金动作。** 会话链接与配置只留在忽略的私有runtime，不写入本文。后续先GET本人已有买方记录，再核必要账户/权限与单笔报价，不执行默认初始化向导。

登录后已确认可用的只读命令是`agent list --page 1 --page-size 10 --json`：使用owner会话GET本人Agent列表，不要求signer；JSON分支不会写Agent缓存。只输出身份、钱包和链等必要字段，完整响应和会话留本地。未过期会话为纯GET，CLI在会话过期时可能刷新token；不把它描述成交易签名。

**没有发现两家的独立预报价命令。** `create-job`会真正写链，不能拿它当免费报价探测；平台`trade --dry-run`也不是这两家Agent的报价。iCLONE声明的LI.FI quote可在取得真实买方钱包后作免费路由预估，但不包含Agent全部费用、接单承诺或退款条件，也不能替使用Kyber的Nox报价。若完整报价只能在创建任务后取得，须先明确该前置写入的gas、权限及可能损耗，再告诉用户，不能为取得报价悄悄发交易。

实际资金签名前还必须核对：服务费结算资产和精确金额、输入资产与本金、资金目标与输出接收账户、滑点和期限、预期最少输出、全部gas/入金/退出成本。`fund --amount`不代表本金与总费用上限；服务费与本金使用不同批准目标，禁止无限授权。显式保留买方evaluator，避免交付后跳过核验自动结算；服务费退款与本金escrow退款是不同路径，不把提供方退款声明当本金可自动取回的证明。新账户或任何待签calls若包含身份mint、tokenize或新资产发行即停止该路线。

实际证据位于`runtime/nox-iclone-preflight-20261023/`（版本/原件、两个详情、两次在线搜索）及`runtime/acp-cli-source-audit-20261023T032723Z/`、`runtime/acp-two-provider-schema-research-20261023/`（固定源码）。一次试单仅能形成一个任务的证据，不冒充足量三维分。

## 自己使用服务能补什么

[官方ACP CLI](https://github.com/Virtual-Protocol/acp-cli)说明了浏览器OAuth、买方身份/钱包、服务发现、job状态及消息历史、需求和交付记录。我们作为真实客户，有机会保留原始要求、报价、资金请求、交付及完成/拒绝等状态，再通过RPC独立核真实执行。当前尚未验证这些具体provider的实际交付是否足以闭合。

CLI的普通账户/钱包、市场任务、链上身份注册和tokenize是不同能力，不能按默认全流程启用；只考虑必要客户端能力并逐项核实是否触及红线。其自带`trade`只是平台交易路由，不等于聘请Nox或iCLONE，不能拿来给这两个provider计分。支持testnet配置也不说明这些真实实例在测试网上接单。

现有平台只具查询/历史采集器，没有已验收的真实写任务采集器。本轮不预建自动签名器；若后续试单可行，先在官方入口由用户保留签名前任务要求并完成必要确认，平台负责采证与独立核验。多个对象闭环后才做最小通用适配。

## 下一步需要先核实的事实

1. 完成官方登录后，仅GET本人已有买方与可访问任务记录，确认钱包和资金条件，再核报价可获得方式；登录本身不保证有最低本金和完整报价。详情和Schema已通过匿名GET取得，不重采。普通买方流程若强制发币或身份NFT铸造则排除，不通过新身份mint绕过。
2. 能否取得自己任务的原始要求、交付和执行账户/业务交易hash；Agent服务可用性是否有合法、可重复实测的入口。只有目录在线仍不足。
3. 取得每对象一单的具体报价及全部费用、资金流向、接收账户、期限和约束；核总预算内有退出余量。真实报价不足以证明30元可行时，不先充值碰运气。
4. 两对象的低额任务证据闭合后，固定同一业务规则、独立样本和剩余预算，再决定完整评价。遇未知执行路径或费用超额停止依赖动作并说明，不为出分改门槛。

本轮为可行性研究和方向更新，生产代码、既有证据和评分未改，工程测试NOT_RUN。对外申请状态已改为取消、未发送。实际资金执行清单尚未形成，不声称已具备完整评分条件。
