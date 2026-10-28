# 同类真实交易Agent覆盖核查

日期：2026-10-28。状态：公开材料与可测资格核查中，尚未新增实验。

沿用transaction-agent-evidence-v3，综合30/40/30，未知不填0或100；同一任务支持A响应、F声明约束和B实际结果。扩展对象而不重设评分标准，不要求测完所有声明才能评价已测范围。

进入共同实验的依据：有来源的独立Agent身份与声明；确切可调用业务入口/参数/费用；能将本次意图、生成或执行的交易与可信链上回执、资产/授权/订单状态对应。链上历史可先复用，也可由已获授权的主动实验产生，不能要求预先拥有未来结果。仅有营销资料、支付交易或无法归属的DEX成交不算闭环。

先确认多个对象可用同一组能力判据和必要协议适配。未通过这一关口不新增业务付款、建单或资产操作；冻结共同任务后保留成功、失败、UNKNOWN全部结果。来源按时间/URL/原件SHA记录，不重复旧拒单试验，不把多个入口或同一后台的重复注册计作独立服务覆盖。禁止发币、tokenize、新身份/报告NFT。

后续核查结果追加在此；原件位于各runtime/candidate-review-20261028-*目录，不包含钱包秘密。

## 已核材料与资格

| 对象 | 身份/声明与接口 | 实际取得的材料 | 下一步 |
| --- | --- | --- | --- |
| Tator Trader | Base ERC-8004 #18132；链上data URI指向Quick Intel x402服务，官网同ID；自然语言任务返回待签transactions | 可信Base固定块ownerOf/tokenURI；官方accepted/health 200；未付款业务402明确0.20 USDC及Base资产/收款；完整输入/输出schema | 与SafeRoute共用首次方案试验；实际响应及交易协议仍待采 |
| SafeRoute | ACP UUID019fe1a3-ac02-7451-8253-50b4af6356cb；官方开发文档/manifest/直接quote均一致，402的payTo精确等于ACP钱包 | 公开详情、声明、直接POST /v1/quote未付款402（0.01 USDC）；返回quote/transaction/minBuyAmount/receipt等schema | 已核官方平台身份与业务通路，未取得ERC8004资料；不编造链注册ID；与Tator共同试取方案 |
| AgentSwap | 官方service agent元数据→MAS接口，registrations为空；多聚合器路由、用户签名模式 | 免费0.10 USDC→WETH请求HTTP200，真实OKX calldata/approveTarget及提供方模拟；原始输入已固定 | 作为第三个方案格式实例保留；官方链上注册/任务服务身份强度另列，不将OKX算第四个Agent，模拟需独立复核 |
| Hydrex Routing Agent | Base #54947，链上URI绑定ACP实例；get_quote完整schema | 可信链读与ACP详情；官方品牌直连health 200 | 直连品牌API未与该身份绑定；注册正文把钱包误写Registry，保留错误；不将requiredFunds=true解释为同意转本金 |
| TheSafeRouteBot | 与SafeRoute不同UUID/钱包/后端；ACP safe_quote及x402桥 | 官方schema、公共状态与桥费0.08 USDC | 桥仅EOA声明与现智能买方兼容性未核；不重复旧建单轮询，不改钱包权限 |
| Elsa | 官方Agent自然语言/任务API、业务健康200与未付款402 | 文档含pipeline/tasks/tx_data及用户回传txHash；未找到可靠注册身份 | 保留身份缺项；不借其它同名Elsa或替它发身份NFT |
| Silverback | Base #1156与Ethereum #13026同服务；链上data URI声明swap | 可信Base owner/URI已核 | 当前官方接口连接失败；保留扩展记录，不付款、不把两个链ID算两个提供方 |

链上注册统一在Base区块53187503 / `0x5d92df5ff4b921a1b219c24fff919bf27563c3214ebf2c8b412223525a07baca`核验，真实节点返回的owner/URI保存在`runtime/candidate-review-20261028-root/registry-read/`。标准Registry由操作者配置，不采信注册正文指定的其它地址/RPC。

Tator与SafeRoute具备不同稳定服务身份、明确的任务/输出协议及共同的买方签名交易取证路径，进入同类**方案pilot**资格；并非已证实接单成功、已成交或已完成三维评分。缺少旧交易历史可由此次授权实验取得，不以未来结果尚不存在否定可测性。ERC8004不是新加评分门槛；SafeRoute按真实ACP身份记载，后续来源适配不得伪造eip155编号。

## 首次共同任务（取得方案前固定）

Tator和SafeRoute各提出同一经济意图：Base原生USDC输入0.10、输出既有WETH、自有买方收款；不桥接、不托管、不创建代币/身份，不修改账户权限。Tator按公开字段填slippage=0.5（百分比）；SafeRoute没有声明可设置该字段，按它实际报价的minBuyAmount/时效核验，不虚构已接受0.5%条件。两家的请求格式不同，输出统一映射为链、资产地址/整数金额、买方、router/spender、calls、最小到账、费用及有效期。

本阶段先各取一个真实方案（当价合计0.21 USDC），不是消费上限；使用现有钱包/现有余额。付款前核现有权限/余额与x402签名兼容性，持久化唯一task_id、付款nonce与输入，单一资金操作者串行发送。只支付公开需求的确切USDC服务费；不把API收费交易当兑换。已发状态未知先核原nonce/回执，不为失败或超时换nonce重复付款。

每个同一任务都保留A完整业务响应与耗时、F意图/资产标识/费用/方案及独立模拟、B后续实际兑换回执与资产/授权。目录200、健康200或402不算A业务成功；提供方模拟不等于独立模拟。先核两家真实输出和路由共性再做必要的协议解码/来源适配，不复制Mango旧24/31槽父报告流程。首个pilot不冒充Agent全部功能评价；正常B仍要求真实目标结果，不能用保护退出替代。无需重跑Mango旧实交易与已通过工程测试。

共同三维指标、权重和UNKNOWN处理沿用ADR-0029，不以对象名称/预期分数特化。仅明确声明及已选任务范围进入F，未采声明不写成失败；服务与签名者角色明确，真实FAIL不隐藏。实际资产兑换前仍须解码核对并独立模拟方案，未知/不符或含发币/部署等动作立即停止该任务，不签其交易。

## 复用边界

`point_scoring.py`与SharedAssessment v3可直接共用；目前Mango来源接入仍依赖Spraay输出、特定Router02及旧父报告图，不能声称已经任意Agent即插即用。新适配只解决共同的EVM unsigned-plan格式/协议和有证据的身份来源，评分公式不改；原有31/34任务与旧报告不改。公开平台身份的支持须独立于评分逻辑；官方域名或API200本身也不能把任意工具变成Agent。
