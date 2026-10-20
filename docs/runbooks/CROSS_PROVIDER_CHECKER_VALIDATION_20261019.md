# PancakeSwap V3 仓位 Checker 跨提供方验证

开工：2026-10-20（文档名按用户指定保留20261019）。状态：跨提供方真实七任务及两份正式报告完成；视觉验收受工具策略阻断，默认Worker恢复启动被自动审批拒绝。

## 目标与保护范围

使用用户指定的真实对象，证明两个不同提供方能够被自动匹配至同一个狭义业务Checker，安全执行真实仓位读取、独立RPC核验、从原件重建并经现有Worker和数据库发布。未满足可行性前不编码新业务规则。

原10份完整报告、Clawdia PARTIAL、Brain旧ERC20 Query PARTIAL及所有证据保持；旧政策、A十槽/F七任务/B七任务和30/40/30权重不变。当前Git初始81个已修改/未跟踪文件SHA和状态见 `runtime/cross-provider-checker-20261020/baseline.json`；不commit/push/reset。常驻Worker保持public-off；不执行付费、签名、链写入、资产操作或外部委托。

## 分阶段计划

1. 核对现有调用链、测试和历史/DB基线；确认既有LLM网络失败是否仍存在。
2. 优先Brain BSC #49467与HeyAnon BSC #45650：注册/ownerOf/tokenURI与认证文档、协议Schema、提供方归属、费用和完整调用安全路径；最多一次有界业务试调用。条件不成立才顺序检查Hallmark #338475、SMEAI #331698。
3. 只有两方真实共同事实与独立oracle成立，才复用现有LP核验和证据机制实现共享核心与轻量Adapter。
4. 冻结最多七个真实互异positionId任务，真实Collector端到端运行、来源复核及正式入库；证据不足保持PARTIAL。
5. 必要前端字段、构建/API/DB/浏览器及旧报告兼容验收，逐项给出完成或阻断证据。

## 当前调查

上轮 `bobai_activity` 的PASS不作为本能力证据。Brain与Hallmark各一次真实仓位试调用证明可行性；正式Collector于北京时间2026-10-20 02:14开始，最终两家各七个互异任务PASS并正式入库，详细经过和限制见文末。

### 基线（实现前）

`architecture-baseline/baseline.json` 证明实际数据库12 Agent/12报告/5作业；12份报告文件、manifest、DB及重算分数一致，原10份发布索引一致；2290和旧Query通过正式 `_load_report` 来源回放。Query30项通过（55.428秒），常驻Worker的public flags均关闭。快照和审查均只写本轮runtime，不改原件。

`llm-baseline/result.json` 记录原样23项LLM网络测试：1个失败子断言、4个ConnectTimeout错误、0跳过、45.281秒，真实socket触达0；生产/测试SHA前后一致。这是在任何V3实现前取得的失败基线，不能归为新Checker回归。保留原预算与断言，不以预建TLS上下文的诊断性成功冒充通过，本轮暂不改无关网络代码。

### Brain #49467

当前注册和协议已重新读取：9次有界请求，45秒上限、零重试、0业务调用；BSC链号、确认块、ownerOf、tokenURI及内嵌data JSON通过，文档登记MCP与实际端点一致，initialize/initialized/tools/list成功。实际 `pancakeswap_position_look` Schema含position/address两个string、禁止额外属性，工具明确Free。安全审阅补取4个不可变GitHub源码blob并核对Git SHA1，已确认精确position输入只走仓位/owner/factory/pool读取及eth_call模拟collect，没有签名、广播、资产操作或下游Agent委托；付款建议链接只当数据。完整闭合路径见 `brain-source-review/REVIEW.md`。尚未把动态liquidity/tick/in_range/fees与异时链值直接比较。

### HeyAnon #45650

8次请求后停止：目录及5个可信注册RPC完整200，owner/tokenURI认证成立；tokenURI为 `ipfs://bafkreihieg77na75qwuthry4w4splip6g24kpy4ftbor3qi4lrmacuk4cu`。原固定网关返回504；一次明确计划的同CID备用网关返回429，保留停止标记，不再换网关规避限流。未取得认证文档，因此目前不能证明端点绑定、当前Schema、任意BSC仓位输入或业务免费条件；未MCP、未tools/call、未付款。按用户顺序转Hallmark备选，不能据目录缓存宣称已具备共同能力。

### Hallmark #338475 与共同判据

Hallmark链上owner/tokenURI及data JSON原件认证通过，7个注册/Card读取均完整200。登记A2A及Card互相对应，Card提供方为Hallmark，`analyse`无pricing、输入为tokenId及可选chainId等，其他付费report和写入act排除。18个已冻结的公开源码GET逐个通过Git blob SHA认证；A2A路由仅调用显式analyse，使用public client读取NFT/pool/token/Chainlink，默认叙述为本地确定文字，无付款、签名或执行意图调用。预检原件在`hallmark-source-preflight`；公开源码不能证明线上部署逐字相等。

共同判据限于仓位ID及token0/token1、fee、tickLower/tickUpper。Hallmark顶层blockNumber来自并行单独查询，底层读取未绑定该块；Brain也缺原子读块证明，因此动态liquidity、tick、in_range、fees和投资建议均不纳入严格比较。

### 先验任务及Brain单次试调用

先于业务输出冻结7个历史ID，独立固定BSC块`0x7aa3155`读取NPM code、factory、positions及首个ownerOf。11请求完整保留，其中6个旧NFT已burn（RPC Invalid token ID），只有7637521有效；不以失败候选凑F。另冻结一次最多19个只读请求，从已认证NPM的totalSupply/tokenByIndex按固定等距索引补取最多6个现存NFT，结果见下文“足量先验任务”。

Brain唯一试调用`pancakeswap_position_look({"position":"7637521"})`完整HTTP200，14.031秒。实际token0为CAKE、token1为WBNB、fee500、ticks[-60370,-56730]，与先验独立RPC一致。`brain-pilot/pilot-plan.json`在请求前冻结身份、Schema、安全依据、输入及零费用预算；107个依赖SHA复核通过。Hallmark唯一实际试调用完整HTTP200，2.813秒，同一NFT的五字段全部与先验RPC相同。首次本地header限制在发送前拒绝（0请求），另存修正计划，仅使用既有允许的Accept头后才实际发送一次，未放宽网络校验。原件在`hallmark-pilot/header-guard-correction/`。

两份试调用仅用于可行性，不冒充正式Collector结果或补充正式七槽。两家真实输出条件成立后才开始新Checker实施。

### 足量先验任务与模块验证

枚举补充19个只读RPC完成：totalSupply为5251723，先冻等距索引[0,1050344,2100688,3151033,4201377,5251722]，独立取得NFT [1,1061890,2329346,4312849,5968095,7686767]。六个positions/ownerOf均有效，和7637521合成七个任务；`configs/position-read-tasks-v1.json`冻结顺序并引用枚举原件摘要。正式Collector将重新取得当前确认块及每个NFT的参考，不拿研究原件代替自动执行。枚举155依赖SHA及19观测离线重放通过；保留初版本地验证器因脚本路径非公开证据而拒绝的诊断，不改原件。

新增`position_oracle.py`复用严格ABI解码，只核静态字段；`position_adapters.py`只负责经审阅MCP/A2A契约。13项纯模块测试全部通过，且在socket阻断下两份真实发现/业务原件分别匹配、解析、经同一oracle得PASS，记录`position-pure-validation/`。这证明判据可复用，不代表正式自动发布已完成。

请求预算控制已实施并立即测试：`DiscoveryEvidence`保守预占请求次数，超额请求保存unsent；网络完成后的证据写入失败不返还预算。默认15秒保留，CLI45秒仅允许指定身份`--once`，generic总预算64。3项预算、3项Worker范围测试通过，旧Query Collector8项通过。

## 最小实现与发布门

| 文件 | 本轮职责 |
| --- | --- |
| `position_oracle.py` | 复用严格ABI解析，验证BSC链、确认块、NPM/factory及NFT存在性；同一五字段静态判据，无Agent ID分支 |
| `position_adapters.py` | 认证登记端点及精确Schema；MCP `pancakeswap_position_look`与A2A `analyse`映射到同一事实结构 |
| `position_checker.py` | 冻结七任务，先独立RPC再业务读取，保留UNKNOWN/unsent；从全部原件重建能力和样本 |
| `checker_dispatch.py` | 静态分派新增V3优先，未匹配沿用ERC20/Mech；一个报告只取一组F任务，避免Brain变成八个F任务 |
| `registration_discovery.py` / `worker.py` | 请求预算及单身份单次45秒上限；沿用队列、租约、网络白名单和public-off默认值 |
| `generic_evaluation.py` | 连接Collector、来源Verifier及原评分/正式入库；不改DB schema、API、权重或阈值 |
| `ReportView.vue` | 仅将PARTIAL提示改为“本次保留X条核验记录”，避免把未发送UNKNOWN称为实际调用 |

政策见ADR0013，任务见`configs/position-read-tasks-v1.json`。两文件在正式报告绑定前已冻结，后续不修改。Oracle只比较NFT ID和token0/token1、fee、tickLower/tickUpper；不评价动态数值、收益或建议，ownerOf只用作存在性参考，不作业务分数。

核心重建不信任存储的PASS：重新核SHA、注册与端点、协议握手、任务顺序、参考区块、输入/输出、完整能力元数据及时间。请求完成时间为observed_at加elapsed_ms；HTTP鉴权/付费/限流及HTTP200顶层JSON-RPC quota均停止该主机。同run早期availability停止也参与重建；合法旧无时间skip只在预冻slot严格绑定时兼容，孤立请求、伪related plan和停止后续发均拒绝。

Collector异常时不会放宽预算；正常/不适用返回恢复先前预算。正式Worker只处理当前指定身份，运行前核对零活动作业并暂时停下public-off Worker，完成后恢复public-off；未绕过常驻公开执行的既有拒绝。

## 工程验证（与真实任务分开）

- Position完整套件34项通过，126.630秒（含纯Oracle/Adapter13项、来源/Collector及分派）。之后停止条件修正的来源/Collector20项通过，142.835秒；最终两个来源边界修正的13项受影响测试通过，88.463秒。日志和最终源码SHA在`position-checker-validation/final-source-boundaries-receipt.json`，不将这些Mock任务计入真实F。
- 独立审计：两份真实pilot离线重建均PASS；5项原篡改/超时/隐藏请求负例拒绝，最终19项quota及availability边界探针全部符合预期。0新增网络。链式回执`architecture-baseline/position-preflight-audit-v2.json`，Checker最终SHA256 `253407959fcea350a811e4731a883af7dbaafa62f3d91b9146c48f0adcd62625`。
- 旧Query Collector8项、来源Checker14项均通过；预算3项、Worker作用域3项、分派2项通过。评分回归2项通过、旧预测fixture缺失2项自跳过，未称完整历史链全量复测。
- Vue `pnpm run build`含`vue-tsc`通过，见`frontend-wording-build/receipt.json`。API与浏览器正式结果待新报告发布；不会把构建成功当作视觉验收。
- 既有LLM网络23项基线仍有1个失败子断言、4个ConnectTimeout错误；这在V3编码前已复现，源码/测试未变，保持独立记录。
- 真实执行前12份旧报告DB行、原字节、manifest、复算分数及证据映射不变，见`preservation-pre-formal-run.json`；旧2290及旧ERC20经生产`Repository._load_report`重放通过，0网络。

## 正式执行与已定位的平台错误

Brain作业`0f2bb92f-9603-4633-ad41-783f2dbcb1bc`由API提交，现有Worker显式单身份`--once`自动完成注册认证、协议发现、十槽A、固定七任务的20个参考RPC和七次真实业务调用。原件在`runtime/generic-evaluation-20261019T181403Z-ea6a1c57`。七任务均由Position来源重建为PASS，暂算A93.37/F100/B及综合null。

首次发布于02:22被generic来源门拒绝，作业FAILED，保留`automatic-brain/result.json`及worker.log。原因不是业务错误：Position为认证先前主机停止而完整引用同run availability原件，旧generic最终槽位完整性比较误把引用同一plan的七条F也计入A，得到17对10。最小修正仅在最终A槽列表中筛选`purpose=availability`，原10槽顺序/输入/响应及F完整重建不放宽。真实原件3项回归通过（5.486秒、0网络/DB连接）：正式加载成功；缺A/乱序A仍拒；F任务篡改仍拒。没有删除依赖、改变分数或改写原件来绕过门禁。

Hallmark单次Worker结束、队列为空且无竞争Worker后，已仅恢复本次Brain作业的发布阶段：先离线生产门验证原件、核对job ID/身份/时间/SHA与FAILED状态，保存失败行和全部文件SHA，条件重排同job，复用既有claim/fence/verify/finalize来源门入库。恢复0公开请求、0业务重试，全部原文件SHA不变，回执`brain-publication-recovery/result.json`。首次失败继续保留，不声称Brain首次运行无故障，也不冒称这是无需恢复的完整自动成功。

Hallmark作业`1ae43746-d6c4-4c5d-b3f5-b30e20d08618`于02:24由同API提交、同Worker单次流程开始，02:31自动COMPLETE/DONE并发布；无需人工补样本或发布恢复。

## 正式结果与跨提供方复用结论

| 提供方 / BSC ERC-8004 | 协议与适配器 | 真实任务 | A | F | B / 综合 | 正式报告 |
| --- | --- | --- | --- | --- | --- | --- |
| Brain/BOBAI #49467 | MCP，`brain.position-look/v1` | 7 PASS / 0 FAIL / 0 UNKNOWN / 0 N_A | 93.37（10PASS，p95 3985ms） | 100 | null / null，PARTIAL | `bb885c5a-b8f0-42c0-94b0-42b10dfc4fc0` |
| Hallmark #338475 | A2A，`hallmark.range-analyse/v1` | 7 PASS / 0 FAIL / 0 UNKNOWN / 0 N_A | 93.68（10PASS，p95 3844ms） | 100 | null / null，PARTIAL | `b4139624-7434-405b-a1dc-19e0328584f4` |

两个完整身份均为`eip155:56:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:<ID>`；提供方归属来自分别认证的注册端点、服务资料和公开源码，Hallmark Card明确organization，不能只凭两个ID认定不同提供方。两方共用Checker `query.pancakeswap-v3-position/v1`、政策`service-contract-v1`+ADR0013、同一任务配置及同一BSC静态核心；只有协议输入输出Adapter不同。核心和调度没有49467/338475分支，不以相同答案互证。

| 预冻positionId | fee | tickLower / tickUpper | Brain独立核验 | Hallmark独立核验 |
| --- | --- | --- | --- | --- |
| 7637521 | 500 | -60370 / -56730 | PASS | PASS |
| 1 | 500 | 40950 / 44890 | PASS | PASS |
| 1061890 | 500 | -2210 / 1810 | PASS | PASS |
| 2329346 | 100 | 16791 / 16798 | PASS | PASS |
| 4312849 | 100 | 21113 / 21153 | PASS | PASS |
| 5968095 | 100 | 78328 / 78369 | PASS | PASS |
| 7686767 | 2500 | -82200 / -80050 | PASS | PASS |

每条同时严格比较完整token0/token1地址；完整统一输出、独立expected/claimed、区块hash、owner参考及所有原件路径在`formal-source-replay.json`和两份report的逐样本解释中。Brain输入`{"position":"<ID>"}`；Hallmark输入`{"chainId":56,"tokenId":"<ID>"}`。每个任务的请求计划、观测和业务响应为对应目录`position-business-<ID>.*`，参考为`position-reference-<ID>-positions.*`及`-owner.*`，可经报告证据API下载。

Brain正式原件目录`runtime/generic-evaluation-20261019T181403Z-ea6a1c57`，独立确认块`0x7aa4c34`（128601140）；Hallmark为`runtime/generic-evaluation-20261019T182432Z-2be65bbc`，确认块`0x7aa50e7`（128602343）。两次各48个逻辑公开请求，其中仓位阶段27=6共享RPC+14逐NFT RPC+7业务。两次均在64/28预算内、0重试/模型/支付/签名/链写入/外部委托；每个正式任务只计一次。可行性两次pilot不补正式七槽，也不重复计分。

两份报告各188个允许下载的公开证据文件；正式生产`Repository._load_report`已再次离线完整来源重放，和数据库report/manifest SHA、validated JSON及evidence_files完全一致；同一Checker、提供方互异、配置/政策SHA及任务键一致。0 socket，结果`formal-source-replay.json`。这证明本狭义能力跨提供方真实复用和正式发布成立；Brain首轮发布需一次已说明的平台恢复。

B无独立履约任务，不把查询无交易当B100；综合继续null，不重分配权重。A只代表MCP发现接口采样；F只代表列明五字段的仓位读取，均不代表Agent所有能力通过。

## 接入边界、运行状态和剩余限制

输入同类新身份可经现有身份/发现/Dispatcher自动匹配，前提是认证BSC注册文档、登记的已审端点、精确Schema/免费无鉴权契约及独立RPC均满足。当前Adapter仅允许Brain和Hallmark两个经源码审阅的端点，**任意新提供方即使工具同名也不会自动执行业务**，需要先审阅并增加轻量Adapter；共享oracle/评分无须复制。新能力不适配时仍走已有证据路径并保留PARTIAL/NEEDS_INFO，不凭LLM补分。

最终旧12份report数据库行、report/manifest字节、原分数及证据映射全部保持；正式重放2290与旧ERC20通过。数据库**13 Agent / 14报告 / 7作业 / 0活动任务**，API/PG健康。`preservation-after-publication.json`保存逐报告核对；未重复耗时全部历史链语义导入，不声称全测试绿。没有commit/push/reset，开工已有修改保持。

最终`preservation-final.json`再次确认上述状态；`final-workspace-scope.json`证明开工81个脏文件中73个原字节未变、8个只在声明范围增量修改，没有删除原文件，HEAD仍`3a680f3c5c82b51d3cc0b6fd51eb32bbb1cc9b39`。新增文件及原先干净的registration_discovery预算改动属于列明范围；无新依赖。`git diff --check`通过，正式绑定的ADR/任务配置及Checker最终SHA保持。

两次scoped Worker均已退出，常驻公开执行从未开启。恢复默认不带公开flags的Worker启动被自动审批拒绝，工具仅返回`blocked by policy`，未提供具体原因；未尝试绕过。**当前没有常驻Worker**，网页和已有报告仍可浏览，但新提交会留在队列直到Worker启动。收据`resident-worker-restore-blocked.json`。如用户手动恢复，在项目根目录另开终端运行`.venv\Scripts\python.exe -X utf8 -u -m reputation_platform.worker`；默认public-off，勿加公开参数。

前端类型检查/构建通过。真实loopback API验收16个GET/16连接通过，0外网/写入/新作业：两新报告模型重算、Agent历史归属（Brain2份、Hallmark1份）、两份业务原件下载逐字节一致、私密路径各404、旧COMPLETE/2290/旧ERC20评分及Checker兼容、HTML/JS/CSS与当前dist一致。新JS SHA256 `e38eee144feec72d98445eef56d56a787f63ddd12d0e83714a84d20c134b9598`。首次验收脚本误用strict模型直接读dict而本地失败，保留3次GET响应；按生产移除computed scores再JSON解析/重算的模式修正后上述16项通过，总计19次loopback GET，不隐藏首轮失败。回执`live-api-frontend-acceptance/result.json`及`acceptance-summary.json`。

真实浏览器视觉验收未完成：CUA没有browser provider，按`computer-use`技能尝试sky后工具停止，原文为“Computer Use has been stopped for this turn because it could not determine the current browser URL on Windows with enough confidence to enforce policy. Stop your work and send a final message noting why Computer Use ended.” 已停止，没有截图或视觉通过声明。原文及手工五场景/390×844步骤在`live-api-frontend-acceptance/`。

本地已运行网站入口为[http://127.0.0.1:7754/](http://127.0.0.1:7754/)。直接打开[Brain新报告](http://127.0.0.1:7754/?agent=agent-e9357377962d8c944359ca49&report=bb885c5a-b8f0-42c0-94b0-42b10dfc4fc0)或[Hallmark新报告](http://127.0.0.1:7754/?agent=agent-0e9825a984849eea12b970ac&report=b4139624-7434-405b-a1dc-19e0328584f4)，核对PARTIAL、两维数值、七F样本、Checker/协议、范围及下载；旧三场景精确链接见`browser-cases.json`和`browser-checklist.md`。桌面和390×844人工确认布局/滚动/证据入口即可，无需再次创建评价任务。

剩余技术范围：线上部署与公开源码字节等价未证明；不评价动态tick/流动性/费用和策略收益；历史任务NFT未来burn或RPC不足会保留UNKNOWN；HeyAnon认证原件仍受IPFS故障/限流阻断；LLM旧网络回归问题独立保留。
