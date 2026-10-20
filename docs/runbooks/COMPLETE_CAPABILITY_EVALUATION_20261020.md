# 完整能力评价扩展 · 2026-10-20

状态：本轮授权范围内的实现、两份真实完整评价、正式发布、API与离线生产来源验收已完成。常驻Worker及浏览器视觉验收保留此前策略拒绝的边界。

## 基线与历史保护

开工数据库13 Agent、14报告、7作业、0活动任务；10份完整、4份PARTIAL。`runtime/complete-capability-20261020/opening.json`保存14份数据库行、report/manifest SHA和复算分数及开工脏文件SHA。此前未提交成果保留；无commit/push/reset。旧v1配置、ADR和报告不改写。

## 政策与实现

新增[ADR-0020](../adr/0020-observable-service-fulfillment.md)与`service-fulfillment-v1`。A仍是十次MCP发现接口可用性；F七任务核五项静态事实；B另外七任务核认证服务、请求ID、任务对象绑定、完整交付、预冻30秒观测窗口。B不核事实真值、不声称全部行为或内部计算可证。迟到/网络/依赖错误UNKNOWN；错关联/错误交付/有效请求明确方法或参数拒绝才FAIL。保留10A/7F/7B、30/40/30及互斥规则。代码：`query_fulfillment.py`、`position_fulfillment.py`和原generic来源门。

规划器从同一认证NPM固定head-64区块读取totalSupply及14个中点分位tokenByIndex；前7F、后7B，B排除旧F对象。不存在Agent ID判分、固定Agent专用NFT或答案选择。枚举独立证明B对象存在，F另读positions；选择、参考和全部输入先冻结，再调用业务。缺失/冲突不补样。代码：`position_planner.py`。

`position_contracts.py`和`configs/position-adapter-reviews-v1.json`将已审端点、真实Schema、零费用/无副作用条件、协议输入输出映射及117项审阅依赖SHA配置化；新同类提供方仍需真实身份认证和安全审阅，不能靠同名工具或LLM取得执行许可。离线第三提供方/改名工具复用不代表已真实评价第三提供方。

来源Verifier重放登记/发现、全部参考RPC、选择及执行时序、真实输入输出、全run计数及所有请求的主机停止，逐字重建样本和能力；报告中的PASS不能自行通过。Collector与Verifier使用不同入口但复用确定性判据。旧v1仍走原来源验证。

## 真实评价与发布

Brain的新正式报告为`0812985f-8777-4629-8fba-3db4b3e1e65a`，原件目录`runtime/generic-evaluation-20261020T082507Z-7406b7e4`。实际63公开请求、14业务调用，10A/7F/7B均PASS；A=80（p95=17610ms）、F=100、B=100、S=94，COMPLETE。分数属于本次协议发现与仓位查询范围，不是Brain所有能力的全局分。

首次发布遇到平台来源分派错误：旧Mech校验误把所有B样本当作Mech任务。修正generic入口，只在存在Mech冻结计划时调用该校验，仍由最终门拒绝未核验业务样本。新增4项真实来源回归通过，旧Position真实回归3项通过后，同一新job通过更高fencing token和正式`finalize_job -> _load_report`恢复发布；未重复采集。所有本次原件/report/manifest SHA恢复前后相同，首次FAILED回执保留在`automatic-brain/first-attempt-result.json`，诊断及恢复收据同目录。

Hallmark的新正式报告为`c88165ca-df10-4cb2-aeb2-6e8680c605c2`，原件目录`runtime/generic-evaluation-20261020T085451Z-32e1fbd4`。现有Worker一次自动完成`QUEUED → COLLECTING → VERIFYING → REPORTING → DONE`，exit0；实际63公开请求、14业务调用，10A/7F/7B均PASS；A=80（p95=15500ms）、F=100、B=100、S=94，COMPLETE。两次均零费用、业务重试、签名、写链和委托。运行意图、作业终态及API报告分别保存在`automatic-brain/`、`automatic-hallmark/`。

| 提供方 | 协议 | A | F | B | 综合 | 实际样本 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Brain #49467 | MCP | 80 | 100 | 100 | 94 | 10A / 7F / 7B |
| Hallmark #338475 | A2A同步Message | 80 | 100 | 100 | 94 | 10A / 7F / 7B |

两方F/B均满分只说明本次静态事实和同步交付任务通过，不证明更复杂能力已被区分。A的p95均超过既有10秒延迟零分边界，10次成功贡献80分，因此两者同为94；未人为制造差异，也未改变权重、阈值或挑样。新政策分不与历史交易履约分直接排名。

## 阶段测试

- 原Position基线38项通过；规划5项、协议审阅8项、B判定7项通过。
- 新Collector/来源重建6项通过（双协议、42请求、14槽互斥、F错事实/B通过、归责、缺参考/预算、冻结/输入/槽位/身份/报告篡改）。工程数据为离线夹具，不计真实Agent成绩。日志`runtime-regression/position-fulfillment-tests.log`。
- 旧真实Position来源回放3项、评分1项、分派2项、Worker作用域3项通过。
- 最新来源守卫定向2项通过（96.203秒、源码前后SHA相同）；新generic真实报告来源4项通过（30.421秒、0跳过/网络/数据库访问），涵盖24样本正式加载、缺计划/未核验B、判定/任务/身份/真实请求输入篡改拒绝。首次负例构造被更早数量门拒绝的测试失败原样保留，修正合法PARTIAL构造后命中预期来源门。
- LLM网络基线46项有3失败子断言及6错误；原证书上下文初始化挤占短预算的根因经受控时钟红测证明，最小修复保留TLS验证和超时断言。修复后49项及相关9项通过，0真实socket，未测试真实LLM服务调用。详见`runtime-regression/result.json`。
- 因最后修复审阅配置版本选择，必要回归重新运行：新版本/路径/摘要负例2项、原Collector 6项、契约8项共16项通过（212.633秒，`review-version-tests.log`）；未重复其余套件。另独立生产单项通过，实际重放两份旧intent的新报告，部署选择故意指向不存在文件时仍保持全部样本、分数和report/manifest SHA（9.172秒，`review-version-production-replay.json`）；六个网络/DB守卫均0，首次独立审计及冻结v1未变。第三提供方仍只是离线夹具。

## 其他PARTIAL与界面

`ui/PARTIAL_REVIEW.md`及`partial-evidence-review.json`逐一索引真实原件：旧Activity仍严格空输入，仅1独立F任务，不能重复凑7；Clawdia缺认证IPFS文档、受控无委托路由合同、独立候选/路由oracle与真实Task历史；不执行route_task或假设budget=0/dry-run。现有其他查询工具属于不同能力，不能移用本次仓位成绩。

现有Vue新增按能力的历史报告覆盖表、四态/缺项、Checker版本与B政策语义；不聚合全局Agent分。未绑定业务能力的A保留报告范围，不传播给每个工具。最终审查修复原目录混排不同政策综合分的问题：仅保留最近更新/名称排序，默认及重置均为最近更新，保留每份报告的范围分。真实13 Agent目录的实际比较函数定向断言通过，Vue类型检查/构建重新通过；API返回的首页和新JS/CSS与dist逐字节相同。

最终验收`ui/final-ui-acceptance.json`为PASS，明细`ui/final-api-acceptance-20261020T092317945659Z/result.json`：34次loopback GET，核对两新报告分数与10A/7F/7B、F/B互斥、原件下载字节、私密路径404和14份旧报告/report/manifest保持；没有新提交或外部业务调用。`ui/final-capability-check-result.json`确认Brain53项、Hallmark7项未测能力不继承F/B，A仍属报告范围，两提供方不冒充两个能力类别。排序与构建记录为`ui/directory-sort-check-result.json`、`ui/final-directory-build.log`。

已增加数据库`worker_heartbeats`、`GET /api/runtime`和前端15秒轮询，分别展示API、数据库、队列及Worker。心跳90秒过期；启动/续租更新在线状态，正常退出记stopped。5项状态测试包含独立PG schema事务全回滚，另3项旧Worker作用域、Vue类型/构建检查通过。已在零活动作业时初始化表并重载API，真实Brain运行中scoped心跳已记录；未恢复常驻Worker。生产表初始化仅增加心跳表及复用既有幂等DDL，不改旧报告行。

## 历史保护与视觉验收边界

`historical-evidence-bytes.json`逐一核对14报告的16016引用、15136唯一原件、79807509字节，SHA全部匹配，0缺失/冲突/改动；此次审计0网络/数据库连接，耗时333.453秒。最终`final-independent-audit.json`为PASS（51.453秒）：数据库只读一致性快照为13 Agent、16报告、12完整报告、12个不同完整身份、9作业、0活动；14份旧报告开工捕获的7个发布字段、report/manifest、重算分数与证据映射保持。

最终检查复用上述全SHA有效回执，逐件核对原映射、尺寸与审计后mtime；没有重复全量哈希或旧报告全链语义重放，元数据复查不能抵御故意同尺寸修改并恢复mtime。两新报告则分别通过正式`Repository._load_report`离线完整重放，样本/能力/分数与数据库一致，各358项公共证据映射一致；socket connect/connect_ex/create_connection、DNS、psycopg及Repository连接六个守卫均为0。审计脚本四项复用自检通过，没有生产数据库写入。

此前浏览器工具因无法可靠识别Windows当前URL被自动策略停止，原始回执仍在`runtime/cross-provider-checker-20261020/live-api-frontend-acceptance/sky-stop-receipt.json`。本轮未重试或绕过，没有新视觉截图或视觉PASS；人工桌面/390×844清单为`runtime/complete-capability-20261020/ui/MANUAL_VISUAL_CHECKLIST.md`。

## 人工运行步骤与后续准入

API已在线时不要重复启动整个平台。人工恢复默认public-off Worker可在仓库根目录另开终端执行`.venv\Scripts\python.exe -X utf8 -u -m reputation_platform.worker`；Ctrl+C停止。默认模式只消费队列并说明未开启公开取证，不生成新的真实业务分数。此前自动审批拒绝仍适用，本轮不执行该常驻启动。运行状态以`/api/runtime`为准。

受授权的单次只读评价沿用`--once --enable-public-readonly --public-reference <canonical> --public-request-timeout 45 --proxy http://127.0.0.1:7897`，先确认零活动作业和无其他Worker；`--once`不按身份过滤队列，其他身份保持public-off。Brain/Hallmark两次原始运行目录采用独占创建，禁止再次运行同provider来补样。遇发布错误只核验并恢复原件，不重新业务采集。

新提供方需认证ERC-8004注册文档及精确服务端点、真实工具Schema/Agent Card、安全审阅的免费只读无委托契约、支持现有输入输出映射，并获限定执行授权。符合现有映射可复用原Checker，不需Agent专属评分；新输出语义或异步Task需审阅适配或新政策。当前只有两个真实提供方；第三提供方/改名工具测试是工程夹具，不能宣称第三份真实成绩。

最终发现并修复审阅配置扩展的历史兼容问题：原地向v1配置追加提供方会破坏旧manifest哈希。现在后台通过`REPUTATION_POSITION_REVIEW_CONFIG`选择新的、不可变的仓库相对配置路径；Collector在业务前的intent中冻结`review_config_path`，Verifier只按该路径及manifest/依赖摘要读取，不读取当前部署选择。两份旧intent没有该字段，严格按原v1核验；显式无效路径、缺原件或摘要变化直接拒绝，不回退其他版本。原v1及117依赖全部保留。新增版本仍须先完成实际安全审阅，设置环境变量不构成执行许可。实现为`position_contracts.py`、`position_fulfillment.py`，用法见`.env.example`与README。

新文件可命名`configs/position-adapter-reviews-v2.json`，其中`schema_version`仍为`position-adapter-reviews-v1`，因为审阅集换版没有改变JSON格式。未设置环境变量使用原v1，显式空串或缺文件则失败，不自动回退。

## 运行限制与后续

开工无常驻Worker。旧恢复默认public-off Worker的自动审批仅返回`blocked by policy`，未给更具体理由；本轮不绕过。API曾为新policy重载：首次脚本在子进程退出后发现venv父启动器已自动退出而报128，确认端口关闭后继续恢复API成功；未启动Worker、未影响数据库或报告。收据`api-reload.json`。

已完成两次限定真实评价、正式发布、生产来源重放、历史保护与API/Vue验收。常驻Worker未启动、桌面/移动视觉NOT_RUN；人工步骤和清单已提供，不把这些受阻项标为通过。Clawdia及旧Activity保留PARTIAL；陌生接口、异步Task、动态同状态oracle及更丰富业务能力需要真实契约和独立证据，不靠新增空Checker补齐。本轮不commit/push/reset，新两报告未加入原10份公开发布包。

本文中的`runtime-regression/`、`ui/`均相对`runtime/complete-capability-20261020/`；生产模块均在`services/platform/src/reputation_platform/`。
