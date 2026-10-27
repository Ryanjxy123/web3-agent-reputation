# MangoSwap V4 原生资产与订单退出补测（2026-10-27）

本轮已完成三笔Base真实交易：**0.00002原生ETH兑换USDC**、**0.02USDC定时订单同笔创建并全额撤销**、**0.02USDC限价订单同笔创建、查询并全额撤销**。三笔均已独立核验，资金已收口，没有本轮遗留的活动托管订单或下一笔金融操作计划。

本轮三项补测已作为**独立链上证据快照接入网站**，没有生成新的数值分或修改旧范围分。[MangoSwap页面](http://127.0.0.1:7754/?agent=mangoswap-26345)展开“新增链上补测”即可查看。原报告仍为A90.20–100、F50.48–69.94、B100、范围综合77.25–87.98，四份历史报告保持；旧98.70也未改。PR21已按用户要求关闭、未合并，多人并发相关内容已撤回，不自动重开PR。

新公开包为`data/public-chain-mangoswap-v4-v1.tar.gz`，817785字节、1487个依赖文件，SHA256 `e301264e36e1cb580f344030d40d4884231a463b4b944e2aa89d956e02df39d5`。这是已生成的本机离线包，本轮没有将新实验代码/包push远端。

## 对象、入口和角色

对象为Ethereum ERC-8004 **MangoSwap #26345**，规范身份 `eip155:1:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:26345`。本轮执行链为Base，chain ID 8453；官网V4实际合约为 [`0x1681D47aA3AAEcc47b9CD1d0bA6DF37CD683510e`](https://basescan.org/address/0x1681D47aA3AAEcc47b9CD1d0bA6DF37CD683510e)，已验证合约名为`MangoSwapV41`。

本项目买方 `0x73d642847cb9a3acef116ea207a74b9956c34a09`依据已获授权的任务签名，合约执行操作，评价平台独立读回交易、回执、事件和状态。当前入口与登记身份的关联仍为PROVIDER_DECLARED，不冒称已取得IPFS注册正文认证。MangoSwap目前按已注册工具/服务型对象描述；这些交易不证明其自主AI决策、提供方自主签名或替用户托管投资策略。

本轮使用官网V4合约，不能与旧网关API直接调用Router02的入口混为一谈；也不并入Spraay #26346的其它能力。冻结任务计划为[plan.json](../../runtime/mangoswap-v4-capabilities-20261027-5ebeb408-0d2b-400d-a39e-b83e27d24979/plan.json)。

## E1：真正使用原生ETH兑换USDC

任务ID为`c55336de-995d-48f6-b28d-233cb1444f3f`，nonce 9。调用V4 `instantSwap`，输入资产为零地址表示的原生ETH，输出为Base原生USDC合约`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`，不使用既有WETH代币充当原生输入。

| 项目 | 实际数值 |
| --- | --- |
| 输入本金 | 0.00002ETH，即20000000000000wei |
| V4平台费 | 0.0000001ETH，即100000000000wei，费率50/10000=0.5%，已包含在上述本金中 |
| 扣平台费后用于兑换 | 0.0000199ETH |
| 最低到账 | 0.045659USDC，即45659个最小单位；任务滑点设置50bps |
| 实际到账 | **0.045889USDC**，高于最低到账 |
| 业务状态 | V4 swap ID 1，Executed |
| 上链区块 | 53151569；核验head 53151753，相隔184块 |
| 网络费 | **0.000002298131649013ETH** |

真实交易：[查看E1](https://basescan.org/tx/0x06821436a39048c70b0f6534a36d1dd3a68e7e014118fb89c5a1b32dd7be4a25)。

独立核验使用17份新增RPC读取和2份复用记录，保存了canonical区块、原交易/回执、官方Factory对应池、V4存储、USDC精度以及前后资产/费用状态。买方USDC增加45889单位、WETH未动，原生ETH精确减少本金加实际网络费；V4原生余额和费用计数均增加100000000000wei。报价按固定区块、扣平台费后的金额与Uniswap V3费率3000路径取得，不把网页零值`previewSwap`当作有效报价。

详见[E1独立证明](../../runtime/mangoswap-v4-capabilities-20261027-5ebeb408-0d2b-400d-a39e-b83e27d24979/runs/c55336de-995d-48f6-b28d-233cb1444f3f/independent-proof-20261027T091849753252Z-e233ac/summary.json)。这补上了原生ETH输入与官网V4即时入口的真实证据，没有验证原生ETH输出、Aerodrome、最佳价格或免gas。

## E2：定时订单创建后立即撤销，本金全退

任务ID为`0abb231a-0403-434e-b189-3573b52a7972`，nonce 10。一笔买方智能账户`executeBatch`按序执行：精确授权20000单位USDC → `scheduleSwap(USDC,WETH,...)` → 取消新订单。创建和撤销处于**同一笔链上交易**，没有拆成两次发送或留下等待到期的活动订单。

| 项目 | 实际结果 |
| --- | --- |
| 定时兑换输入 | 0.02USDC，即20000个最小单位；目标输出WETH |
| 计划时间 | 创建预检固定区块时间+86400秒；订单时间为2026-10-28 09:30:13UTC（北京时间17:30:13） |
| 托管与退款 | 买方→V4转入20000单位，V4→买方完整退回20000单位 |
| 最终订单 | V4 swap ID 2，**Cancelled**，没有执行兑换 |
| 买方及V4的USDC净变化 | 均为0；本订单残留托管0 |
| 剩余USDC→V4授权 | 0 |
| 平台费 | 0；创建后取消，未进入收费兑换执行 |
| 上链区块 | 53152159；核验head 53152305，相隔146块 |
| 网络费 | **0.000001718331295636ETH** |

真实交易：[查看E2](https://basescan.org/tx/0xec3f837d439b4ce032bdabe118e205541f6881bf544f0454d67817b1d43d5b21)。

独立证明使用16份新增RPC读取和2份复用记录，核对精确批调用、回执中的两向USDC转账、`getSwap(2)`、买方订单列表、前后余额/授权与实际gas。V4创建方法不发创建事件，因此订单关联依靠原calldata、买方历史与已存状态，不能虚构`OrderCreated`事件。最终本买方V4历史为`[1,2]`，分别Executed和Cancelled；WETH不变、没有本轮未结订单。

发送前还保存了取消错误ID 3的只读模拟：外层RPC code 3 revert，确认该错误路径不会在实际批处理中留一个已成功创建的订单。该负例没有广播。详见[E2独立证明](../../runtime/mangoswap-v4-capabilities-20261027-5ebeb408-0d2b-400d-a39e-b83e27d24979/runs/0abb231a-0403-434e-b189-3573b52a7972/independent-proof-20261027T093721868674Z-dfe34e/summary.json)与[错误ID模拟记录](../../runtime/mangoswap-v4-capabilities-20261027-5ebeb408-0d2b-400d-a39e-b83e27d24979/runs/0abb231a-0403-434e-b189-3573b52a7972/WRONG_CANCEL_EXPECTED_REVERT.json)。

这证明创建、本人撤销、全额退款和原子退出，不证明到期自动执行、keeper在线、周期交易或真实限价履约。两笔V4交易中只有E1完成了资产兑换，E2不能再计作一次成交。

## E3：限价订单创建、查询与全额撤销

任务ID为`ab0adfaf-b70b-49ce-9de8-2932bcd26793`，nonce 11，使用独立冻结计划，不修改E1/E2原计划。真实交易：[查看E3](https://basescan.org/tx/0x202b76100bf19ae91c399b25dfb6433ab5dfd6effa8541e67ea1931c9be6fb9a)，Base区块53155395，独立核验时相隔74块。

本笔以0.02USDC创建USDC→WETH限价单，目标价格原始值`500000000000000000000000000`，即1USDC对应0.0005WETH；到期时间为准备区块时间加86400秒。同一原子批次精确approve、创建、查询、取消，再读终态与资产，不调用`executeLimitOrder`。

限价单ID0最终为Cancelled，本人历史为`[0]`；回执中买方→V4的20000单位USDC和V4→买方的20000单位退款均已核对。双方USDC净变化0、既有WETH不变、授权0、无本单残余托管。完整固定块`eth_call`看到了中间Scheduled和终态Cancelled；实际链上证明以同交易事件与最终存储为依据，不冒称可从区块终态读取交易中间状态。

新增实际网络费**0.000001838383645158ETH**，服务费/平台费0，无兑换或净本金支出。独立证明18次只读取证，无重跑旧交易。原件见[E3证明](../../runtime/mangoswap-v4-e3-20261027-eb85e0f1-7d2f-4704-b741-fa9fe997d836/runs/ab0adfaf-b70b-49ce-9de8-2932bcd26793/independent-proof-20261027T112229379311Z-dc2695/summary.json)与[E3安全结算](../../runtime/mangoswap-v4-e3-20261027-eb85e0f1-7d2f-4704-b741-fa9fe997d836/safe-closeout.json)。结算SHA256为`484e41a486df36c1b4aa6d7d6ba1a4f6e32992c7eeafa8ba184bf05a7f1c1fb1`。

这补上限价创建、字段查询、本人取消与退款，不证明价格条件触发成交、执行失败后可退款或自动keeper。该实验安全退出依赖创建与取消处于同一笔已验证的原子批次；不在链上留下等待未来执行的资金。

## 费用与资金收口

| 费用 | E1（wei） | E2（wei） | E3（wei） |
| --- | ---: | ---: | ---: |
| L2执行费 | 2297382000000 | 1716924000000 | 1836024000000 |
| L1数据费 | 749649013 | 1407295636 | 2359645158 |
| Operator费 | 0 | 0 | 0 |
| 实际网络费合计 | 2298131649013 | 1718331295636 | 1838383645158 |

三笔网络费共 **0.000005854846589807ETH**；本轮新增x402服务费为**0USDC**。E1的0.0000001ETH平台费已在0.00002ETH本金内扣除，不能再加一次。本轮原生ETH总减少为本金加网络费，共 **0.000025854846589807ETH**；USDC净增加0.045889，WETH不变，E2、E3各0.02USDC本金均全部退回。

确认任务快照（区块53155395，非实时余额查询）为：

| 资产/状态 | 本轮开始 | 收口快照 |
| --- | ---: | ---: |
| 原生ETH | 0.002993237310238374 | 0.002967382463648567 |
| USDC | 0.663007 | 0.708896 |
| WETH | 0.000540187903644028 | 0.000540187903644028 |
| 本轮USDC残留托管 | 0 | 0 |
| USDC→V4剩余授权 | 0 | 0 |

三笔实际资产交易对应nonce 9、10、11；钱包交易签名和后台请求授权签名分别记账，不把授权签名数当链上交易数。`financial_actions_complete=true`、`further_financial_actions_planned=false`；本轮没有新增Signer或变更策略/委托，不因还有余额继续发送没有明确假设的交易。

总账：[safe-closeout.json](../../runtime/mangoswap-v4-capabilities-20261027-5ebeb408-0d2b-400d-a39e-b83e27d24979/safe-closeout.json)，SHA256 `627405eadf2ea353a7eeeab4019b3a685acf23709f3a07905daee7971a488ff5`。本次文档核对了两份独立证明的原字节SHA，均与总账所记一致，没有重跑核验脚本或重新采集。

## 源码与模拟揭示的缺口

已保存的BaseScan页面声明Exact Match；提取的11299字节部署代码与此前可信Base区块53147401的`eth_getCode`逐字节一致，源码是具体`MangoSwapV41`，没有代理升级路径。本轮没有本地重新编译。来源见[源码审计](../../runtime/mangoswap-v4-source-audit-20261027T084316Z-64f757cb/audit-findings.json)、[字节码绑定](../../runtime/mangoswap-v4-source-audit-20261027T084316Z-64f757cb/bytecode-binding.json)及[实际源码](../../runtime/mangoswap-v4-source-audit-20261027T084316Z-64f757cb/source-01-mangoswapv41.sol)。

- `executeScheduledSwap`和`executeLimitOrder`捕获内部兑换失败后只改为Failed；公开取消方法仅接受Scheduled，没有Failed订单的公开退款/重置入口。限价执行允许任意调用者尝试，因此不能为了补覆盖把真实本金投进这个已知退出缺口。本轮仅将真实限价创建与取消放入同一原子交易，未尝试限价兑换或让定时订单进入到期执行。
- ERC20→原生ETH即时路径把输入代币的原始费用单位累加到全局`fees`，而`withdrawFees`按原生ETH支付，存在单位混用；ERC20→ERC20费用留存也没有对应代币取费入口。这是源码发现，不伪称已通过真实资金实验验证；本轮未执行ERC20→原生ETH或原生资产订单托管。
- `_getBestPool`按3000、500、10000顺序选择存在的池，没有比较各池可执行净报价；`previewSwap`的估价始终为0。不能以本次成交支持全市场最佳价格、完整报价质量或Aerodrome支持。

另一次[同块只读差分](../../runtime/mangoswap-v4-atomic-simulation-20261027T090550Z-a4450125/PAIR_RESULT.json)实际执行7次可信读取：控制组创建限价后取消，模拟余额全退、状态Cancelled；处理组插入执行再取消，外层返回`execution reverted`。它观察到取消失败和该实际批处理路径的外层失败传播，**未观察到中间Failed状态**，因为Executed也会拒绝取消；Failed退款缺口依据仍是已绑定源码。两次`eth_call`均不落状态，无真实限价本金、订单或额外交易。增强三call方案未执行，不为改善结论重复模拟。

E1准备过程中曾出现本地SafeHttp目标日志键大小写错误；修正后保持同一资金范围继续追加，原失败记录保留、资金影响0，不归成Agent失败。

## 确认、评分和下一步的边界

E1/E2/E3的CONFIRMED、canonical匹配与184/146/74块距离已经取证，**不是Base finalized标签或L1最终性证明**。旧七笔的finalized补证也未齐：本次节点返回finalized块51996642，早于样本；B01–B05 canonical重读匹配，B06读取失败后停止，B07未读取。该[补证记录](../../runtime/mangoswap-finality-20261027T084502921641Z-484116/summary.json)保持UNKNOWN，不改旧报告分数。

三笔补测可以支持原生输入、V4执行、定时及限价创建、查询与撤销/退款判据；不能把RPC耗时、钱包签名耗时或确认等待改成Agent业务HTTP可用性样本。真正到期自动执行、周期、限价、免gas、原生ETH输出、其它路由/资产、最佳价格及长期可靠性仍未覆盖，不把服务型注册对象写成自主AI。

来源接入已完成：按能力/协议重放新任务，并复用既有`AgentChainEvidence`表和接口并列展示；没有新增评分模型、Schema、表或钱包协调器。配置、ADR与旧原件保持原字节，新增快照目录为`runtime/mangoswap-v4-supplement-20261027-v2`，来源配置为`configs/chain-supplements/mangoswap-v4-20261027-v2.json`。初次构建因第三份计划使用单任务格式，仅生成2项核齐/1项UNKNOWN草稿，未导入；修正读取后新v2完整核齐3项，旧草稿保留。

一次必要验收已通过：`python -m unittest discover -s tests -p test_contract_lifecycle_snapshot.py -v`，1项用例、59.048秒、exit0。使用真实公开包离线重放，核三笔、退款与授权，修改真实退款日志并重绑定SHA仍不能通过；错身份被拒、错交易保留未决，原31任务及范围分不变。没有重跑旧七笔或旧工程全套。前端构建两次exit0，第二次仅为补上Base交易的BaseScan链接；浏览器视觉NOT_RUN。

真实PostgreSQL导入成功，网站agent/report/chain快照/静态资源和新附件HTTP200，附件SHA匹配；私有签名文件404；原报告字节、latest及四份报告数量不变。收据见`runtime/mangoswap-v4-web-verification-20261027/receipt.json`。1488压缩成员逐个审查无凭据发现，两份plan中的authorization为普通用户授权说明，已核为字段名误报；原官网HTML/旧含访问配置摘要和私有签名均不导出。

离线恢复或在自己的PostgreSQL导入本包，使用已安装依赖的项目环境；本机uv不在PATH，实际验收使用`.venv/Scripts/python.exe`，以下提供通用uv入口：

```powershell
uv run --no-sync python scripts/build_contract_lifecycle_snapshot.py verify --archive data/public-chain-mangoswap-v4-v1.tar.gz
uv run --env-file .env --no-sync python scripts/build_contract_lifecycle_snapshot.py import --archive data/public-chain-mangoswap-v4-v1.tar.gz
```

按需要执行其中一步，已有有效核验不要重复；导入会复核后写快照，离线verify不写数据库，也不需要钱包、RPC或LLM。公开包已包含原范围报告的身份来源依赖，不必重新调用Agent。下一任务为用户查看补测结果；没有下一笔金融操作计划。未验证的自动到期/限价成交及Failed退出风险保持，不能为覆盖率继续把本金留在缺乏正常退出的订单中。
