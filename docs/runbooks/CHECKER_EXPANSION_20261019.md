# 能力 Checker 渐进扩展与验收

日期：2026-10-19。当前任务：`CAPABILITY_CHECKER_EXPANSION`。本报告随实现更新；工程夹具、真实公开取证和历史离线复核分别记录。

## 基线与改造依据

已阅读指定架构审查、历史评价 runbook、README、PLAN、STATUS、相关 ADR，并核对 Worker、通用评价、协议发现、身份来源复核、评分、报告、数据库和 Vue 调用链。现状确为共享队列/身份/证据/评分底座加固定业务分派，并无可注册的通用业务 F Checker。

- Git：`main`，HEAD `3a680f3`；开工已有 LLM、网络、Worker、启动脚本及文档等未提交改动，保留，不 commit/push/reset。原始状态和已修改文件摘要保存在 `runtime/checker-expansion-20261019/baseline.json`。
- 环境：Python 3.12.4、Node 22.17.0；全局 pnpm 10.12.4，项目入口实际使用声明的 pnpm 11.25.0。已有锁定虚拟环境和前端依赖，不新增依赖。API 7754、PostgreSQL 55438 已运行。
- 数据库：11 Agent / 11 报告 / 4 历史作业 / 0 活动作业。常驻 Worker 仍 public-off；不绕过此前常驻公开启动拒绝。
- 评分基线：`test_scoring`、`test_generic_scoring`、`test_planning`、`test_worker_scope` 共5项通过。`test_prediction_scoring` 因旧 pilot 原件缺失跳过，不计通过。前端生产构建通过。
- 历史基线：10份公开报告重新计算分数、核对 report/manifest SHA、与数据库分数比较均一致；2290 的88项manifest输入摘要及 `verify_generic_report_sources()` 通过。未重复约13分钟的全量链语义导入。收据：`runtime/checker-expansion-20261019/historical-baseline.json`。

核对发现的约束：

1. `generic_evaluation.verify_generic_report_sources()` 目前只接受协议发现 A 和独立重建的 Mech B；不能把 Checker 上报 PASS 直接加入报告。
2. `service-contract-v1` 已支持七个全部可判、互异且绑定能力的 F 任务。无需改权重、门槛或历史政策；B缺项时综合分继续为null。
3. `registration_verified` 只证明固定块的链注册读取，不证明注册JSON已取得或端点已认证。目录缓存不是认证后的注册文档；通用IPFS读取尚不含CID/DAG认证。新正式F必须处理这一来源边界。
4. 真实job阶段为QUEUED/COLLECTING/VERIFYING/REPORTING/DONE；前端只能展示这些实际状态及后端消息。

## 最小实施顺序

1. **真实候选调查**：复用群体声明清单，跨提供方筛15～20个候选，保存有界公开目录/协议发现原件，区分声明覆盖、同一对象可测覆盖和已完成评价覆盖。优先Query/Tool，另研究Clawdia的Routing约束。
2. **首个Query闭环（有真实适用对象才实施）**：定义固定任务/参考来源/安全许可，复用DiscoveryEvidence与可信RPC；同时实现从原件重建的来源Verifier、七槽F及必要负例测试。尽可能用不同提供方复用，禁止按Agent ID分支。
3. **最小调度（在首个真实闭环成立后）**：在现有通用入口增加简单静态Checker分派，保留预测和增仓成熟路径、单报告政策与任务互斥，不预建未有真实对象的评分器。
4. **独立前端改进**：修改App/ReportView/ScoreCard及必要样式，突出已有政策、范围、逐能力实际F/B覆盖、样本四态和时间；提交文案准确表达请求与真实Worker状态。复用现有页面，不伪造Checker元数据或进度。
5. **Routing与LLM边界**：仅在安全任务及独立预期成立时接正式评分。LLM沿用现有有出处声明机制，不用于改判或直接给分。
6. **最终验证**：相关工程测试、真实证据与正式入库校验、十份历史及2290回归、真实API/数据库/浏览器检查；逐项记录未达成原因和启动方式。

上述为开工计划。调查后没有凑七个重复任务，而是保留一次无参数调用为一个真实F事实样本；实施进展如下。

## 阶段一：真实候选与安全调查

完整清单见 [候选研究](../research/AGENT_CHECKER_CANDIDATES_20261019.md)：20个真实身份、六条链；覆盖Query、Prediction、DeFi、Routing及开放任务。调查批次26个观测，其中23个完整HTTP200、2个body timeout、1个连接失败；含可能的在途请求保守上界27。该批次不执行业务工具、RPC、模型或付款。

优先对象为 Brain BNB #49467 的公开查询。Degen Ethereum #23121虽有零价发现工具，但动态价格无固定oracle，且Ethereum尚无本项目可信RPC注册来源；Arena Base #18500有免费profile查询，但登记IPFS读取失败，且不是同一业务判据。不能以共用HTTP执行器冒充同一Checker的跨业务复用。

源码安全调查另进行了六次有界不可变GitHub blob读取，四项成功且校验Git blob SHA1，两个超时原件未采用。只批准 `bobai_activity({})`：源码仅读取固定公开活动日志或本部署静态ASSETS；常规访问统计/缓存经过审阅。返回的付款、捐赠或其他链接只作数据，不跟随。预检工具的元数据来自六小时缓存，不能把其税测量block误作所有字段的固定块oracle，故未实现宽泛“token安全评分”。

## 阶段二：首个真实Query事实与独立核验

Brain规范身份：`eip155:56:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:49467`。链上tokenURI为JSON data URI，原始ABI及解码内容核对成功；owner初次超时后另做一次同固定块的有界补读，保留原失败，不伪造证明。认证注册文档明确登记 `https://brainonbnb.com/mcp`。

实际业务只调用 **一次** `bobai_activity({})`。首次fresh tools/list大体积响应超时后未重试；采用已经成功保留的原始工具目录与后续成功初始化。调用前计划、真实请求、响应及后建索引分开标记。原始15秒RPC四次超时均视为平台UNKNOWN；后续使用现有SafeHttpClient的45秒选项，限定六个可信BSC RPC读、零重试，全部成功；没有新增业务调用或绕过DNS/TLS/代理控制。自动Collector继续使用既有默认超时，不宣称网络稳定性已全面解决。

- 返回交易：`0x41da02b6e7e36aae1b74e336b8975afd1a71813f3d8b8e6b85208940b043eb37`。
- 交易块128175989、独立head128574951，确认距离398962。
- 目标token：`0x245c386dcfed896f5c346107596141e5edcbffff`；预定接收地址为dead。
- 固定交易块的decimals=18；全部目标Transfer合计11768639803124515570716 base units，即11768.639803124515570716；正数half-up取整11769，与真实返回11769一致，**F样本PASS**。
- 未安排十槽A采样，仅有一个F任务，无B任务，所以 **A/F/B/综合均null，PARTIAL**。工具查询成功不等于评分门槛满足。

原件位于 `runtime/checker-expansion-20261019/query-pilot*`、`brain-owner-supplement`、`query-oracle-supplement`；独立复核收据为后者的 `independent-review.json`。正式来源回放的报告位于 `runtime/checker-expansion-20261019/real-query-report`。报告构建脚本只离线关联这些真实原件，未再次调用Agent。后建索引不冒充调用前计划。

## 阶段三：最小Judge与Checker实现

新增 `query_oracle.py`：纯确定性ERC20记录判据，无Agent ID、网络、队列、模型或评分分支。独立数据需先由调用层认证；核对chain/head/tx/receipt/header、交易位置、所有日志归属及唯一位置、removed和固定块decimals；全量聚合后用整数运算取整，无浮点容差。

新增 `query_checker.py`：受审阅端点/Schema/输出映射是协议适配器，业务判据单独复用。准入需要链注册和认证文档、匹配MCP端点、严格空对象Schema及实际初始化；未认证IPFS文档不触发本Checker。调用前和报告回放共用相同发现校验；一次tools/call，至多六个只读RPC，费用零、重试零。一个无参工具输入具有固定task_key，不能换request ID凑成七个任务。

来源Verifier重读全部manifest依赖、注册证明闭包、原始请求计划/observation/raw以及独立RPC方法和参数，从原件重建整份SampleExplanation和Checker能力元数据；不信任Checker上报PASS。完整确认的业务矛盾FAIL；合法网络/授权/工具错误UNKNOWN。文件缺失、SHA变化、归属/请求/计划/报告篡改则拒绝发布，不能用UNKNOWN掩盖完整性错误。规则单独记录于 [ADR0012](../adr/0012-query-transfer-record-checker.md)，未改旧ADR或评分。

最终审查补上Checker元数据的来源闭环：没有Query计划时冒用本Checker标识，或在合法计划旁挂未重建的Query能力，都会被拒绝。新增两个负例测试；其他Checker标识仍由各自的核验规则处理，不把本规则扩成未来插件的统一限制。已发布真实报告再次只读加载通过，未改报告、ADR或分数；收据为 `final-query-source-review.json`。

新增 `checker_dispatch.py` 静态注册表，将Query和既有Mech历史履约收集接入通用入口。原预测政策仍走既有优先分派，Brain增仓及Worker profile路径保留；Mech历史补取只重跑Mech，避免重复Query。没有动态插件、微服务或新依赖。

能力结构仅增加兼容可选的 `capability_type/checker_id/checker_version`，旧数据默认null，重新生成共享Schema与TypeScript。未为旧报告猜测补写Checker。评分函数、数据库schema及API路由未改。

新Agent路径为：原有规范化/注册发现 → 既有Prediction优先匹配 → 协议发现与A采样 → 静态业务Checker匹配 → 已审阅单次Query或Mech历史 → 原件重建 → 既有评分和数据库发布。未适配的能力仍保留声明、缺项及部分报告。常驻public-off下提交准确返回NEEDS_INFO，不发外部请求。

## Routing与LLM边界

Clawdia #2290 `route_task` 只有task_description及可选credits预算；未发现dry-run、固定候选集或禁止下游委托约束。它可能收费或启动下游任务，因此未执行，不开发或启用正式Routing评分器。现有2290报告继续仅A=90.87。

本轮确定性Checker不需要模型。既有DeepSeek声明提取/解释路径保留；LLM不授权工具、不替代oracle、不改判、不调权重；模型不可用不影响本规则。开放内容主观评分与非交易B均未新增。

## 前端与当前验收

沿用Vue页面，突出COMPLETE/PARTIAL、政策、逐能力实际F/B样本数、四态统计、缺项、范围及时间。新能力卡直接展示后端实际类型和Checker版本；旧字段缺失显示“未记录”。提交按钮改为“提交评价请求”，执行阶段和时间来自真实job；不展示虚构七阶段或百分比。

前端构建通过。真实浏览器已检查原完整历史对象、2290 PARTIAL及public-off提交结果；保存history-report/history-scores/clawdia-partial/public-off截图。public-off测试只新增一个NEEDS_INFO作业（950a604e-b7c2-4e7d-9ecb-c4c11b69e823），没有新增分数。新增Checker报告的入库、最终API及浏览器验收继续见下方最终收据。

工程测试使用合成临时原件，与真实验收严格分开；真实单F样本不能用Mock补足。跨不同真实提供方复用尚未达成，不能宣称通用Query所有业务已经支持。

## 最终发布与真实 API 验收

真实报告已通过正式 `import_local_report.py` 来源复核和持久化校验入库：

- 报告ID：`888f98ca-0bc7-4a58-9de2-1f0626bc40a5`。
- Agent key：`agent-e9357377962d8c944359ca49`；Brain BNB #49467。
- 本地页面：[新 Query 部分报告](http://127.0.0.1:7754/?agent=agent-e9357377962d8c944359ca49)。
- 状态：PARTIAL；F样本1个、PASS 1个；A/F/B/综合分均null。不是新增完整评分对象。
- 最终数据库：12 Agent、12报告、5作业；其中10份原完整报告、2290 PARTIAL和新增Query PARTIAL。

`real-api-acceptance.json` 记录了连接实际数据库的 FastAPI TestClient 六项HTTP验收：health、12个Agent、报告/Checker元数据/空分数、真实证据下载及SHA一致、私密配置下载404、public-off作业NEEDS_INFO/DONE。该验收未再创建作业。另有运行中的API和真实浏览器检查，不把TestClient等同于网络服务验收。

最终来源修复重载后，又通过回环HTTP直接访问实际7754服务重复上述六项检查，全部通过；收据 `final-live-api-acceptance.json`。未创建作业、未访问公网，真实证据SHA保持一致。

已发布 `real-query-report` 及其manifest依赖保持冻结，尤其不再修改作为来源的ADR0012。离线构建助手增加已发布文件存在即停止的保护；后续复核应读现有bundle，不能重跑生成时间或覆盖报告。真实业务只调用一次；新自动Collector重构后没有再次调用真实服务，直接Collector路径的成功/失败/预算由合成工程测试验证，真实验收使用保留的真实调用及RPC原件重建。

## 测试结果与历史保护

| 验证 | 结果与边界 |
| --- | --- |
| Query oracle、来源重建、Collector | 最终30项通过（8 + 14 + 8），62.986秒，0失败/错误/跳过；匹配/错误Schema/归属/篡改、业务不一致、UNKNOWN/null、超时/429/停止及冒用Checker元数据均覆盖；全为临时合成工程原件 |
| Oracle异常输入 | 独立468次JSON类型变异未出现未捕获异常；不是468次真实评价 |
| 原评分/规划/Worker范围基线 | 5项通过；旧prediction pilot缺失项跳过 |
| 广泛既有回归 | 执行103项，记录2个失败子断言、8个错误、3项跳过；失败/错误均位于既有 `test_llm_network`，不能宣称全套通过 |
| LLM网络模块单独运行 | 23项、81.702秒；3个失败子断言、6个错误，仍未通过 |
| Vue/TypeScript生产构建 | 通过；最终JS `index-gP2GttWe.js`、CSS `index-DFOfNC5r.css` |
| 实际数据库/API | 上述六项通过，真实来源Verifier接受后才入库 |
| 历史/2290最终回归 | 原11份DB行和证据映射不变；report/manifest字节、重算分数一致；2290的88项输入及完整通用来源回放通过 |

广泛回归收据为 `regression-tests.json`；其中按测试总数减失败子断言计算的 `passed` 是粗计数，不应作为精确成功测试方法数引用。3个跳过来自旧预测pilot/原始LP报告未安装。`test_local_platform` 需要独立 `reputation_verification` 数据库及缺失旧夹具，本轮未对主库运行；实际主库已用上方专用API验收替代，二者覆盖范围不同。

LLM失败的只读诊断见 `runtime/checker-expansion-20261019/llm-regression-diagnosis.md`。已排除mock类身份不一致；既有网络实现把TLS上下文初始化计入3秒总预算，本机隔离测量约1.141秒，受控时钟可复现拨号前超时、mock拨号次数为0的症状。预建相同上下文时原失败断言通过，只是诊断证据，不能替代正常回归。原失败时缺少逐阶段计时，尚不能断言其具体耗时，也未独立证明本轮全部影响均已排除。没有降低断言、删除测试或修改既有网络代码来隐藏失败。

历史收据为 `final-history-regression.json`：还核对了17个本轮未碰的既有已修改tracked文件与开工SHA一致。开工已存在的untracked LLM文件没有同等初始SHA收据，不扩张该证明。没有重复约13分钟的历史全链语义重放。本轮不commit、不push、不reset，保留原有改动。

## 浏览器展示与本地运行

真实浏览器已从当前数据库验证三类页面：原完整 #2359（综合84.39）、Clawdia #2290（仅A=90.87）及Brain #49467（Query F 1 PASS、各分数为空）。目录显示12个Agent/10份完整评分；public-off提交显示真实NEEDS_INFO作业原因；浏览器console没有warn/error。截图位于本轮runtime目录：

- `history-report.jpg`、`history-scores.jpg`：完整历史报告及分数。
- `clawdia-partial.jpg`、`public-off.jpg`：协议可用但无业务判据，以及公开采集关闭的真实提交结果。
- `query-checker-page.jpg`、`query-partial-overview.jpg`：实际Checker/版本、Query能力、F/B覆盖、PASS证据及PARTIAL概览。

本机7754端口已有API，直接打开上述链接即可；无需另启Vite，也不要在已有服务旁再启动同队列Worker。API已安全重载以加载兼容字段及最终来源校验修复，原常驻Worker未重启、未加公开标志。最终重载收据为 `final-api-reload.json`。

需要重新启动时，在仓库根目录执行；先确认7754没有旧API占用。本机已有虚拟环境、已构建前端、数据库及私密配置，`uv`不在当前PATH也可用：

```powershell
pnpm --dir apps/web run build
& .\scripts\start_local_platform.ps1
```

脚本默认public-off，复用本机PostgreSQL配置；勿添加 `-EnablePublicReadOnly`。只需启动API且保留现有Worker时：

```powershell
& .\.venv\Scripts\python.exe -X utf8 -m uvicorn reputation_platform.api:create_app --factory --host 127.0.0.1 --port 7754
```

数据库URL来自环境变量或私密 `runtime/platform-config/database-url.txt`；不要输出内容。新机器的安装、独立数据库和 `.env` 显式加载仍按 [README](../../README.md)。本轮真实Query bundle依赖本机保留原件，尚未打包进原10报告的公开归档，不能宣称克隆仓库即可复现这份新报告。

工程复查入口（不调用真实Agent）：

```powershell
& .\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p 'test_query*.py'
& .\.venv\Scripts\python.exe -X utf8 runtime/checker-expansion-20261019/check_real_api.py
```

## 最终验收范围与下一步

| 目标 | 当前结论 |
| --- | --- |
| 原10份完整报告与2290保留 | 已验证；评分、证据、数据库兼容 |
| 按能力匹配的新Checker与来源重建 | 已实现静态调度、Query转账记录规则和兼容元数据，无Agent ID评分分支 |
| 新真实业务F事实 | Brain #49467一次真实只读调用 + 六次成功参考RPC，1 PASS，正式发布PARTIAL |
| 同一Checker跨两个提供方 | **未达到**；Degen可信RPC/状态条件不足，Arena登记资料认证失败且语义不同 |
| 新Agent提交后持续自动评价 | **未启用**；常驻public-off准确返回NEEDS_INFO。已授权的受控入口才可对严格适配条件匹配；不是任意MCP/任意Agent |
| 七个F任务及新完整综合分 | **未达到**；同一无参查询重复执行也只算一个任务；B无证据不补分 |
| Routing / Workflow | 仅真实工具调查；无安全受控任务/独立oracle，未调用、未正式评分 |
| 前端真实展示 | 三类报告、能力/Checker/四态/范围/证据/真实作业状态均已浏览器验证 |
| 各阶段与全套回归 | Query阶段及发布验收通过；广泛既有LLM回归未全绿，旧夹具项明确跳过 |

优先下一步是寻找第二个不同提供方、已认证且同语义的固定历史查询；在安全调用和独立参考均成立后再增加适配器。随后设计七个真正不同的任务及明确的B证据，不能以重复调用或拆分字段满足门槛。另应独立修复并复跑既有LLM短预算测试、补齐旧pilot夹具；公开Worker扩围需单独明确授权，Routing继续等安全任务模式和可归属交付记录。
