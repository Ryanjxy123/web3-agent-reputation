# 小额实交易：真实Agent评价可行性

日期：2026-10-23。当前task_id：`SPRAAY_FULL_EVALUATION_DESIGN`，主线`MULTI_PROVIDER_TRADING_EVIDENCE`，延续`SMALL_BUDGET_TRANSACTION_FEASIBILITY`。

用户取消对外材料请求，改自己参与小额真实交易。原30元不再阻断研究/准备，用户已买币10元；本次实际充值、付费和资产兑换均0。EVM No Policy已读回生效，账户委托上链；先前一次建单因期限缓冲不足失败，独立核清后修正并成功创建Nox订单82141。真实需求已提交，约395秒观察仍无提供方报价/资金请求，订单期限已过，不向旧单付款。Nox观察已收口；用户随后明确授权继续iCLONE接单/报价/证据预检，需要充值再告知。iCLONE与Nox同属Virtuals ACP市场，是不同Agent；只建立零价值、gas赞助的swap_base订单及提交1USDC→WETH/0.5%滑点需求，不付款、充值或兑换。iCLONE随后观察30分45秒仍无提供方回复或报价，已停止。两者均未进入付费执行，不建议现在充值；真实兑换和两对象完整评价仍未达成。

## 当前：受控实交易实验与独立取证

当前主线改为主动实验与独立取证：用户提出先做一笔受控真实交易，由平台保存原始任务、报价与付款信息，独立核链和资产变化，再据结果评价。此方案可行；未充值、尚无样本只说明尚未验证，不能断言无法三维评分。不要求Agent预先返回全部评价材料或在首单前已有完整历史。覆盖优先及多对象可复用目标保持，单笔pilot先验证取证流程，不为单对象写评分规则。禁止发币/tokenize/身份NFT；当前按用户最新要求切换到无需XRPL钱包的交易Agent小额实验，先核现有Base/USDC路径与实际报价，费用明确后再通知充值。

当前task_id=`SPRAAY_FULL_EVALUATION_DESIGN`。用户最新要求完整评价Spraay全部声明，不能用单次兑换代表整体。已为公开六能力列服务可用性、独立功能判据及真实链行为实验；Spraay兑换/转账为生成方案、操作者签广播，预付计算额度则另有USDC存入/消费drawdown/退款链操作。AI/查询不伪造资产交易，API费支付不冒充业务完成；身份/入口与能力覆盖分别核清。当前先说明完整计划与费用范围，0.015USDC付费方案暂缓，未充值或动用资金。仍用固定三维、30/40/30与正式样本政策；六能力等权或改变分母尚未批准/实现。详细设计见[受控实验方案](../runbooks/CONTROLLED_TRANSACTION_PILOT_20261023.md)。

本轮已追加独立XRPL节点采证：操作者按XRPL官方公共服务器表固定xrplcluster.com，仅一次tx查询HTTP200/exit0。公开样本在validated账本107591208中Payment成功、实际到账3.347405XRP，与提供方收据差581drops；不是只靠Agent响应或区块浏览器。原件`runtime/controlled-pilot-xrpl-read-preflight-20261023T121227Z-f0bd1be9/`。此项说明我们可自行采集关键交易结果，尚未产生自己的真实付费任务；没有新签名/资金/业务交易，主应用工程测试NOT_RUN。

前一批询价已停止，目标未达成：新增三个真实交易服务、四个零付款订单，实际接单报价0、已确认可拿齐完整评价证据的对象0。ZeroAgent的82146、Ethy的82147，以及修正流程后的GSB 82148均在需求已获平台接受并记入同job历史后REJECTED，budget均null；原因只有bytes32哈希，明文未知，不能归因为余额、费用、请求文本或协议版本。GSB首单82145在我们发送需求前已拒绝，首次需求HTTP403；修正共用时序后只补做了一单，82148只提交标准requirement、无长文本询问，仍拒绝，因此不再重试这批对象。四单建单均经可信Base RPC独立核验；GSB首单拒绝另有独立链事件核验，其余拒绝以本轮已取官方任务历史为依据。未fund、支付服务费/本金、兑换、发币、身份mint或新增评分。详细时间、原件和失败路径见下方批次表及原件索引。

### 用户后续指定：先继续Virtuals，不转其他平台

用户随后明确询问Virtuals内可确认多少完整三维评分，并要求先试可行对象。本阶段沿用原三维、权重、样本门槛；先前“转Zyfai登录后预检”的待选问题已被这次指示取代。**已核查对象中完整三维可确认数量仍为0，不能把这个数说成Virtuals全平台的最大容量。** 目前取得真实免费业务报价的新增候选为N9T2一个，不能把它的ACP、REST、MCP入口算三个Agent。原有12个完整历史评分身份不代表新增Virtuals资产执行覆盖。

针对不同业务群体，新增一次桥接和一次转账目录查询，各top10，两次均200。结果去重17身份，其中14个未在前一批目录出现；并非17个已可评对象。固定核BridgeKitty、N9T2、Spraay及DevOps Butler四份详情，均200，不重复旧swap/recency目录循环。两家桥接的声明均含实际执行/回执路径，适合先作同协议预检；Spraay的requiredFunds=false不能直接当作“不执行”，也不能按execute名称认定代签。原件为`runtime/acp-bridge-transfer-discovery-20261023T112759Z-dd8d7ea2/`、`runtime/acp-bridge-transfer-details-20261023T112934Z-98e8b0c5/feasibility.json`。

| 对象 | 已实际取得的业务或历史证据 | 还不能给完整分的原因 |
| --- | --- | --- |
| N9T2 Bridge | 官方免费REST报价200；公开ACP81682收据200；可信Base RPC核付款/路由及历史getJob，provider匹配当前ACP钱包；XRPSCAN REST核实际XRP付款 | 原始用户需求/交付历史未公开拿到、收据有缺字段/数量不一致，正式样本未齐；独立XRPL RPC本轮已补到，可用主动实验补其余材料，用户尚无XRPL收款钱包 |
| BridgeKitty | 旧列表200、共150条engagement；固定取一条COMPLETED详情200，但原文被遮罩，signedReason实际为bridge_status查询；新报价单82150已提交需求 | 150条不能当150次桥接执行；不能由status查询、已完成协议订单或目录Schema证明真实代桥接；新单尚未报价 |
| Spraay Batch Agent v2 | 官方文档与实时x402 manifest可达，网关明确列服务费率 | 目录Agent与网关身份未绑定、由谁签广播未核齐，费用层级及真实任务→业务交易未闭合；没有实际业务结果 |
| DevOps Butler | swap_execute_guard有声明 | 免费资源为HTTP裸IP，不降低HTTPS/受控客户端边界；缺原始任务/tx契约，未调用或建单 |

N9T2官方来源为`https://x402.n9t2.com/llms.txt`，明确列出Virtuals的provider钱包`0x001f501a949454daba53bf6163b66a63fbae5925`；它另列的BNB ERC-8004 #375728为另一身份，不能替代ACP身份或合并计数。第一次免费报价只POST `/bridge/quote`，body为XRPL XRP→Base USDC、destination为已有专用买方、省略source_amount取实时最低档，不调用`/bridge/execute`或`/bridge/payment`、不签x402付款。返回quoted/executable=true，quote_id=`4613196e8ccfefc7edc726db5ec317691be31415eda2f94b2b8951bdaa3986d4`：输入5.018791XRP=转移3.568791XRP+服务费1.45XRP，预计目标4.440059USDC；创建11:35:01UTC、到期11:49:51UTC。报价已过期，不能用来付款；该方向也不表示我们持有XRP。原件`runtime/virtuals-n9t2-free-quote-20261023T113456Z-ff1ff18d/`。用户已回答没有XRPL自托管收款钱包，目前不创建钱包或要求充值，Base USDC→XRP方向不能填他人/占位收款地址。

N9T2公开样本独立预检：ACP81682的0.01USDC预算及FundTransferHook与当前provider在付款块`0x320cb01`匹配；客户实际付7.007337USDC本金，另付0.01USDC job费，USDC进入treasury后4.969134USDC用于路由。这里只核既有交易，没有动用我方资金。XRPSCAN提供的公开交易`95B077…B2AB4`显示Payment/tesSUCCESS，实际送达原收据目标地址3.347405XRP；这是当时的独立浏览器REST证据；本页当前段已追加直接XRPL节点validated核验。官方收据自身destination tx为null且数量写3.347986XRP，与链上差0.000581XRP（581drops）。保留该不一致，不拿收据自称settled当全链成功，也不在未固定判据/完整原始要求前直接判交易FAIL或给分。原件`runtime/virtuals-bridge-samples-20261023T113420Z-16d5c608/`、`runtime/virtuals-n9t2-independent-sample-20261023T113739Z-053e8f94/summary.json`、`runtime/virtuals-n9t2-job-binding-20261023T114238Z-cdeefc84/summary.json`。

两家新ACP报价试单均service-only、hook=zero、转账值0、gas赞助，不支付目录0.01USDC服务费：BridgeKitty82150（Base→BSC USDC报价）与N9T2 82151（与已成功免费报价相同的XRPL→Base参数）。前者首轮followup因API将zero hook表示null安全停止，需求尚未发送；仅修正静态service-only的null表示后，在可信RPC核原建单后恢复同一单唯一需求，没有重播或新建。后者使用修正后的共用流程，已立即提交唯一需求。BridgeKitty到期11:48:27UTC，N9T2到期11:58:30UTC；本轮不为卡片数量、满分或正式评分确认数重复轮询/重试。到期后两单最终只读均exit0，API仍OPEN、budget=null、history2条且provider回复0；已停止观察，没有重发需求或付款。不能因API未自动标EXPIRED就认定旧单尚可付款。

最终收口原件`runtime/nox-iclone-preflight-20261023/service-only-quote-closeout-2026-10-23T11-59-58.530Z.private.json`绑定23份来源SHA256，文件SHA256为`e3ff080ba720dcde94094dccd1a444f35560fe9cb3e9a8db71604f7c2503ee3f`。BridgeKitty最终history读取11:59:02.427UTC，N9T2为11:58:57.305UTC，均晚于原期限；各只读一次job/history、四个GET均200、命令均exit0。两次创建交易分别为`0x5f6615b34b335483b70831b1b6cb501e4117c7583102290ac938a30ab2e7f744`与closeout所列N9T2交易，可信回执确认深度当时分别71、22；没有为了提高确认数重新查链。这只证明建单，未获ACP接单/报价/桥接交付，不影响N9T2另一路免费REST报价成功的事实。所有观察已停止，不重试或延长。

私有operator的必要修改只支持这两个同协议service-only计划：静态来源绑定requiredFunds=false、hook精确zero，复用原createJob selector、provider/evaluator、赞助/nonce/唯一发送检查；报价约束不沿用旧USDC→WETH/50bps文案。API null仅在静态plan+intent均零hook的service-only允许，undefined、错误非零及fund-transfer的null继续拒绝。一次必要离线检查新模式，一次针对真实null表示失败的检查，均exit0；生产适配、评分规则、UI、数据库和历史报告未改。现有真实命令中首个模拟曾因误用client子目录路径找不到文件退出1，未发任何RPC；改准确路径后唯一实际模拟exit0，失败不隐藏。

本追加阶段复用既有账户，额外1次acp-auth登录消息签名、2个赞助零价值建单UserOp，没有新账户委托或fund/本金/服务费/兑换/mint。两次prepare、精确eth_call、独立6次RPC建单核验及恢复/最终需求读取均exit0；BridgeKitty首次resume的跟进因null表示退出1，既有广播已接受，按原单恢复需求，没有重新签名或重播；N9T2 resume+fast需求exit0。工具命令见前批相同命令名与上文准确新目录，Python脚本位于`runtime/nox-iclone-preflight-20261023/`、不是其client子目录。主应用工程测试NOT_RUN，不为文档收口重复测试。

Spraay的[实时manifest](https://gateway.spraay.app/.well-known/x402.json)200，列swap quote 0.008USDC、swap execute 0.015、batch execute 0.02、batch estimate 0.001，均不当免费报价；与ACP服务费是否重叠未知。gateway payTo与目录wallet不同且缺绑定，不当执行钱包；Base文案广播与unsigned/approvalRequired描述须以实际结果核清。其Peaq公开样例没有ACP任务绑定，也未RPC验证，不能拿来给该Agent计分。未安装会自动建钱包的MCP工具、未付费调用。3说明GET及2只读GET中，BPA页308未跟跳转、estimate缺参数400，整体exit1，保留原失败；原件`runtime/spraay-official-feasibility-20261023T115113Z-65d43972/feasibility.json`。

已有SDK只确认认证的`GET /jobs`活动任务、`GET /jobs/{chainId}/{jobId}`及`GET /chats/{chainId}/{jobId}/history`，没有已核provider历史过滤；SDK统一加Bearer不证明接口匿名公开或仅参与方，公开性UNKNOWN。未用我方owner session读他人聊天，也不猜路径枚举私人材料。TheMetaBot的免费arrivalFeed真实200但最新条目为8月、分类是提供方自报，不能把该自报分数/organic标签复制为平台结论；其purchase_execute仅留作代理采购/链上支付候选，没有接单或完整证据。首次sandbox对其两个资源ConnectError仅为环境限制；切换允许网络环境后一次arrivalFeed200，原失败不归Agent故障。原件`runtime/virtuals-live-evidence-sources-20261023T113003Z-abda49e8/`及`runtime/virtuals-metabot-network-recheck-20261023T113049Z-c9c2d7f8/`。

### 前一批三家实际询价结果（UTC，已收口）

| 服务 / 订单 | 真实流程及结果 | 能否安排充值 |
| --- | --- | --- |
| GSB `dca_buy` / 82145 | 官方索引创建10:42:56.109、历史创建10:42:56.126，历史拒绝10:43:03.757；我们的首条需求随后HTTP403，没有送达。拒绝另以可信Base RPC事件核实 | 否；无接单、预算或报价 |
| ZeroAgent `swap` / 82146 | 首次官方索引暂未返回job，安全停止后只恢复同单读取，未重建/重播。10:58:44.800需求入历史、10:58:50.934询问入历史，10:58:52.216拒绝 | 否；budget=null，无原始交易交付 |
| Ethy AI `swap` / 82147 | 11:00:30.263创建，11:00:31.364需求入历史、11:00:31.771询问入历史，11:00:37.944拒绝 | 否；budget=null。其声明的本人swap查询资源另实读HTTP404，不等于有可导出历史 |
| GSB `dca_buy` / 82148 | 修正共用时序后唯一补单；11:08:42.482创建、11:08:45.284标准需求入历史、11:08:49.731拒绝。没有追加长询问 | 否；budget=null；停止该批重试 |

四个createJob的链、买卖方、目标合约、JobCreated及EntryPoint内层执行成功均经可信RPC核验；只证明订单创建，不证明业务执行成功。GSB首单的拒绝额外独立查链，其余三单拒绝来自已保存的官方job/history，不冒称额外做过拒绝交易RPC核验。三个provider均未返回明文原因，不能把拒绝哈希推断成“先充值就能用”，也不据此给正式FAIL或完整分。

新四单原件目录依次为`runtime/nox-iclone-preflight-20261023/`下的`createjob-approvals-2026-10-23T10-42-09.179Z.private/`、`createjob-approvals-2026-10-23T10-55-01.287Z.private/`、`createjob-approvals-2026-10-23T10-59-20.232Z.private/`、`createjob-approvals-2026-10-23T11-06-28.924Z.private/`。离线批次清单`quote-trials-closeout-2026-10-23T11-19-57.082Z.private.json`绑定49份来源文件SHA256，清单SHA256为`24ceedbd1e6e33206a395c6f2f99d6702891d6664b501782d63f1a8267b74d0b`；不含签名、令牌或带凭证RPC URL，继续保留在忽略目录。

共用私有operator只修正已实际遇到的问题：建单后在同一进程核官方回执并发送唯一requirement，索引短暂`data:null`只作有界只读等待；先持久化意图，不自动重试消息POST或广播，不换request_id恢复未知提交。官方回执仅供同job链下消息关联，独立RPC随后完成，未降低支付或评分门槛。GSB补单采用官方最小流程、无长文本，仍拒绝；不能把所有失败归因于额外询问。未形成新的生产适配或评分规则。

部署兼容性调查只核到以下事实：[官方部署表](https://os.virtuals.io/acp/overview)与SDK的FundTransferHook地址不同，但本轮npm官方最新版本仍是0.1.15，包完整性核对一致；可信Base固定块52981153实核两个hook均有代码、core白名单为true且绑定同一ACP。不能据地址差异认定SDK失效，也不能据白名单推定provider实际兼容。8次RPC的原件`runtime/nox-iclone-preflight-20261023/hook-preflight-20261023T103403Z/`及证明`hook-preflight.private.json`保留，未盲改合约地址或升级依赖。

### 其他渠道与证据可得性

| 渠道 | 本轮实际观察 | 当前限制 |
| --- | --- | --- |
| ACP额外在线目录 | 一次20条现货执行搜索；仍有2999年占位活动时间 | 没有新增可证当前接单的执行者；calldata生成、分析和建议不能冒充代执行 |
| ACP近期链上群体 | 固定块52981325向前10000块，12个JobCreated，排除我方旧2单后10单/6个provider；逐一详情核验 | 全为研究、图像、QA等，0个明确现货执行服务；其中5单与运营方自测钱包有关，不能宣称真实外部交易需求 |
| ACP旧协议公开历史 | GSB历史列表200，但选定swap详情一次超时；Zero列表/选定详情200，但交付被遮罩且为研究任务 | 未拿到可用的原始交易要求→执行→结果闭环；旧完成记录不能证明当前新协议接单 |
| Bitte CoWSwap / Uniswap AI Agents | [官方目录](https://github.com/BitteProtocol/awesome-bitte)列出的两个部署首页本轮均HTTP402，Vercel返回`DEPLOYMENT_DISABLED` | 属部署停用，不能当x402收费报价或已接单；两者原本为钱包辅助生成交易，亦须区分Agent规划和用户签名 |
| Giza | [官方迁移说明](https://www.gizatech.xyz/blog/giza-world-migration-guide)指出ARMA/Pulse退役；[当前SDK](https://github.com/gizatechxyz/giza-hub)要求联系取得partner key，activate要depositTxHash | 不按旧产品名凑两家；按用户不联系他人的要求暂不推进API路线。费用、最低额与原始决策导出未核齐 |
| Zyfai | [当前Getting Started](https://docs.zyf.ai/docs/sdk/getting-started)指向[Dashboard](https://sma.zyf.ai)取得SDK Key，用户另需SIWE；首次sendDeposit才分配Safe/session | 未开户、未取得Key/用户会话，最低额/费用/实例级原始任务导出未实核；不能保证先零资金创建两个可评执行实例。两个Safe也不等于两家提供方 |

Bitte两次首页观察原件`runtime/bitte-deployment-homepages-20261023T111114Z-5e73776a/`；Ethy本人查询资源404原件`runtime/ethy-swap-status-20261023T105848Z-34fd4dd0/`。Zyfai文档本次未列强制身份NFT铸造，普通Safe不是身份NFT；仍需逐步核实际流程，若强制发币/身份铸造即排除，不为取得资格先入金。

### 实际命令与验证范围

私有工具位于`runtime/nox-iclone-preflight-20261023/client/`。新四单按各自目录运行`node request-createjob-approvals.private.mjs --provider <gsb|zero|ethy>`、`python simulate_createjob_call.py <目录> --provider <key>`、`node resume-createjob.private.mjs <目录> --provider <key>`，GSB补单及后续使用`--quote-only-followup`；prepare与精确eth_call均exit0。首个GSB发送需求因拒单HTTP403退出1；Zero首次发送后跟进因索引`data:null`停止退出1，发送已被接受的原UserOp没有重播，随后恢复原单成功。其余广播/快速跟进exit0。

`python verify_createjob_receipt.py <目录>`四次均exit0，每单6次可信RPC；正式评分所需确认门槛未在本轮宣称达成，也未为出分继续轮询。`node send-createjob-requirement.private.mjs <目录> --provider <key> --read-only`终态读取exit0，后续无消息发送。GSB首单拒绝独立查链exit0。Ethy资源404、Bitte两个部署402的采集命令exit1，保留真实失败，不写成通过。必要私有operator语法/AST及关键离线分支检查已执行并通过；主应用工程测试NOT_RUN，没有生产代码、评分、数据库或报告修改，不为文档提交重复测试。

前一批额外1次既有ACP登录消息签名、4次零价值赞助建单UserOp；没有新增账户委托、fund调用、服务费、本金支付、兑换、代币发行或身份mint。此前Nox/iCLONE两单仍作为无报价历史保留，该阶段累计六个成功创建的未付费订单（本页后续两单后累计八个），不能计成六个可用Agent。

## iCLONE本次订单与证据口径（前轮历史）

iCLONE订单`82142`观察已收口：唯一sponsored/零转账建单交易`0x3a87a41bd31ea897644f0d1d62ed8b394815e82b157b9cbc58d9a977166cf552`，可信Base RPC、EntryPoint内层成功及唯一JobCreated已核。1USDC→WETH/0.5%滑点需求于09:22:59.882UTC提交一次，最终09:53:44.829UTC（北京时间17:53:44）仍API OPEN/budget=null、history2条、provider回复0；观察1844.947秒，记录deadline09:53:10已过。未确认接单、真实报价或完整评价证据，不能解释为已收费服务违约或直接计FAIL。已停止轮询，不向过期旧job充值/付款，不重复需求或建单；fund/服务费/本金转出/兑换/发币/身份mint/新评分均0。原件`createjob-approvals-2026-10-23T09-20-09.034Z.private/QUOTE_OBSERVATION_COMPLETE.private.json`。

iCLONE是Virtuals ACP市场上的独立服务Agent，Nox是另一提供方；Virtuals ACP是二者使用的交易任务协议/市场，不是这两个Agent本身。本次实时官方详情GET200与此前声明一致，原件`iclone-detail-20261023T091622Z/`。服务价0.05为挂牌值，实际预算/本金资金请求、路由gas及总充值需求均须等真实响应；不把上游LI.FI报价充作iCLONE报价。

| 三维证据 | 本次已取得 | 仍需取得 |
| --- | --- | --- |
| 服务可用性 | 当前公开声明、真实客户建单与一次需求发送 | Agent本人认证回复/接单及响应时间；平台建单成功不等于Agent可用 |
| 功能声明一致性 | swap_base声明、输入资产/金额/recipient/滑点的固定请求 | 本人同job交付及真实兑换输出；amount_in JSON类型未获正式Schema保证，不能因接口歧义直接计业务FAIL |
| 交易行为可靠性 | 仅本方建单回执与业务字段绑定 | 任务资金请求/实际执行授权和执行钱包归属、提供方交付tx_hash、可信Base receipt及USDC/WETH正确合约资金流、确认距离；不能把本方建单交易计作Agent兑换 |

iCLONE交付模板未承诺amount_out/minOut；若后续执行，到账量需独立查链，0.5%滑点需与当时对方报价/minOut基线比较。一次试单只核证据通路，不替代既有A10/F7/B7门槛或产生完整分。工程主应用测试不重跑，私有operator仅必要JS语法/Python AST检查与离线交叉审阅。

充值前仍需核清协议兼容性：官方当前[部署表](https://os.virtuals.io/acp/overview)列Base FundTransferHook为`0x90717828D78731313CB350D6a58b0f91668Ea702`，本轮固定SDK0.1.15使用`0x0EaD25150985Bce0B4925c54E4ee1D856381A86B`。该SDK本身会正确识别本轮hook；提供方实际运行版本未知，不能证明兼容，也不能据此认定本轮无回复的原因。未经真实资金请求/版本核对，不修改活跃job的hook、不重建订单、不付款。另已离线确认`acpV2AgentId=null`是迁移关联字段缺值，不能推断对象必为legacy；官方CLI仅显式`--legacy`才切旧路径。

异步业务还存在方法边界：现有A政策的同步访问延迟不能直接套30分钟交易SLA，且SLA未证明就是付款前报价期限；后续若多对象证据闭环，须明确异步A采样口径并保留原维度/门槛。当前没有新增评分政策，不将轮询同job计作多次独立服务机会。

本轮真实命令均exit0：`node request-createjob-approvals.private.mjs --provider iclone`、`python simulate_createjob_call.py <原目录> --provider iclone`、`node resume-createjob.private.mjs <原目录> --provider iclone`、`node read-createjob-status.private.mjs <原目录>`、`python verify_createjob_receipt.py <原目录>`、`node send-createjob-requirement.private.mjs <原目录> --provider iclone`。目录为上文准确basename，均在既有私有工具环境运行。共6轮job/history读取（初始1、root一次、独立观察4次）均成功，未重发需求；最后一轮覆盖30分钟和deadline后时点。必要operator语法/AST检查及离线审阅通过；主应用工程测试NOT_RUN，生产代码/数据库/评分未改。四份项目文档作本地检查点，不push，私有runtime及无关演示稿不入Git。

## 必须保持的边界

- **禁止发币是竞赛红线**：不部署/发行代币、不做Agent代币化、token launch，不发行项目币/声誉币，不把报告铸成NFT，也不为扩覆盖新发身份NFT。第三方CLI即使提供`tokenize`或链上身份mint，也不使用；接入若强制这些动作则排除。
- Nox虽同时声明Virtuals bonding路径，本次不得进入新币发行/首发或代币化流程；若未来现货试单成立，只选预先核实的既有资产和普通兑换路径。不能因为服务名叫swap就略过真实调用检查。
- 研究现有Agent对既有资产的业务操作，不通过我们直接调用DEX、自己部署两个样例或复制钱包地址伪装第三方履约。
- 原30元包含本金及全部成本的调查保留参考，已由最新“预算先别管”取代硬阻断；资金周转、服务费、gas、兑换和入金退出等费用仍如实核算，具体资金动作给用户确认。
- 先确认两个真实外部对象各能闭合一次任务，再确定共用判据和正式取样。原A10槽/至少8可判、7F及另一组7B不变；这是任务分配，不是必需14笔交易。只有查询F不能宣称兑换正确性已通过。

## 早期官方资料核查结果（预算与可用性以本页最新结论为准）

| 路线 | 现有依据 | 本次预算与证据判断 |
| --- | --- | --- |
| Nox v2，`019e4f32-23d3-78eb-80bc-9545cdc49328` | [本轮官方详情API](https://api.acp.virtuals.io/agents/019e4f32-23d3-78eb-80bc-9545cdc49328)实际匿名GET200：Base `token_swap`、`priceType=fixed`、`priceValue=0.05`、`requiredFunds=true`、5分钟SLA；输入JSON Schema和交易hash/输出资产/原始单位数量的交付Schema齐全 | 固定服务标价已核实，但最低实际本金未公布，当前接单、实际交付及全部费用待核；要求金额>0不等于任意微额可执行 |
| iCLONE v2，`019eae06-96cd-77d0-8f8b-a6abb71f0cd7` | [本轮官方详情API](https://api.acp.virtuals.io/agents/019eae06-96cd-77d0-8f8b-a6abb71f0cd7)实际匿名GET200：`swap_base`、固定0.05、`requiredFunds=true`、30分钟SLA；输入要求和交付模板已取得 | 最低本金及全部费用尚未确认；其requirements/deliverable为字符串模板而非严格JSON Schema，需根据真实任务响应核实，不能声称已完成接口适配 |
| Wasabot #1048 | [官方身份页](https://app.virtuals.io/acp/agent-details/1048)；前轮API原件明确`open_position`最低10USDC | 杠杆业务不选；其它存取款能力也未证明多对象闭环，不因标价0.01就先开仓 |
| Zyfai个人Safe | 早期[支持资产与最低余额](https://docs.zyf.ai/docs/sdk/supported-assets)调查给出Base/Arbitrum每账户10USDC；[再平衡频率](https://docs.zyf.ai/docs/sdk/api/get-rebalance-frequency)及[规则](https://docs.zyf.ai/docs/product/intelligence/monitoring)显示低额低频且不保证发生操作 | 原30元现不作为准备阻断；当前最低额与费用需在新流程实核。两个Safe不自动等于不同公共Agent；不使用新发身份NFT扩覆盖 |

费用只做条件下界：若Nox/iCLONE最终每任务报价均0.05USDC、各7F+7B全部采用付费兑换，两对象的服务标价合计`2×14×0.05=1.40USDC`。**这不是完整成本报价**，尚未包括独立A取样、DEX费、滑点、gas、入金退出成本及所需本金，因此不能据此承诺30元足够。若F可核另一项已声明的免费功能，可减少付费任务，但必须准确限定F覆盖，不为省钱改评分含义。

## 本轮真实预检与登录状态

固定官方客户端为`@virtuals-protocol/acp-cli@1.0.40`，NPM gitHead=`fbb7884480b7c757f8e77ab9ef1be46ac1c9a5be`，实际依赖SDK=`0.1.15`，官方API常量为`https://api.acp.virtuals.io`。工具仅安装在Git忽略的`runtime/nox-iclone-preflight-20261023/client/`，关闭安装脚本，未增加生产依赖。真实Node版本为24.13.0，使用显式7897代理及`NODE_USE_ENV_PROXY=1`；不沿用旧Node版本假设。

官方源码有重要边界：默认交互`agent create`可在signer设置后自动注册ERC-8004身份，不能使用；CLI `browse`也会要求signer，不能为了读资料授予它。经本轮真实GET验证，两实例详情API本身允许匿名读取，不需要登录或签名。SDK的认证前置不能直接推断后台所有详情都受保护，前轮“没有登录就取不到详情”的判断已由新证据修正。

已获得的规则：

- Nox输入为`fromContractAddress/amount/toContractAddress`；`amount`是人类单位，`slippageBps`用基点，默认300。本轮未接受其3%默认值。交付要求`txHash/tokenOut/amountOut`，输出数量是原始单位；请求本身没有显式recipient，须从真实任务/资金指令和回执绑定接收账户。
- iCLONE输入为小写`token_in/token_out`地址、`amount_in`人类单位和`recipient`；可选`slippage`为百分数。交付模板包含`tx_hash/amount_in/recipient`，未承诺输出数量字段，须独立查真实资产变化。
- 两者都要求另付本金；“固定0.05”不包括fundRequest中的资本。仅详情调查时尚未创建job；随后两个试单及其观察结果见本文当前状态，尚无提供方完整报价，不能给出全包成本结论。
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

以下为已批准的建单阶段范围（当前转入`NOX_SIGNER_AUTOMATION_SETUP`）：Base专用买方采用Alchemy v1.0.0、仅Nox建单并发送1USDC→WETH/0.5%滑点需求取条款，不充值/付款/兑换。两项官网逐笔审批随后已完成，旧任务过期未发；后续自动策略进度见下方最新段落；7702使专用买方账户采用指定智能账户代码，委托会持续到替换/撤销，并不只覆盖本次任务；UserOp则只执行核明的Nox建单。二者超出原登录签名许可，已另获上述授权且随后由用户官网批准；旧job恢复401、过期未广播，见下方最新进度。执行时先准备新鲜待签payload，人工审批并建单取真实条款；本金、付款、兑换与后续结算另核，不在本步自动执行。禁止发币/身份铸造保持不变。

最新执行进度：fresh Nox建单与两项签名请求已在`createjob-approvals-2026-10-23T08-18-28.852Z.private/`保存，用户均已官网核对批准。恢复在首个owner审批GET即HTTP401，未进入广播、无SEND_INTENT；原job窗口已于08:24UTC到期，不发送旧call，也不盲重建。官方CLI随后通过现有会话恢复完成只读策略核查：08:25UTC signers/global均200，当前仍DENY_ALL，ethereum全局另有ACP_ONLY；返回只有名称/ID，没有细则或金额限制。

用户已明确要求取消持续人工审批、由助手按约定范围判断。此前`NOX_SIGNER_AUTOMATION_SETUP`阶段：用户进一步询问双链No Policy，最新建议仅本次专用实验买方EVM选No Policy、Solana保持Deny All；尚待用户实际完成和读回，不把咨询当作已切换。No Policy也作用于未来充值；截图说明Virtuals Only包含tokenisation，两个选项都不能代替本地禁发币检查。不重建钱包/密钥。CLI `agent set-signer-policy`只能指向官网，真实变更须owner Privy会话，不能用P256 signer自行提升权限。ACP_ONLY不等于仅Nox或1USDC，现有custom接口也只有目标地址白名单；金额、资产、provider、selector及禁发币由本地operator逐笔核，不冒称后台硬限额。本次仍只获准账户委托与Nox建单/需求/取条款，不充值、付款或兑换。策略变更后准备新鲜UserOp，不使用过期建单；旧7702签名只有在chain/delegate/nonce及恢复验签完全匹配时才可能复用，不能当已上链。原签名/会话/策略响应均留忽略目录。

最新策略已生效：用户已官网将EVM改No Policy，08:39UTC官方CLI同一signer读回policyIds=[]。原件`policy-read-2026-10-23T08-39-20.534Z.private/`。随后执行`NOX_CONTROLLED_FIRST_JOB`（最终观察已收口见下文），其余业务权限仍仅建单/需求/取条款，不付款或兑换。原生keychain实际环境中owner/agent会话均仍有效；沙箱内读取为空不能当作丢失。

## No Policy后的真实执行

Nox订单`82141`已真实创建并观察收口：No Policy自动签名/单次提交、可信Base RPC、EntryPoint内层成功及唯一JobCreated均已核；交易`0x9b2ff0a28423834cf4b5ab609f2f88ffc556b06b7f72b210c2741389fe883b26`。北京时间16:58:51唯一提交1USDC→WETH/50bps需求，最终于17:05:26（北京时间）只读观察结束（原件以UTC时间戳为准），观察395秒，仍OPEN/budget=null、仅创建与我方需求2条、provider回复0。设定到期时间已过，不向旧job付款，不重复需求或对Nox反复建单；不能据此认定已收费服务违约或直接给Nox FAIL。未fund/支付/资产兑换，原件`createjob-approvals-2026-10-23T08-56-20.984Z.private/QUOTE_OBSERVATION_COMPLETE.private.json`。本次只证明平台接入流程跑通，Nox实交易可行性仍未确认。

此前唯一广播的旧UserOp因ExpiryTooShort失败，已6次可信RPC及独立事件解码确认无JobCreated；7702委托已实际生效，旧操作不能重播。修正为5min原SLA+180s准备缓冲，签名前/提交前剩余>330s；新calldata先经确切eth_call成功，再构造唯一发送。源于接入流程，不计Nox FAIL；旧失败原件与新成功原件均保留，未改评分规则。

当前推进边界：无需XRP钱包，不恢复N9T2或前轮过期旧单。已实际创建Spraay82153和VEGETA82154并独立查链，12:45UTC观察均OPEN、budget=null、历史2条；尚无本人接单报价，不无限轮询或重复建单。已实取Spraay直连0.015USDC费用要求及官方六能力源码；具体身份绑定、部署一致性、全部费用和授权边界须按实验核实。下一task_id=`SPRAAY_FULL_EVALUATION_SCOPE_AND_COST`，先按完整范围制定共用判据、复用有效观察并列费用，不把全部源码声明当已验证能力，不改变旧分数或直接上新生产计分方案。实际付费和资金动作仍按明确方案授权。

## 本轮三家候选的声明初筛（实际询价结果见上方）

等待iCLONE期间追加1次官方在线过滤搜索，HTTP200、20条记录；原件`runtime/acp-swap-search-20261023T093827Z-32086f52/`。20条lastActiveAt全部为`2999-12-31T00:00:00.000Z`，不能据此证明活跃或据online标签开始付款。保留3个明确声称现货执行的后备对象，其余17个包括只给calldata的Hydrex均不冒充执行者。该初筛阶段未建单；本轮随后给三家创建了四个零付款询价单，均拒绝，未适配或充值。

| 候选/公开ACP UUID | 服务/挂牌原值 | 充值或适配前的明确缺项 |
| --- | --- | --- |
| Ethy AI / `019d87e1-f0d3-7a6c-b273-08729fc85b6e` | swap / fixed 0.5 / requiredFunds=true | 输入符号与数值金额；交付仅result:boolean，未承诺txHash、滑点或独立收款地址；所谓Butler用户钱包归属待核 |
| ZeroAgent / `019df9a9-db36-701b-8659-86283716ab21` | swap / fixed 0.4 / requiredFunds=true | 输入token和字符串金额；交付仅string，未承诺txHash、滑点或收款地址；Bankr/0x执行链需原件证明 |
| GSB Wallet Profiler and DCA ENGINE / `019d756c-9eba-7600-81ba-f1c78f43277c` | dca_buy / fixed 0.25 / requiredFunds=true | 可指定既有tokenAddress、USDC数额和maxSlippagePct；声明txHash/输出/滑点等，但资金进入、真实输出归属、是否需其钱包预置资金待核；不自动预充值 |

三个候选的目录ERC-8004字段均null，ACP UUID不是ERC-8004身份，链上注册/执行授权尚须核实。价格字段本身未明示币种，不能仅凭原值报全包充值数。此表保留声明及缺项；后续真实拒单不改变它们原本的功能声明，也不证明可完整评分。不可测原因与原件保留，当前不做生产适配。

## 资金入口参考：欧易入金与钱包辅助（尚不安排充值）

用户已要求优先考虑欧易；将其作为可能的资金入口、钱包与记录查看工具。当前评价对象已按最新要求更换调查，不再固定Nox/iCLONE；先有至少两个真实接单报价及完整证据通路再确定入金，不启动新的单对象评测适配。

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

现有平台没有已验收的生产真实写任务采集器。此前不预建签名器的准备阶段已结束；本轮仅在忽略的私有operator中按既有授权签ACP登录及零付款询价，没有生产适配。付费或资产操作仍先核具体条款、签名前要求及授权，多个对象闭环后才做最小通用适配。

## 下一步：按受控实验准备，不再以缺公开历史否定可评性

1. 单笔实验方案已准备；读方案中三维判据、平台自采证分工和实际资金执行单，不再重复选择生态或绕回Zyfai。
2. 核我们自己的源/目标账户、可信只读节点和任务关联；历史资料只辅助预检，不要求Agent先提供全部未来结果。用户没有XRPL收款钱包，具体准备方式仍待确认，本轮不生成密钥。
3. 用真实收款地址取得新有效报价，给用户明确的本金/费用/gas/地址/签名内容；获具体授权后才执行单笔交易。旧报价/过期订单均不付款。
4. 首单先产生有原件的三维观察，保留成功、失败和UNKNOWN，验证完整取证流程；后续按群体与正式计划扩样，不把一单记为长期100分，不跨正式F/B分母重复计入。

本轮只更新实验设计及只读准备，主应用工程测试NOT_RUN、既有分数未改；资金/新密钥/真实新业务交易/新评分均未执行。
