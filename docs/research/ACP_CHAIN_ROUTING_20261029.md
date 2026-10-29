# ACP接单链、协议与活跃性核查

日期：2026-10-29（北京时间）。任务范围：解释D01–D06在Base新ACP合约建单并提交需求后仍OPEN/budget=null的可能原因，核实是否统一迁移Robinhood4663；只读，不新增业务请求、签名或资金操作。

## 结论

**没有证据支持“六家已统一迁移4663、Base下单一定错误”。** 官方当前SDK同时支持Base与Robinhood的ACP合约；CLI创建任务仍默认8453，显式使用调用者给定的chainId，不从`chains.active`或`acpV2AgentId`自动选择接单链。六家中Simon、OUWIBO甚至没有4663记录；Pinchy、Simon的Base `acpV2AgentId`分别是20449、1403，并非全部null。Hydrex、TheSafeRouteBot的该字段为null，却已在本项目Base新合约真实报价交付，反证该字段可单独判断新旧接单协议或是否支持Base。[当前CLI固定源码](https://github.com/Virtual-Protocol/acp-cli/blob/9d2be827cc19e4ea2cecfff3896398607537ea3e/src/commands/client.ts)

**个别服务只监听4663仍是可成立的假说，公开目录不能证明或排除。** SDK的SSE/Socket会发送`x-supported-chains`，来源是运行端provider adapter的实际支持链，不是目录`chains`字段。若提供方自行只配置4663，可能影响实时消息分发；本轮没有读取任何提供方私有配置或实际连接头，不能把这个机制推定为六家当前配置。应通过其正式运行声明或按链可认证的近期任务交付验证，而非改链重下同一单。

**本次没有取得两个新增、近期活跃交易provider的完整证据。** 官方搜索的未来日期、历史累计成功率及主页宣传都不足以证明当前接单。公开旧任务API超时、区块浏览器403及公共RPC429分别留证；不能据这些平台/资料故障判Agent失败。六个未付款任务保持原UUID与原状态，不换链重试、不重付、不因暂时空预算下调分数。

## 当前SDK与CLI：已核实是最新发布版

官方npm当前`@virtuals-protocol/acp-cli`为1.0.40、`@virtuals-protocol/acp-node-v2`为0.1.15，与本机安装一致。本轮下载官方SDK tarball作为数据，核对npm SHA512 integrity，并逐字节核对constants、acpAgent、SSE、Socket、API client、EVM adapter六个安装文件，全部相同；没有安装、执行远程代码或更改依赖。[CLI发布元数据](https://registry.npmjs.org/@virtuals-protocol/acp-cli/latest)、[SDK发布元数据](https://registry.npmjs.org/@virtuals-protocol/acp-node-v2/latest)

| 项目 | Base8453 | Robinhood4663 | 依据 |
| --- | --- | --- | --- |
| 新ACP合约 | `0x238E541BfefD82238730D00a2208E5497F1832E0` | 相同地址，但属于另一链实例 | SDK `ACP_CONTRACT_ADDRESSES`；不能因地址相同混淆链 |
| FundTransfer hook | `0x0EaD25150985Bce0B4925c54E4ee1D856381A86B` | 相同地址、不同链实例 | SDK `FUND_TRANSFER_HOOK_ADDRESSES` |
| 新CLI任务链 | `--chain-id`默认8453 | 显式给4663才使用4663 | `client create-job`直接向`createJobFromOffering(chainId, …)`传参 |
| 实际运行端监听 | provider adapter `getSupportedChainIds()` | 同左 | 发送`x-supported-chains`；目录不展示实际连接头 |
| 旧协议兼容入口 | 显式`--legacy`，SDK旧Base配置 | 当前CLI旧兼容器仅支持Base/Base Sepolia | `LegacyBuyerAdapter`及`resolveLegacyConfig` |

旧兼容器使用`@virtuals-protocol/acp-node`、`https://acpx.virtuals.io`及Base旧合约`0xa6C9BA866992cfD7fd6460ba912bfa405adA9df0`；新SDK使用`https://api.acp.virtuals.io`及`0x238E…`。**协议选择与接单链选择是两个独立维度。** 不能把旧协议Base入口误称Robinhood迁移，也不能从SDK包名中的v2、前端agentVersions中的v2/v3和代码注释中的v1/v2推定它们是同一个版本编号。CLI不会自动探测旧协议，只有显式`--legacy`走兼容器。

本轮没有调用旧兼容器、创建旧协议任务或向任何新链发交易。旧来源是否允许同一已批准买方直接调用、实际资金机制和身份归属，仍须按root冻结的具体任务核实。

本地原版源码快照与原始路径/SHA在`runtime/acp-chain-routing-20261029/local-sources/source-review.json`；最新包对照收据为`latest-sdk-integrity.json`。GitHub当前CLI提交为`9d2be827cc19e4ea2cecfff3896398607537ea3e`，创建任务代码与本次抓取main正文一致；npm发布gitHead另保留原值，不混称同一commit。

## 六个候选的元数据反证

数据复用2026-10-28已取得的官方detail原件，未再对这六家发业务请求。各`chains`中的`active`都是静态目录标志，不能当作运行进程在线证据。

| 对象 | 目录链与Base关联ID | 官方detail `lastActiveAt` | 能否由元数据确定只在4663接单 |
| --- | --- | --- | --- |
| PinchyMeow | 4663 active；8453 active、acpV2AgentId=20449 | 2026-08-18 14:31:43.987Z | 不能；Base记录与legacy关联ID均存在 |
| Clawpump | 4663 active；8453 active、关联ID=null、ERC8004#60748 | 2026-08-11 05:54:14.094Z | 不能；缺实际运行端支持链 |
| SimonAgent | 仅8453 active、acpV2AgentId=1403 | 2026-04-29 10:02:43.941Z | 没有4663记录支持该解释 |
| OUWIBO AGENT | 仅8453 active、关联ID=null | 2026-06-16 13:46:44.076Z | 没有4663记录支持该解释 |
| Opet | 4663 active；8453 active、关联ID=null | 2026-09-07 14:03:14.019Z | 不能；缺实际运行端支持链 |
| ArmaBase | 4663 active；8453 active、关联ID=null、ERC8004#60504 | 2026-09-20 04:54:14.040Z | 不能；缺实际运行端支持链 |

以上旧日期应降低“已有当前接单证据”的信心，但不等于Agent功能失败或永远不能评分。相同UUID在此前搜索结果的`lastActiveAt`统一为`2999-12-31`；这不是可用于近期排序的真实业务时间。新搜索即使带`isOnline=online`仍会返回未来值，故online标签也需要独立任务交付对照。

官方`/agents/legacy/20449`与`/agents/legacy/1403`均指回Pinchy、Simon同一UUID及同一钱包，但正文`offerings=[]`，只证明关联映射存在，不能证明其正在旧协议运行。[Pinchy映射](https://api.acp.virtuals.io/agents/legacy/20449)、[Simon映射](https://api.acp.virtuals.io/agents/legacy/1403)

D01–D06最新已知读取为`batch/read-20261028T161019528780Z-78af2e/summary.json`：job82379–82384、各两条记录（建单事件及我方requirement）、OPEN、budget=null。尚无提供方条款/付款/本金或交付；本轮没有把预付款前的等待时间直接认定为服务履约超SLA。

## 官方活跃数据：取得了什么，未取得什么

当前官网前端公开JS实际使用：

- `/agents/search?query=…&agentVersions=v2,v3&topK=…&metadata=true`，而旧CLI搜索没有附带agentVersions和metadata；联合结果会出现旧数字ID与新UUID，不能统一按新UUID协议建单。
- `https://acpx.virtuals.io/api/metrics/agents`及`/api/metrics/agent/{id}`，支持历史volume、successfulJobCount、lastActiveAt等；前端还描述past7d字段。[当前前端搜索模块](https://app.virtuals.io/assets/acb.api-D-OD_zxo.js)、[当前metrics模块](https://app.virtuals.io/assets/metrics.api-CaRgCNyk.js)
- 旧公共任务列表`/api/agents/{id}/engagements`，可取得原任务ID、phase、时间和交易线索；它与新合约的`/jobs/{chainId}/{jobId}`不是同一后端协议。

本轮按这些已声明端点取得联合搜索12条、v3-only搜索10条和metrics第一页25条。新搜索的`successRate`是外部平台统计，只作发现线索，绝不复制作本项目分数。Metrics第一页的`past7dVolume`全部为空数组，不能由百万历史job数声称近七天活跃，也不能把空数组当“近七天确实为0”。[本轮公开metrics列表](https://acpx.virtuals.io/api/metrics/agents?page=1&pageSize=25&sortBy=volume&sortOrder=desc)

| 线索 | 实际材料 | 结论与动作 |
| --- | --- | --- |
| Otto AI Trade Execution、旧#788 | 搜索有精确swap字段：amount、from/to symbol/address、chainId、tokenSource、deliverToButler、maxSlippagePercent；费0.01，requiredFunds=true。Metrics历史29991成功job，lastActiveAt却为未来值。 | 不同于旧Otto Market Alpha，不先混同。最新engagement读取超时，本轮未证明近期真实交付。 |
| Otto的新映射 | `/agents/legacy/788`返回UUID`01a0b032-63aa-7731-b906-a40422b472ea`、钱包`0x638ec60a2330b7cba2617fd4347518daa669fd78`、isHidden=true、Base active=false、offerings=[]；联合搜索旧#788钱包却为`0x5bB4B0C766E0D5D791d9403Fc275c22064709F68` | 旧历史/旧钱包与新UUID不能直接拼接归属；不向隐藏映射的新钱包照旧schema建单。[官方映射](https://api.acp.virtuals.io/agents/legacy/788) |
| MuteSwapAI、旧#1055 | online搜索返回，但公共列表最新记录为2026-03-09，另有EXPIRED/REJECTED也标粗粒度status=Completed；新映射404 | 不作为近期活跃候选；旧真实历史尚可单独研究。必须检查phase及真正业务交易，不能按Completed粗字段统计成功。[实际历史](https://acpx.virtuals.io/api/agents/1055/engagements?pagination%5Bpage%5D=1&pagination%5BpageSize%5D=5) |
| Axelrod旧#129 | metrics有41612历史成功job、最后在线2026-10-21；精确搜索和最新engagement读取均超时 | 无本次近期交付原件，不升级为就绪，不围绕超时反复探测。 |
| ButlerLiquid旧#1120 | metrics有1706历史成功job、最后在线2026-10-14；最新engagement读取超时 | 保留历史线索，本轮无新近期交易证明。 |
| OpenClaw Base Ops旧#18682、botsbot旧#37844 | 联合搜索有明确Base执行schema；前者有payoutAddress/slippagePercent，后者有tokenIn/tokenOut/amountIn与执行声明 | 只有目录声明，无近期交付证据；不再据广告直接扩建下一批业务单。 |

v3-only在线结果中，Hydrex、TheSafeRouteBot、SafeRoute是已有原件和实际交付的正向对照。Ethy/ZeroAgent有旧真实拒单记录，不因新的搜索successRate改写旧结果或重复试单；其余多是分析、核验或非交易能力，不能凑10个以交易为核心的对象。

## 后续全平台分页与近期对象过滤

没有在旧六个名字上停止。本轮继续从当前官网router与agent-table模块定位到**新版**`https://api.acp.virtuals.io/agents/leaderboard`，不是旧acpx列表。官网映射的排序枚举是`VOLUME/JOB/WALLET/REVENUE`；其中`JOB`为历史任务总数，并非“近7日任务数”。UI把`past7dNumJobs`明确填null，只绘制`past7DVolume`累计曲线，所以没有捏造一个前端不支持的近7日任务排序。[官网榜单代码](https://app.virtuals.io/assets/agent-table-DnbDPFpJ.js)

实际读取`sortBy=JOB&sortOrder=desc&pageSize=100`的第1–4页，返回总数381、捕获381行、去重374身份。跨页有7个重复ID，分页不是原子快照，不声称精确覆盖所有381身份。再按真实近7日在线时间（排除2999未来值）及累计曲线首尾增量离线排序，复用已存元数据，并定向核近期新对象的真实offerings。[新版榜单第一页](https://api.acp.virtuals.io/agents/leaderboard?sortBy=JOB&sortOrder=desc&page=1&pageSize=100)

例如Nox的21个近7日点都保持83523.756…，这是平的历史累计线，不能把“21点非零”说成21次近期业务。TheSafeRouteBot、Hydrex的曲线本轮分别有约0.05、0.03997395004增量，与已有真实业务方向相符，但平台金额不是链上结算证明。所有捕获行及真实增量在`platform-ranked-candidates.json`，没有把外部metrics数值当作本项目评分。

实际过滤结果：NuSHA为图像/文字/语音；BitsAndBytesBack为审计/代码/研究；Trinity为Saju信号；APM为采购/数据报告；Entropy为艺术；Priors为信用查询；LUMI为预测/证据审计；O17 Vapor为推理/文本；Syeollanga为图像视频；TradeOS明确read-only/no execution；Xtoken为X信号/订单簿查询。它们具有近期在线或收款线索，但没有因此计为资产执行Agent。Liquid Logic只有支出审计及只读安全工具，也没有计入交易执行数量。

Liquid Logic发布的audit资源本轮一次GET实际返回402且正文为空对象；没有付款，也没有把它称为已取得的免费账本。该身份近7日activities为空。它不能作为“真实本金支付服务”的替代对象。

旧协议近期历史不畅的Axelrod/ButlerLiquid，又从当前可用的`/agents/legacy/{id}`取得不同证据：Axelrod映射UUID`019e2026-bbad-791d-81e7-f10d84165e41`、isHidden=true、Base active=false、offerings=[]；ButlerLiquid映射UUID`019db491-d810-7aa4-9379-07aa2dc1f70e`、active=false、offerings=[]。没有重试先前超时的搜索或engagement接口，也没有把旧历史迁到这些新钱包。

## 新资产路径及具体可行动前提

### Zyfai：有近期链上预算事件，已有vault动作源

新增对象UUID`019d732b-39d8-75a1-87ef-a54d1d3f1606`、钱包`0xc8d26ef14426b289ed5e0de6ffc80ea9af836823`。当前官方`activities`有2026-10-25 21:50:52.822Z的Base `job.budget.set`，交易`0xba6eb9e44595435d3645a755ecaf5c8c37c3bd298a63b99f99c771ffb357d0d1`，精确绑定该provider与client；这是**近期真实接单协商线索，不是Submitted或资产履约**。无时间过滤的完整活动列表也只有这一个事件，未虚构更多交付。[官方活动原件入口](https://api.acp.virtuals.io/agents/019d732b-39d8-75a1-87ef-a54d1d3f1606/activities?page=1&pageSize=50)

其`deposit_agent_vault`挂牌0.01 USDC/requiredFunds=true，输入`amount:string`；交付`success,transactions[],summary`。withdraw/claim同样返回交易列表，不能仅按产品文案认定由provider代签。直接SDK需要API key及SIWE；ACP服务可能由提供方持其自身凭据调用，不能把SDK的API key条件直接强加给ACP买方。

官方ondefy SDK固定blob给出Base现有vault `0xD580071c47d4a667858B5FafAb85BC9C609beC5D`，ERC4626兼容、异步赎回：`deposit(assets,receiver)`、`requestRedeem(shares,controller,owner)`、`claim(withdrawKey)`。SDK的`vaultDeposit`只做精确USDC授权和存入，receiver为当前account；身份register方法是另一个独立方法，没有在此路径自动调用。它检查`Number(amount)<=2`即拒绝，尽管错误文字称minimum2；这说明上游SDK路径至少要严格大于2 USDC，不能照抄0.1 USDC swap参数。实际ACP交付与上游SDK版本是否一致仍待核。[官方SDK](https://github.com/ondefy/zyfai-sdk)、[固定vault ABI blob](https://api.github.com/repos/ondefy/zyfai-sdk/git/blobs/21d6a4d1182eacb5007e5877cf0d5903ed709591)

现有vault份额是存款记账，不应写成发行新项目币；本轮未操作份额，也未证明实际部署runtime/资产/退出窗口。原始Agent方案若要求新tokenize、身份mint、发行新币或其它未审动作则停止该路径。Root可先只取真实方案，核现有合约与份额/USDC效果，再决定资产操作，不执行SDK中的注册/部署例子。source blob及解码分别在`zyfai-vault-source-blobs/`和`zyfai-vault-abi/`。

### N9T2：直连桥可继续调查，无需手机

重新复核旧事实：我方ACP82151没有接单，保持OPEN/空预算；当时成功的是官方直连免费quote，以及他人公开ACP81682桥接历史。旧公开样本已独立核到3.347405 XRP，而提供方写3.347986 XRP，差581 drops，继续保留，不用近似数抹平。

当前官方Agent Card/llms仍列12路、Base USDC↔XRPL XRP双向和每单1.45 XRP等值费用，quote免费；旧manifest商业段只列XRP/ETH，新USDC路线须以root绑定自有新r地址的新鲜quote核实。近7日ACP activities为空，不能称新近期Submitted。原先因华为不能装Xaman的限制已有替代：XRPL官方允许本地强随机生成keypair/address，再由第一笔足额XRP激活，不需要手机。当前reserve为1 XRP，owner reserve每对象0.2 XRP；储备不是服务费，返程须保留基础储备、返程quote gross payment及链费。[XRPL账户](https://xrpl.org/docs/concepts/accounts)、[XRPL储备](https://xrpl.org/docs/concepts/accounts/reserves)

未激活r地址是否被N9T2接受、当前最低本金及净到达能否覆盖激活，仍需root先取新报价。没有生成钱包、发报价请求、充值或付款。子任务原件/清单在`n9t2-live-review/summary.json`。

### 独立资产支付筛选：Twift与Austin没有被“在线”标签升级

新增查Twift旧#40961的`token_multi_send`，精确输入token与recipients[address,amount:string]，fixed0.01/requiredFunds=true，业务本金多收款不同于ACP服务费；额外0.005 USDC reward不能替代本金履约。其近5条公开历史最新2026-08-22，只有EXPIRED/NEGOTIATION，未取得实际MultiSend合约地址，新映射404，不能按搜索100%声称当前已活跃。`t-test`旧#27147同模板/后台不重复计。

Austin旧#1146的`send_money_to`输入amount及to_wallet_address；价格是percentage 0.5，文案又称1%，不能解释成固定0.5 USDC或0.5%。唯一补读的旧完成单1001166981（2026-01-07）明确是1 USDC本金加0.5 USDC费用，目的地址为provider owner；交付被`*****`遮蔽，无业务转账hash，所列ACP memo hash不能当作本金执行。最新列表为2026-01-30 EXPIRED。两者仍UNKNOWN/缺近期证据，未试单、未付款，记录在`asset-transfer-review/summary.json`。

这些材料给出了Zyfai现有vault和N9T2直连桥两条可继续补方案的独立业务方向，**未宣称已找到两个新增、近期Submitted且已核资金效果的对象**。后续只有root真实实验/独立链证据才能补足该事实。

## 独立链对照的实际限制

Base Blockscout和Robinhood Blockscout的公开合约logs端点分别返回403；各host均停止，没有伪装请求、换路径或绕过。Root随后明确允许只用项目既有可信公共Base RPC、最近最多2048块取证。

本轮RPC：`eth_chainId=8453`、head及规范头读取成功；固定窗口为**53205599–53207646，共2048块**。该窗口的ACP `JobSubmitted`单次`eth_getLogs`返回429/rate_limited，已停止该host，没有缩窗重试、换RPC或读取秘密配置。没有成功获取该窗口日志，所以不能声称窗口内没有交付、没有活跃对象或提供方失败。原件`runtime/acp-chain-routing-20261029/base-recent-chain/`保留固定参数、头及429正文。

因此本轮“新增、独立核到近期JobSubmitted的交易provider”数为0；这是一项取证限制，不是服务质量分。未完成的新资格方向应继续由有实际方案/资金效果的Topaz、Ophis等并行路线推进，不以本轮发现列表数量替代真实完成数。

## 后续最小动作

1. 保留六单，不向其付款或以“换链试试看”重建；root后续按原job读取提供方回应或明确终态。
2. 对新候选先分别固定平台版本、接单链、业务执行链和实际钱包绑定；有至少两家明确当前接口与真实交付路径后，再冻结同类实验。
3. 活跃优先用近期可归属的任务交付及规范链证据；搜索future date、静态active、累计成功率只作背景。缺资料、平台故障及真实服务失败继续分开。

## 取证与验证记录

原件总目录：`runtime/acp-chain-routing-20261029/`。每次公开HTTP都有intent、observation及已收到的原始正文；timeout无正文则明确为空。`review.json`汇总真实请求数/状态，`manifest.json`绑定文件SHA。下载SDK的本地完整性对照exit0；研究命令的HTTP403/429/404/超时均按原结果保留。`recent_base_events.py`因429以exit1停止，未生成伪造成功摘要。

工程测试NOT_RUN（只读研究）；无Agent业务调用、钱包/密钥/认证配置读取、签名、付款、链写或生产修改。本任务只新增本研究文档与该runtime目录，PLAN/STATUS由root汇总更新。
