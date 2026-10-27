# 单笔真实交易受控实验

日期：2026-10-23。task_id：`SPRAAY_REAL_SWAP_PILOT_COMPLETE`。状态：唯一真实兑换成功且独立链核通过；已追加153区块确认及费用组成证明。本单授权已消耗完，不继续付费或交易。

## 实验完成：真实兑换结果与三维解读

**本次已成功用1USDC换到0.000419044293938828 WETH。** 这是Spraay官方网关生成方案、我方专用买方签名并自付gas执行、Uniswap V3池实际成交的一次受控实验。不是ACP旧订单82153的履约，也不宣称Spraay自主决定或代为签名交易。

| 项目 | 独立核实结果 |
| --- | --- |
| 交易 | [BaseScan查看](https://basescan.org/tx/0xc128634a06746badd64c9e07fff97cfb486350239b7ecb7c9e50fba616e0c193)，Base8453，普通type2，本人from=to，nonce1 |
| 成交区块 | 52987893；可信RPC核canonical receipt status1 |
| 实际业务 | 精确1USDC→WETH，固定Router02调用官方Factory对应0.01%池0xb4cb800910b228ed3d0834cf79d697127bbb00e5 |
| 新报价 | 预计0.000419475256337655 WETH，最低0.000417377880055966 WETH |
| 独立预模拟 | 固定区块52987868，返回0.000418988806613433 WETH，满足最低要求；不是只对Agent字段互相比较 |
| 实际到账 | 0.000419044293938828 WETH，较报价少约0.10274%，在0.5%滑点上限内 |
| 资产与事件 | 同交易USDC向官方池精确Transfer1000000，WETH从池到本人419044293938828，池Swap事件相符；固定前后块余额相符 |
| 授权 | 首次只approve1000000，执行后allowance=0，无无限授权；7702委托保持不变 |
| 提交前预算 | 网络估计0.000001357052099443ETH，保守预算预览0.000003232160663947ETH，均低于批准的0.00001ETH；L2gasLimit213639/maxFeePerGas15046248wei |
| 实际网络费 | 1128052393709wei = 0.000001128052393709ETH；回执L2+L1及同块oracle operator0合计与ETH余额差完全一致 |
| 后续确认 | 区块头52988046，相距153块；不把L2确认距离说成Ethereum L1 finalized |

最终已核余额：**1.47USDC + 0.000419044293938828WETH + 0.002998871947606291ETH**。两次真实方案费合计0.03USDC；1USDC本金换成自己的WETH，不是付给Agent的服务费。ETH提币费/买币成本未提供，不虚构人民币总成本。

三个维度如何解释这次实验：

| 固定维度 | 本次已经拿到的真实证据 | 正式评价还需什么 |
| --- | --- | --- |
| 服务可用性 | 合法付费请求HTTP200、status ready，返回实际可执行方案 | 按统一规则补足独立可用性样本及耗时，操作者准备/签名等待不记Agent耗时 |
| 功能声明一致性 | 输入1USDC/WETH/本人/50bps与解码后calldata相符；独立链模拟返回可接受输出，实际成交高于minimum | 将兑换通用判据固定、关联准确注册身份，补足独立F任务；其他五项能力不能算已验证 |
| 交易行为可靠性 | 真实canonical交易成功、池/资产流/金额/收款/授权/费用独立核齐，确认距离153 | 按任务/执行角色及统一政策补足独立B样本，不把API付费、仅生成calldata或同一事实重复计数当B成功 |

结论：**兑换功能已证明具备取得正式三维评分的可行性，当前仍是一单pilot，没有创建正式三维总分。** 同任务可解释三维事实，正式F/B计分槽位仍互斥；不能把这一笔两头灌进分母。接口签名/发币授权不扩展，后续新增付费、本金或批量采样另列具体预算获准后执行。

身份与范围须继续核实：缓存ACP目录身份为Spraay Batch Agent v2（019e6bd3-2987-7bea-bfcc-89c3d7b79410），A2A卡为Agent Mango，卡明确将MangoSwap/兑换和Spraay/批量转账列为不同Ethereum ERC-8004身份26345/26346。该卡url指gateway.spraay.app，但不能把品牌下身份合并计数或把本次网关样本直接归进ACP旧单；下一步先只读核注册metadata与实际入口/功能归属。返回tokenOut.symbol写ETH而地址是WETH，应向用户明确封装资产；旧_gateway.contract标签与官方QuoterV2地址也有差异，不能拿该标签当唯一真值或在未定规则下武断扣分。已完成的独立池/资产核验不依赖这些自述。

原件与实际执行：

- 新方案目录runtime/nox-iclone-preflight-20261023/spraay-fresh-build-for-real-swap-20261023.private/，一次新CSPRNG费用nonce，0.015USDC已结算；新费用交易0x8c105dd8468e47f24f0b3f11348c932dcedb463305105ce996fa6ade64f01900，独立证据runtime/spraay-fresh-fee-verification-20261023T141816Z-da15d203/，5读exit0。
- 资产执行目录runtime/nox-iclone-preflight-20261023/spraay-real-swap-20261023.private/：先保存CSPRNG requestId、输入/nonce/预算、正确raw签名与hash，再fsync SEND_INTENT后一次eth_sendRawTransaction；执行exit0，14只读+1签+1广播。固定nonce与pending一致，不改delegate、不用sponsor套壳。
- 独立业务证明runtime/spraay-real-swap-proof-20261023T141933406775Z-9c22a9/summary.json，19读exit0，9个业务检查全部true。首次回执缺operatorFee字段时保留未知。
- 随后仅追加runtime/spraay-real-swap-finality-20261023T142345Z-6edee3cc/summary.json，4读exit0，补同块getOperatorFee(receipt.gasUsed)=0、153块距离及总费对账；没有重跑19项业务核验或覆盖旧证据。
- 新type2执行器必要离线ABI/编码/边界检查最终exit0；首次harness仅相对Python路径ENOENT，修绝对路径后通过。主应用工程测试NOT_RUN，因为生产代码、数据库、评分/前端均未变；完整报告新增0。

## 执行前记录：ETH到账与实际兑换批准

用户报告ETH交易`0xfe7e859311f4f20016b51dc527b19a6ab8bf65b523b0387f84b3fcc92867bd1c`。2026-10-23北京时间22:05:11可信Base52987476核：交易成功直达同一买方，value=3000000000000000 wei（0.003ETH），75确认；当前ETH余额0.003、USDC2485000、既有Alchemy v1.0委托不变。命令`.venv/Scripts/python.exe -X utf8 runtime/read_spraay_eth_deposit_20261023.py 0xfe7e859311f4f20016b51dc527b19a6ab8bf65b523b0387f84b3fcc92867bd1c`，exit0，7次只读，原件`runtime/spraay-eth-funding-20261023T140443Z-3a7c9d2c/summary.json`。已告知用户无需继续充值。

用户随后对具体问题回答“同意，执行这一次兑换”。范围为：额外一次最多0.015USDC新有效方案费；仅1USDC换既有WETH、slippage50bps、资产给本人、固定Uniswap Router02精确授权1000000；提交前网络总预估<=0.00001ETH才发出，超过停止，真实费用按链回执。gasLimit/maxFeePerGas约束L2；L1及operator不由这两个字段完全硬封顶，不能把估价说成链上绝对总上限。不改7702委托/钱包权限、不新增钱包或发币。

旧方案过期且旧费nonce已消费，不复用旧授权或改写原件。新fee使用一次新CSPRNG nonce并先持久化意图；所有普通type2签/唯一广播及独立链核工具准备且审阅后再取得5分钟新报价，避免先付费后才开发。真实type2 from=to本人、value0、data只含新方案的精确USDC approve及Router兑换两call；签前可信链模拟及成本、离线raw签名恢复/字段绑定通过才发。发送前持久化nonce、raw交易hash与SEND_INTENT，网络不明查原hash，不自动重发或换nonce。

新方案目录`spraay-fresh-build-for-real-swap-20261023.private/`，资产执行目录`spraay-real-swap-20261023.private/`，均位于忽略的runtime/nox-iclone-preflight-20261023/。上述是执行前记录；实际新费和本金已完成，以上方实验完成结果为准。平台与Spraay执行角色分开：Spraay生成方案，我方签名广播；后续独立核receipt、官方Factory池、USDC本金/WETH到账、授权及真实gas，不据API200宣布交易完成。

## 首轮方案费授权（历史，不作为当前待办）

用户已明确回答“同意，先付0.015USDC取得交易方案”。复用现有Base买方，仅支付一次官方网关固定构建请求的15000单位原生USDC；不包括兑换本金、合约授权/兑换调用、其他六功能消费、额度存款或新钱包。已独立核验用户2.5USDC入金，签名前核费用挑战不变。首次签名尝试与已核账的同nonce修正见下一节；状态不明先核USDC授权使用状态，不生成新nonce重复支付。响应只留存与解码，真实兑换及业务gas核清后再执行获准动作。完整六能力计划继续保留；本步只是兑换样本，不是整体完成。下一task_id=`SPRAAY_SWAP_EXECUTION_APPROVAL`。

最新到账核验：2026-10-23北京时间21:25:45，可信Base固定区块52986293，用户报告交易`0x0b180c0621d6bf83d0f1e9af6081e9aefa6b31af054ca24e644f92a4f3d051ff`成功、94确认；原生USDC精确Transfer至买方`0x73d642847cb9a3acef116ea207a74b9956c34a09`为2500000单位（2.5USDC）。余额2.5USDC/0ETH，既有Alchemy v1.0.0的7702匹配，6次只读exit0。原件`runtime/spraay-funding-20261023T132523Z-ca50a040/summary.json`。此前两次0余额快照保留，不再作为当前资金状态。

用户本人已确认OKX最低提币2USDC，最终自行提币2.5USDC；充值到自己的买方钱包，不是将全部款项付给Spraay。仅0.015USDC在本步费用范围，余款留存，后续可另核USDC/Base充值地址与网络成本回到本人账户。付款请求、签名和结算原件只存忽略runtime，不进公开包；不先买ETH、不新增委托或签名器。一次性付款脚本已经离线核验，不重复工程测试。

## 最新结果：方案和服务费均已独立核实

21:38:02北京时间，修正请求HTTP200；仍为原CSPRNG nonce及15000单位USDC服务费，没有新增委托/权限/钱包。7次可信Base只读预检同时证明buyer ERC1271 magic、原nonce unused、余额2.5USDC及精确USDC付款simulation成功；新签名和请求仅存忽略目录。原件`runtime/nox-iclone-preflight-20261023/spraay-paid-build-20261023.private/smart-account-signature-correction-v1.private/`。

21:40:35，独立可信Base52986731核付款交易`0x36f0092e9b358c281b97e640e7b6939f91c3af40dfc485c7b06ddc383ea9b5fa`：canonical receipt status1、精确15000单位USDC Transfer及同nonce AuthorizationUsed各一条，确认深度62；余额2485000单位（2.485USDC）/0ETH，刚好比入金少0.015USDC。9次只读exit0。证据`runtime/spraay-fee-reconciliation-20261023T134002548461Z/summary.json`，不是只信网关付款响应。

| 固定请求与返回 | 实际核验 |
| --- | --- |
| 1USDC换WETH，收款为本买方、滑点0.5% | 返回1000000原始USDC；WETH合约0x4200…0006，recipient/链8453一致 |
| 报价与最低到账 | 预计0.000416793635364511 WETH，最低0.000414709667187688 WETH，满足floor(报价×0.995) |
| 准备的授权 | USDC.approve(Uniswap SwapRouter02,1000000)，精确1USDC，没有无限额度 |
| 准备的兑换 | Router02 exactInputSingle，fee tier100（0.01%）、精确输入1USDC，value0 |
| 执行状态 | 两个calldata仅保存并解码，实际approve/swap/UserOp均0 |
| 报价时效 | 元数据截止21:43:02北京时间；Router02参数本身没有deadline，操作者须遵守本地时效，过期不签 |
| 已观察命名问题 | 返回symbol写ETH，但地址实际是WETH；对用户说明为封装ETH，不能宣称原生ETH到账 |

本次只说明该网关的兑换方案请求可完成，且输入/收款/授权/最低到账约束一致；独立市场报价及真实兑换履约仍待核。直接网关与ACP身份/任务绑定仍需分清，不能把此付款移植成82153订单履约。完整Spraay六能力未完成；不能把平台自己的API付费当Agent的业务交易B样本。

unsigned gas预估首次wallet_prepareCalls在13:42:04UTC返回401（旧会话失效），原件`spraay-unsigned-swap-gas-20261023.private/`。按既有同买方协议登录授权，用auth-prepare.private.mjs --auth-only仅签一条acp-auth并刷新会话，exit0，原件`auth-prepare-2026-10-23T13-44-00.962Z.private/`，无订单或广播。随后相同两calls的只读预估13:45:41UTC返回HTTP400，明文`Sponsored call rejected: Call[1]: contract 0x2626664c2603336E57B271c5C0b26F421741e481 is not on the sponsored allowlist`，原件`spraay-unsigned-swap-gas-after-auth-20261023.private/`。这是Virtuals赞助规则限制，不能据此判Spraay业务FAIL，也不能继续承诺gas免费。不套壳隐藏目标绕过赞助白名单。

自付ETH只读仿真及成本估算现已完成（见下节），未签/广播/发新委托或猜USDC allowance存储slot。用户已明确表示自行提币ETH，已提供同一买方地址并强调Base网络；当前等待交易哈希和独立到账核验。报价已在21:43:02北京时间过期；旧calldata只能用于诊断和成本参考，不能因eth_call成功就签旧报价。下一步须有新有效报价、本金与gas具体批准；本轮不继续支付第二次服务费。

## 自付Base ETH成本：已读，不是已执行

为避开Virtuals不赞助目标合约这一真实限制，未向赞助通道套壳。采用固定操作者官方Base RPC `https://mainnet.base.org`，SafeHttpClient+7897，只读核原delegate/余额，再对本人普通交易from=to=买方、原精确approve+swap的executeBatch执行eth_call；实际成功后才eth_estimateGas。不换节点重试、不改账户状态或allowance、不签名广播。官方SDK ABI与Python独立编码一致，不能仅凭ABI宣称权限成立，实际eth_call已经证明该固定区块下调用可执行。

2026-10-23北京时间21:52:53，Base52987105，9次只读exit0：

| 费用项 | 实际读取或计算 |
| --- | --- |
| 估计gas | 178059 |
| 当前gas价格 | 11398178 wei/gas |
| L2执行估计 | 2029548176502 wei |
| L1费用上界 | 18788351535 wei，GasPriceOracle.getL1FeeUpperBound(996) |
| operator费 | getOperatorFee(178059)实际返回0，不是缺项补0 |
| 合计预估 | 2048336528037 wei = 0.000002048336528037 ETH |
| 易懂解释 | 以这次1USDC→WETH报价比例粗算约0.0049USDC，不到1美分；不是需买一整枚ETH |

原件`runtime/nox-iclone-preflight-20261023/spraay-self-paid-gas-input-20261023.private/trusted-public-base-probe.private/SUMMARY.private.json`；命令先运行client/prepare-spraay-self-paid-gas-input.private.mjs纯本地编码（exit0），再Python probe_spraay_self_paid_gas.py（exit0）。L1尺寸取740字节calldata+256字节保守type2封装预留，不是签后精确序列；执行gas/价格可变，不能拿这个数当未来固定保证。Base费用依据[官方说明](https://docs.base.org/specifications/transactions/network-fees)。

这只是已过期方案的诊断和成本预览，未形成任何实际授权或兑换。USDC最新读取仍2485000单位；本步需要Base ETH支付普通网络费，但OKX最低提币可能大于实际消耗，须看本人页面后再给具体充值量。用户随后明确表示将自行提币ETH，已再次给出同一Base买方地址；当前等待实际交易哈希/到账，不自动支付第二次0.015USDC。真正执行前必须有新有效报价及明确本金/gas授权。

## 本轮实际命令与退出码

均在本项目根目录执行；Node使用D:/download/node.exe，Python使用.venv/Scripts/python.exe。命令中的client/为runtime/nox-iclone-preflight-20261023/client/，其他短脚本位于同一preflight目录。原件/签名/配置均只在Git忽略runtime中，不能直接公开打包。

| 实际命令或步骤 | 退出码与观察 |
| --- | --- |
| Python runtime/read_spraay_deposit_20261023.py 用户提供的交易哈希 | 0，6次可信RPC，2.5USDC到账 |
| Node client/spraay-paid-build-once.private.mjs runtime/spraay-funding-20261023T132523Z-ca50a040/summary.json | 1，402签名格式不兼容，无方案 |
| Python reconcile_spraay_service_fee.py 原付款私有目录 | 0，8读，未扣款/原nonce unused且过期/旧raw签名1271 revert |
| Node client/spraay-smart-signature-correction.private.mjs runtime/spraay-fee-reconciliation-20261023T133050886523Z/summary.json | 0，官方封装、7读预检、HTTP200，方案保存未执行 |
| Python reconcile_spraay_service_fee.py 同一原付款目录 | 0，9读，精确0.015USDC已结算，余额2.485USDC |
| Node client/prepare-spraay-swap-gas-once.private.mjs | 1，401会话过期，无签/广播 |
| Node client/auth-prepare.private.mjs --auth-only | 0，仅1条acp-auth登录消息，无建单/广播 |
| Node client/prepare-spraay-swap-gas-once.private.mjs --after-session-refresh | 1，400明确Router02不在赞助白名单 |
| Node client/prepare-spraay-self-paid-gas-input.private.mjs | 0，仅本地按官方ABI编码 |
| Python probe_spraay_self_paid_gas.py | 0，9次官方Base只读，实际self-call与gas/费用读取成功 |

新封装的必要离线检查最终exit0，收据spraay-smart-signature-offline-check.private.json；首个夹具只因大小写FF比较错误而失败，修正断言后通过，未把夹具错误当Agent错误。主应用工程测试NOT_RUN，因为没有改生产代码、数据库或评分政策；不为文档/提交重跑旧测试。

## 首次付款结果与签名修正

北京时间21:26:49，一次已授权付费头请求返回402，错误为`invalid_exact_evm_payload_signature: contract call failed: unable to call contract: execution reverted`，无付款响应头、无方案。没有凭HTTP错误直接认定未付款：随后在可信Base52986455独立读取authorizationState=false、余额仍2.5USDC、原nonce已过期、窄区间无相应Transfer，8次只读exit0。既存raw签名对买方isValidSignature的只读调用revert。原件`runtime/spraay-fee-reconciliation-20261023T133050886523Z/`及首次付款私有目录均保留。

我方调用Virtuals底层signTypedData只产生65字节EOA签名，绕过了现有Alchemy v1.0的nativeSMASigner ReplaySafeHash/1271封装；不能据此给Spraay业务FAIL。官方x402支持非65字节签名的bytes重载结算路径。源码及摘要`runtime/spraay-7702-signature-source-20261023T132906Z-ccb03aa2/`，官方说明见[钱包兼容性](https://github.com/x402-foundation/x402/blob/main/docs/advanced-concepts/wallet-compatibility.mdx)及[Alchemy版本说明](https://www.alchemy.com/docs/changelog/2026/8/20)。

恢复限于原0.015USDC费用授权：复用原CSPRNG nonce（不生成第二个），在确认旧签未使用且已过期后刷新有效期，对Transfer digest的ReplaySafeHash另签并按官方owner entity0封装72字节；先离线恢复内签者，再可信RPC只读核1271 magic及精确USDC transferWithAuthorization simulation通过，才能一次修正付款。原尝试不可重跑或改写，新恢复目录只追加；不升级/撤销委托、不改No Policy、不引入新钱包，不执行approve/swap或额外付费。若修正仍失败则停止并据实际错误决定下一步，不盲重试。原“最多一次”操作预算的失败路径在独立核账和明确格式修正后只允许本次有依据恢复，累计实际服务费仍不超过15000单位。

## 用户最新要求：覆盖Spraay全部声明，不能用一次兑换代表整体

六项公开声明的完整评价设计保留；用户现已批准先从单次0.015USDC兑换方案开始，其余功能资金另核。下表是计划，并非已经取得的验证结果；仍使用服务可用性、功能声明一致性、交易行为可靠性及30/40/30，不新增评分维度、不擅自六项等权。现有正式计分器按整份报告取样，尚未实现每能力独立评分再平均；涉及新业务判据、分母或汇总改变须另写ADR后实现。

| 公开声明 | 功能声明一致性的独立判据 | 交易行为可靠性涉及什么 |
| --- | --- | --- |
| 代币兑换token_swap | 固定USDC/WETH、1USDC、recipient和50bps；核输入单位、真实报价、最少输出及解码后的授权/兑换目标；实际结果与承诺核对 | 用户签名广播后独立核真实receipt/内层结果、转出/到账、精确授权及费用；清楚标注Spraay构建、操作者执行，不能写成它自主决定买卖或代广播 |
| 批量转账batch_payment | 固定两个受控地址和不同金额；核资产、每收款人、金额、手续费及是否按承诺合并 | 独立核同一任务全部Transfer/执行结果，有无漏付、重复、错付或额外授权；生成unsigned交易不算已付款 |
| 价格查询price_oracle | 核token合约、链、币种、来源与时间；对承诺的池/区块用独立链上读取比对，不以另一个不同时间市场价格武断判错 | 无业务链上写入时不适用；读取过区块链、付API费均不能冒充资产操作 |
| 多链RPC rpc_proxy | 以固定区块查询已知公开账户余额、交易或事件，与操作者可信RPC对照；参数和错误语义要一致 | 纯查询不伪造写入；它可以支持取证，但不能同时成为被测输出和唯一真值 |
| AI计算ai_compute | 按其实际承诺类型选有独立答案的小任务，核输出类型/格式/任务结果；音视频可用已知输入、可解码性与转写等；不能凭非空或model字段证明质量/模型真实性 | 单纯推理不计资产执行；若通过链上额度实际扣费，则只核相应额度合约与任务关联，不把x402付款当模型可靠性 |
| 预付计算额度compute_futures | 核存入USDC、可用额度、消费报价/折扣、真实消费扣款及退款是否符合说明 | 先核部署及权限，再用受控账户验证存款→一次真实计算→drawdown→余额/退款；核合约、资产、角色、金额、事件与任务，不自动重试扣款 |

服务可用性覆盖上述每项能力：合法请求能否得到该功能的有效业务结果，记录成功/失败、响应/完成时间、明确错误及服务稳定性；不能只测首页、RPC或HTTP200。付费服务先满足具体费用/授权条件，正常402报价挑战不判服务失败；用户等待签名和本平台故障不算Agent耗时。已有有效观察复用，必要的业务边界用例有限增加，不反复重测工程代码。

功能判据在结果出来前固定，分别保存输入、提供方原始输出、独立对照及PASS/FAIL/UNKNOWN/NOT_APPLICABLE。模型身份、最优路由或去信任等无法独立证明的声明明确保留缺项，不能凭服务自述通过。正式F/B样本用途保持互斥，同任务仍可在解释中展示不同事实。

报告应先解释该注册身份做什么，再给三个维度分数与六项能力的已测/未测范围，每项可展开任务与链证据。只验证兑换时只表述兑换范围，不叫Spraay整体完整评价。UNKNOWN不补100也不硬扣0；有链上写能力为B提供真实证据，查询的B不适用不制造虚构交易。Agent Mango/ERC8004/ACP不同身份不能凭品牌拼接；需先核入口与注册/运营绑定，报告始终保留具体入口与执行角色。

判据按兑换、转账、定区块查询、消费额度等通用能力复用，不为Spraay复制六套对象专用评分；实现扩展前仍核多对象覆盖。当前只提出完整评价方案，原政策及已发布分数未改。

额外源码核查：`compute_futures`在已审源码中为Base USDC预付计算escrow，不是ERC20/NFT发行或金融衍生品。最低deposit1USDC；deposit/refund返回用户待签交易，成功计算后operator才发drawdown。仍须核已部署代码、USDC与operator权限及任务授权，不能把宣传的non-custodial当无信任保证。文档与handler的账户标识、费用描述存在漂移，先记录待实测，未据此判已部署服务FAIL。源码原件`runtime/spraay-complete-capability-source-20261023T125154Z-cb38ec67/`。此核查未授权存款、消费、提款或付费。

## 当前路线变更：取消XRP钱包依赖

用户华为手机无法安装Xaman，已要求改测无需XRP的真实交易Agent。当时task_id=`BASE_ONLY_TRANSACTION_PILOT_PREFLIGHT`，优先复核Virtuals既有候选的Base/USDC现货能力与调用协议，再按新依据尝试零付款询价。N9T2和以下XRPL钱包步骤转为历史方案，不再等待r地址、不生成新钱包。三维自采证实验方法仍复用，报价与全部费用明确后再通知充值，禁止发币/身份铸造。

## Base候选：本轮已实际执行

现有买方为`0x73d642847cb9a3acef116ea207a74b9956c34a09`，Base 8453。新取VEGETA和Spraay官方详情、Spraay免费批量估算及公开Agent Card四次均HTTP200，原件`runtime/base-only-pilot-20261023T123506Z-c8cbe208/`。第一次采集在取得VEGETA后因本地响应路径拼接错误exit1；修正后复用该原件，仅补其余三个请求，接续命令exit0，不把工具错误算Agent失败。

| 候选 | 本次真实尝试 | 当前证据与限制 |
| --- | --- | --- |
| Spraay Batch Agent v2 | `token_swap`的action=quote；请求1USDC→WETH、0.5%滑点；service-only、零hook。订单82153，12:40:28.389UTC首次需求被平台接受 | 独立Base RPC核唯一建单与内层成功。12:45观察仍OPEN、budget=null、历史仅建单和我方需求2条；尚未收到本人报价 |
| VEGETA | `swap_base`；请求1USDC→WETH、recipient为现有买方、0.5%滑点；沿用已核资金hook。订单82154，12:42:17.122UTC首次需求被平台接受 | 独立Base RPC核唯一建单与内层成功。12:45观察仍OPEN、budget=null、历史2条；代执行声明尚未实证 |

两单为不同新对象的首次尝试，不重播前轮旧单；gas赞助、转账值0、fund调用0，未支付挂牌0.05USDC或本金。Spraay建单交易`0xb3736cc93406a7cb74bee7189eb8f106791b59214813e1ef586f3c5bfa255150`；VEGETA建单交易`0xb0b8cad583b77d9569e11def8e095eb0e5257167f3dc53b6d1bf5493755654f3`。它们不是兑换交易，也不代表接单成功。订单期限分别为13:42:33与13:14:11UTC，当前观察不能写成已过完整SLA或永久不可用，不向过期订单付款。

私有原件分别在`runtime/nox-iclone-preflight-20261023/createjob-approvals-2026-10-23T12-39-32.240Z.private/`和`createjob-approvals-2026-10-23T12-41-10.468Z.private/`；沿用现有operator，仅扩展静态对象/参数配置。两次精确eth_call、唯一提交/需求、独立receipt核验均exit0；一次必要离线配置/语法核对exit0。另续签一次既有ACP登录消息，不新增账户委托。主应用源码、评分及数据库未改，工程测试NOT_RUN。

## Spraay具体做什么

官方ACP声明六项服务：代币兑换、批量转账、价格查询、多链RPC、AI计算及预付计算额度。本轮仅研究前两项，免费估算只证明它声明支持Base及30bps协议费，不能证明已执行付款；其他功能未测。

本次拟测的兑换由用户指定币对和金额。Spraay读取报价、构造精确授权与兑换交易，调用者核对后签名广播，DEX合约结算。它不代表自主投研、选择买卖时机，也不能写成已验证的第三方代执行。已审[官方固定源码](https://github.com/plagtech/spraay-x402-gateway/blob/8cdf46506c578ec4e21b6b0f799899115405f409/src/routes/swap-execute.ts#L213)明确返回unsigned交易；batch实现同样返回待签交易。若最终采用该路径，报告分别说明Agent生成了什么、操作者签了什么、合约实际产生什么效果，不能把我们发送交易冒充Agent自己广播。

源码原件`runtime/spraay-swap-source-20261023T123810Z-a3b990d7/`，固定commit`8cdf46506c578ec4e21b6b0f799899115405f409`，六次只读均200。`amountIn`是人类单位，因此`"1"`为1USDC，不能照抄部分清单的`1000000`例子；默认支持声明和部署行为仍需用真实返回核查。

## 可直连的下一步与付款边界

已向`POST https://gateway.spraay.app/api/v1/swap/execute`发送一次无付款头的固定请求（1USDC→WETH、现有买方收款、slippageBps=50）。实际HTTP402列明Base原生USDC服务费15000最小单位，即**0.015USDC**，payTo为`0xAd62f03C7514bb8c51f1eA70C2b75C37404695c8`。只是读取收费要求，没有签名或结算。原件`runtime/spraay-execution-pricing-20261023T124340Z-710e5f53/`，响应SHA256`404d3c4aa8a5cc89bc7c23246ffdf736a24935ddafea1b5f0faf3024c810ccf2`，命令exit0；预期402不当作业务失败。

此前完整评价说明后，用户已明确批准先付0.015USDC取得方案；本步骤恢复，范围见上方最新授权。付款前先核余额并指导充值，不再重复询问同一费用许可。该费用不含1USDC兑换本金及业务gas，也不保证兑换已发生。现有智能买方有typed-data签名能力，但其x402实际兼容尚待实证，不能预先保证付款成功或免gas。

若完整方案对齐后该步骤获准，先给具体充值方法与金额，仅支付一次精确服务费取得原始方案；解码核对输出资产、recipient、金额、最低到账、精确授权与目标合约后核业务gas，再执行获准的真实兑换。官方已审方案使用Uniswap SwapRouter02 `0x2626664c2603336E57B271c5C0b26F421741e481`；5分钟截止时间只在响应元数据，须本地限时执行。真实返回改变这些内容则先说明，不盲签。当时下一task_id=`SPRAAY_FUNDED_BUILD`；ACP两单可后续只读查看，但不为等待空回复无限轮询或继续建同样订单。

## 前轮XRPL钱包方案（暂停，仅历史）

用户实查补充：当前欧易Web3中只找到Binance-Peg XRP（BNB Chain、0x地址），不适用于本次原生XRPL收款。收款地址改用下方Xaman步骤；欧易已确认的Base USDC来源保持。未让用户给该BNB地址充值，仍等待本人XRPL公开r地址。

用户已明确同意先用N9T2跑一笔小额真实交易，并要求告知XRPL钱包准备方式、报价与费用后再充值。当前只等待本人控制的公开收款地址，不再询问是否选择本路线。

1. 优先复用已有欧易App的**Web3钱包→收款/接收→XRP**。网络须为原生XRP Ledger/XRPL/Ripple，地址为`r`开头；交易所共享充币地址与其他链上的包装XRP不用于本次实验。欧易有[原生XRPL钱包页面](https://web3.okx.com/zh-hans/wallet/ripple-ledger)，用户当前版本是否展示该网络以实际页面为准。
2. 若现有钱包没有原生XRPL，用[Xaman官网](https://xaman.app/)提供的商店链接安装，选择Create a new account，由用户自己备份并校验Secret Numbers，取得公开`r`地址后停止。只需要公开地址，不需要恢复信息，不购买XRP或先充值激活。[官方建户步骤](https://help.xaman.app/app/getting-started-with-xaman/your-first-xrp-ledger-account/how-to-create-an-xrpl-account.md)
3. 当前XRPL主网基础储备为1XRP，首次足额原生XRP入账可创建链上账户。先核N9T2是否接受未激活地址，再核新报价净到账超过储备并留余量；不假定地址未激活就必须额外充值。储备是到账本金中的保留余额，不与桥接服务费重复计算。[储备](https://xrpl.org/docs/concepts/accounts/reserves)、[账户创建](https://xrpl.org/docs/concepts/accounts)
4. 普通Xaman自托管收款不需Destination Tag，本次不使用要求Tag的交易所地址。[官方收款说明](https://help.xaman.app/app/getting-started-with-xaman/sending-xrp-to-xaman.md)

地址收到后只做地址/链状态核验和免费最低档报价，随后展示精确本金、费用、gas支付方、收款与付款地址、报价到期时间。当前没有绑定用户XRPL地址的新报价，不给出充值金额。下一task_id=`N9T2_BOUND_QUOTE_AND_PAYMENT_PREFLIGHT`。

## 本次纠正与实验目标

用户提出先做一笔真实交易，由我们设计实验和独立取证，再根据结果评价。该方式可行。之前已确认的是“还没有取得足量真实任务证据”，不能进一步断言“Virtuals Agent不能完整三维评分”。公开历史不足也不妨碍我们作为真实客户产生自己的任务和观测。

老师固定三维是服务可用性、功能声明一致性、交易行为可靠性。A10、F7/B7是项目的正式统计政策，不是开展首单实验的先决条件。本次不改三维、权重或旧分数，先验证一条可复用的“任务约定→服务响应→实际链上效果→逐维解释”流程。

## 已完成的独立只读取证准备

从[XRPL官方公共服务器表](https://xrpl.org/docs/tutorials/public-servers)选择并固定`https://xrplcluster.com/`，配置来源为操作者审查，不接收Agent指定的RPC。本轮只允许一次`tx`读取，未开放submit或付费能力。

已有公开交付交易`95B07728773BF1D64E1075CDAEA23D998C6CD8F1678BDCF2CF80431ABF2B2AB4`独立RPC返回HTTP200、validated=true、账本107591208、Payment/tesSUCCESS，`meta.delivered_amount=3347405`drops，即3.347405XRP，收款人与原公开样本一致。这与提供方收据3.347986XRP相差581drops。当前已能自己取得两端链上材料，不再把“没有独立XRPL RPC”列为当前缺项；原始请求与正式样本数量仍需用主动实验补齐。

原件及静态操作者配置：`runtime/controlled-pilot-xrpl-read-preflight-20261023T121227Z-f0bd1be9/`，响应SHA256为`351f5af7a19772abf61f986d34ce628b3de55b567867fbf97680cc601d4c1153`。命令exit0，1次只读请求、0签名/付款/新交易；这是历史采证准备，不冒称首单实交易已完成。

## 具体首单方案

优先对象为Virtuals目录中的N9T2 Bridge，provider为`0x001f501a949454daba53bf6163b66a63fbae5925`。它的官方说明绑定了该身份，我们已从免费接口取得业务报价，并用可信Base RPC核到公开ACP81682的provider、付款和路由；不再被动等待无回复的旧ACP订单。采用其官方直连接口开展实验，报告注明入口，不把直连接口成功写成ACP订单成功。

目标操作：从已有专用Base买方支付原生USDC，通过服务收到原生XRPL XRP。使用既有资产，不发行代币、不tokenize、不铸造身份/NFT。用户目前没有XRPL自托管收款地址；尚未生成钱包或密钥。收款地址必须由用户控制，不使用旧公开样本地址、占位地址或需要未支持Destination Tag的交易所地址。

金额先取**新鲜、绑定该收款地址的最低档正式报价**，不沿用旧反向报价或假定1USDC必可成交。官方商业桥接流程为`POST /bridge/quote`→按报价支付→`POST /bridge/payment`提交已发生的付款哈希→读取`GET /bridge/receipt/{quote_id}`；`/bridge/execute`是另一套接口，不能混用。[官方流程](https://x402.n9t2.com/llms.txt)

付款前准备一张明确执行单：买方、Base 8453、USDC合约、报价ID/到期时间、收款地址、精确支付数量、其中本金与服务/路由费用、目标资产和收款人、gas支付方及最坏自付金额。报价内已包含的费用不重复相加，是否赞助gas按本次真实prepare核查。用户已同意单笔小额实验，要求先取得具体报价与费用再充值；在资金执行单明确前不付款。No Policy不是无限支出授权。

付款准备复用现有智能账户。已只读核对本地官方SDK：普通ERC20转账使用`/wallets/alchemy-rpc-erc20`的`wallet_prepareCalls`，固定Base原生USDC的单个`transfer`、`value=0`，地址与6位精度金额只取本次有效报价，显式`eip7702Auth={delegation:ModularAccountV2,version:v1.0.0}`。检查本次`feePayment.sponsored/token/maxAmount`，不以之前建单获赞助或代理名称推断免费；0余额可能阻止真实金额模拟，也不能用0额模拟代替。预检不调用会签名广播的高层`sendTransaction`，401停止、不自动刷新登录。当前未调用prepare、未签名。

## 三维如何由我们测量

| 维度 | 事先固定的观察问题 | 我们自己保存、采集的证据 |
| --- | --- | --- |
| 服务可用性 | 合法请求能否获得实际业务响应；接受任务及完成的耗时是否符合明确声明 | 原始请求/响应、发送/响应/受理/付款/完成时间、错误和超时、任务状态；HTTP ACK与实际业务响应分别记录。用户审批等待和平台故障不算Agent响应耗时 |
| 功能声明一致性 | 是否执行约定方向、资产、数量和收款人；实际结果是否达到明确承诺 | 交易前固定的输入/约束/报价；我们核源资产实际转出、目标资产实际收到、必要退款；只用明确保证的最低到账或误差约定判断违约，未承诺的估计价格不硬解释为保证 |
| 交易行为可靠性 | 交易是否真实成功、确认并与本任务对应；有无重复执行、超额扣款或越界授权 | 源链与目标链交易、原始事件/状态变化、实际调用者与目标、执行窗口、费用和授权；智能账户核内层结果。付款成功和服务真正交付分开核验 |

Agent只需提供可调用的服务及必要业务标识/条款，不需替我们生成评价结论。原始任务、报价、我方签署的支付内容和付款哈希由我们掌握；链上效果通过操作者选定的可信RPC独立采集。第三方收款地址不自动当执行钱包，实际角色按证据说明。

未返回目标交易哈希时，可用已知收款地址、资产、时间窗及相关交易/事件定位；须核唯一性和任务关联，无法排除其他转账时标UNKNOWN，不随意挑一笔到账。跨链必须检查两端。XRPL以validated账本中的`TransactionResult`、`meta.delivered_amount`及账本变化核实际结果；不能只读Payment.Amount或提供方收据。[XRPL元数据说明](https://xrpl.org/docs/references/protocol/transactions/metadata)

首单前固定钱包基线、任务约束和停止窗口，保留全部尝试；结果出来后不改判据。失败、拒单、错误到账和收据不一致同样是实验结果，不以“必须成功”决定是否保留。已有公开样本中收据与实际到账相差581drops，是待核事实，不预设本次也失败。

## 执行与报告

1. 准备用户控制的普通XRPL收款地址；核独立只读取证链路，冻结实验清单。当前不创建钱包或付费。
2. 用该地址取得Base USDC→XRPL XRP新报价，核算一次任务的总支付与gas，提交具体资金/签名内容给用户确认。未确认或报价过期不付款。
3. 获准后保存前状态、唯一付款意图与关联标识，执行一次真实付款；提交中断先查明原交易，不换请求盲重发。
4. 采集服务交付、两端链上效果和后状态，生成该任务的三维观察报告：测了什么、实际发生什么、证据何在、PASS/FAIL/UNKNOWN及缺项。
5. 首单闭环后复用同一任务/事件/效果采集结构验证其他对象，再按事先固定的正式采样计划扩样，不为一个对象复制评分代码。

同笔任务可以解释三维不同事实，正式F/B分母仍不跨用途重复计入。本次尚无正式桥接计分profile，计划先按`BACKGROUND`保存取证实验；若正式规则和样本分配能在交易前确定，可事先选择只计入F或B之一，不能看到结果后再挑用途，也不因pilot名称机械要求重复付费。现有正式计分器不会对单笔产生维度数字或综合分，首单先输出可核验观察，不把一次PASS写成稳定100分。后续足量样本按现有规则汇总；不以这个限制阻断实验，也不声称已改变评分政策。

本轮只读调查、文档和实验设计不需重跑主应用测试，工程测试NOT_RUN。真实新交易、资金支出、密钥生成及正式新评分均未执行。
