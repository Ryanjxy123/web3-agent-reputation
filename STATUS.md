# 新项目当前状态

更新日期：2026-10-18。task_id=`PREDICTION_EVIDENCE_EXPANSION`。当前已核实9个不同完整评分对象，新增2135为A97.05/F72.89/B100、综合88.27，原14任务、10次A和来源SHA全部复用；2267综合29.8保留。至少10个目标仍待完成。2150按用户批准的统一512条上限执行中，批次 `runtime/prediction-auto-batch-20261018T145833Z-77a6b75c/`，不能提前计为完整。 视觉BLOCKED，无远程配置。

## 本轮V2证据扩展

最新决定：用户批准512条上限与14不同问题停止规则，评分门槛不改。已重载单worker修订4，进程记录 `runtime/v2-worker-revision4-20261018T145816Z/process.json`。2150新job `50f827ad-be96-40ed-81c4-91e54776c32d` 正式取证中；原128条10题的PARTIAL保留。1722实际38条仅2题，本轮不重跑。

- [ADR-0016](docs/adr/0016-prediction-evidence-v2.md)：增加CID认证根File与完整包装原题精确关联，旧Directory与V1报告复算不变；无模糊题义匹配。V2按14个不同Question冻结7F/7B后才读输出，另10次A。
- 首批2135/2150/2267三任务全部结束：2135因直接原题尚未支持而无分；2150只有8个合格问题，F13.39/PARTIAL；2267为A99.34/F0/B0、29.8/COMPLETE。原批次 `runtime/prediction-auto-batch-20261018T135720Z-9a59504a/`，driver exit2/执行层exit1来自2135未被旧driver缺项枚举识别，并非三个平台作业失败。
- [ADR-0017](docs/adr/0017-prediction-question-and-output-contract.md)：先在三个对象的原件中比较格式，再以2135和2150真实CID/独立结算及提前交付证明直接单行Will原题可共用；2267首直接题交付过晚，明确UNKNOWN。来源研究57次只读请求、无output/模型/评分。直接原题离线提取及9项拒绝控制exit0。包装格式保留原方法严格重放。
- 输出核查已证实2150六个失败均无有效概率，2267七个功能输出均为Invalid response，低分有真实依据；prompt声明并无逐字回显原题义务。核验修订3仅供显式V2，按实际Schema及链上任务/CID关联，失败报告展示真实result。旧修订1/2保留；同样本说明修订不重采。
- 必要验证：两个真实根File/一个旧Directory及错误CID离线控制exit0；两真实包装题严格query重放与六项拒绝控制exit0；V1原报告独立复算、V2同概率信用及根File副本篡改拒绝的一项受影响回归最终exit0。该回归先因测试JSON载入方式、再因根File误用旧目录接口各exit1，修正后通过；未把失败抹除。共享Schema/OpenAPI生成exit0；前端首构建暴露可选policy字段类型问题，修正后最终pnpm build exit0。未重跑旧套件；视觉仍BLOCKED。

- **同协议历史事件与2135补充**：[ADR-0018](docs/adr/0018-marketplace-request-event-versions.md)。官方父版/变更源码和2135、2150两个真实对象先核实四参数事件；纯核验默认旧修订不变，显式新修订仍逐项核身份、授权、价格、接手、调用、CID与确认。`runtime/check_marketplace_event_revision.py` 一次必要实原件验证exit0：两旧事件UNKNOWN→PASS、2198当前事件整结果不变、7拒绝控制通过，0公网/模型/A。2135新报告 `9dbc7665-6942-4f7f-9af9-98229de3c0c2` 位于 `runtime/evaluation-report-20261018T145744Z-4d118477/`，A97.05/F72.89/B100、88.27；14任务、10A与原SHA不变。`runtime/append_prediction_event_revision.py` 最终exit0，真实PG独立导入、API200、旧事件回执附件200且SHA一致；首次沙箱本机PG10013 exit1发生在生成前，失败审计保留。发布审计 `runtime/prediction-event-revision-publication-20261018T145702Z-cfb27de2/result.json`。
- **扩大窗口**：[ADR-0019](docs/adr/0019-prediction-history-bound.md)在依赖实现前记录用户批准。V2自动接入统一512、旧profile/报告仍原值。新2150批次只提交一次canonical，不写对象专用profile。driver现识别V1/V2，旧driver退出2记录不改。
- **面向用户的摘要修正**：共用HTML/Vue明确区分没有有效概率、概率方向错误和履约中的约定输出差异，不将2267的Invalid response概括成链上交易失败。没有改分或覆写旧报告。可审阅包 `runtime/prediction-summary-presentation-20261018T150728Z-fc35cc3e/` 绑定原JSON和新HTML的SHA，离线生成最终exit0（首试严格模型载入入口错误exit1保留）；原分与源文件SHA保持。此次Vue实际变更后仅运行必要的 `pnpm run build`，exit0，新资源 `/assets/index-DEE3Wput.js`；未重跑旧套件，视觉仍BLOCKED。

## 当前完整结果

| 不同真实对象 | 评价范围 | A / F / B | 最新综合分 |
| --- | --- | --- | ---: |
| Brain DeFi #363709 | 历史增仓披露及完整步骤（特例） | 93.09 / 100 / 100 | 97.93 |
| Olas #2198 | 历史预测，prediction-history-v1 | 98.20 / 75.66 / 100 | 89.72 |
| Olas #2235 | 历史预测，prediction-history-v1 | 98.61 / 97.81 / 100 | 98.71 |
| Olas #2340 | 自动接入历史预测，核验revision2 | 98.51 / 79.33 / 100 | 91.28 |
| Olas #2182 | 自动接入历史预测 | 98.33 / 77.64 / 100 | 90.56 |
| Olas #2360 | 自动接入历史预测 | 98.33 / 72.79 / 100 | 88.62 |
| Olas #4110（service3786） | 历史预测及登记日期补录 | 89.69 / 53.89 / 100 | 78.46 |
| Olas #2267 | 历史预测V2，实际错误输出 | 99.34 / 0 / 0 | 29.8 |
| Olas #2135 | 历史预测V2，历史事件核验修订4 | 97.05 / 72.89 / 100 | 88.27 |

4110新报告 `6b4a1a7b-278b-48f0-88e8-980edc86129f` 已真实PG发布，原件 `runtime/evaluation-report-20261018T130748Z-45152bd3/amendment-result.json` exit0。原14任务与10次A复用，A/F不变；补登记证据后B可完整核验。旧PARTIAL保留，同身份多报告只计一个对象。范围分不代表整个Agent，历史入口A不代表实时推理在线。

## 旧版缺项与剩余扩展

下表为V1旧取证快照，不表示CID不存在。2267已由V2取得完整分；2135/2150进度见上。其余候选继续保留缺项。

| 对象 | 保留结果 | 处理 |
| --- | --- | --- |
| 2135 | 128份输入404，0合格市场 | 缺资料，不记预测失败 |
| 2150 | 109份输入404、10条无market_id、9条非支持工具，0合格 | 按缺项保留 |
| 2267 | 42份输入404、79条无market_id、7条非支持工具，0合格 | 按缺项保留 |
| 2359 | 只有6个合格市场，少于14 | 保留PARTIAL，不降门槛 |
| 4134（service3809） | 共用null CID解析已修；首条input是inline JSON（129/174字节），无request_context | 不为inline另开类别、不重跑；追加格式说明 |
| 1722 | 本次38条：36份输入404、2条无market_id | 新四对象批次0合格 |
| 2266 | 14份输入404 | 新四对象批次0合格 |
| 2673（service2661） | 29条：22份输入404、6条非支持工具、1条无market_id | 新四对象批次0合格 |
| 2699（service2685） | 2条：1次ReadTimeout、1条非支持工具 | UNKNOWN/不适用；超时不是平台逻辑bug |

后四对象批次 `runtime/prediction-auto-batch-20261018T125324Z-96bd00cd/qualification-summary.json` 已结束，新增完整对象0；driver exit2，PowerShell执行层exit1，未改Omen/cutoff/14条件。源中的缓存scope提示不等于上表真实资格原因，资格结论仍来自原输入/观测。4134说明报告 `e34a935a-13de-4608-a4ee-dcd51889ab2c`，目录 `runtime/generic-report-format-gap-20261018T125256Z-f7e7d0b1/`；原任务与缺项保留。

有限发现见[扩量调查](reference/PREDICTION_EXPANSION_DISCOVERY_20261018.md)。4160在原cutoff前为空页，未再评；历史概率校准3795/3798不冒充独立预测。注册声明充分仍可能缺足够历史，不把factory、工具Schema或名字当可测证明。

## 本轮补录、展示与验收

- **4110登记补录**：[ADR-0015](docs/adr/0015-registration-date-supplement.md)及共用helper仅接受绑定原history manifest/bundle的登记evidence/time/block。补1次确切目录GET+3次必要RPC，核唯一mint、同笔按序ServiceAgentLinked、agent4110/service3786与旧固定N；登记块47694994、UTC时间2026-08-12T23:45:35+00:00。补录源 `runtime/prediction-registration-supplement-20261018T130654Z-671d83aa/`，没有重采14任务/10A、调用模型或发链交易。正常真实PG发布exit0。两项负控产物显示错误身份/时间被拒绝；原执行退出码未回收，后续只读产物检查exit0，**不将负控原命令写成exit0**。
- **长验证租约修复**：`runtime/publication-lease-check-20261018T124836Z-c445e119/result.json` exit0，真实PostgreSQL验证107.05秒（含65秒本地延迟，用于验证续约）；第66秒竞争领取返回None、fence未变，旧token提交拒绝。该阶段同job恢复PARTIAL、A89.69/F53.89/B空，后来才由登记补录追加完整78.46。早期租约过期引发重复A采样的中断记录保留，不声称恰好一次；本次租约恢复没有新增A/公网/模型。
- **2340实现勘误**：[ADR-0014](docs/adr/0014-prediction-binding-verification-erratum.md) revision2正规解析Unicode JSON题干，取消额外内部prompt回显门槛；原83.01报告保留，revision1仍复算原分，更正为91.28。完全复用原14任务、10A及翻译；`runtime/prediction-binding-correction-20261018T121045Z-c0f88c67/{result,failure-controls}.json` 均exit0，真正不同题干/歧义目录仍拒绝。
- **逐功能展示已发布且分数不变**：2340报告 `c7eb4285-bd1a-456d-9a1e-34606e067b15`（`runtime/evaluation-report-20261018T123417Z-556b41e4/`）；2182报告 `1e7732c5-3a24-4582-9ca0-b0f4deedd1dd`（`runtime/evaluation-report-20261018T130123Z-25aa1c20/`）；2360报告 `63b17e17-3260-48f8-b258-67bdd68abf94`（`runtime/evaluation-report-20261018T130228Z-14e08e63/`）。各4工具/14真实样本关联，刷新脚本exit0、新网络/模型0。2340展示验收 `runtime/prediction-presentation-check-20261018T123347Z-7205aa6b/result.json` exit0；首次双origin复核exit1且未入库，修正后复用原件发布。
- **三个0资格说明**：`runtime/prediction-gap-publication-20261018T123936Z-2004616f/result.json` exit0，2135/2150/2267来源、样本、分数不变，correction错误SHA拒绝，新网络/模型0；缺资料没有补成0分。前端区分计划槽位与实际测得，最终受影响 `pnpm run build` exit0，无core/API Schema改变，旧工程测试不重跑。
- **早期自动流程仍可核验**：2340 `runtime/prediction-auto-platform-check-20261018T115048Z-fdb8afe6/result.json` exit0中83.01为历史初版，不是最新分；2198离线兼容 `runtime/auto-prediction-material-check-20261018T115122Z-f5a5d6fd/result.json` exit0、原89.72不变。旧运行profile/selection与错误身份控制保留，不伪造旧计划字段。

- **最终只读平台收口**：`runtime/prediction-batch-close-20261018T131251Z-ef4125f5/result.json` exit0，确认真实PG38候选/35报告/7完整/0active；4110新报告API200、补录附件200且字节SHA一致，网站与当前 `/assets/index-C2_SL-FZ.js` 均200。新公网/模型0；这不是视觉验收，visual仍BLOCKED。当前API在 `http://127.0.0.1:7754/`、仅一个重启后载入最新代码的worker保持运行；两个额外批量worker已停，旧三个已替换为一个。

## 下一任务与边界

预测证据扩展按ADR-0016/0017执行；已发布结果及当前批次以STATUS开头为准。 既有prediction-history-v1的三维、30/40/30、固定历史计划与原件继续保留；取得足够可核证据才发布新分数。

普通用户仍只提交canonical/注册页，平台自动核实登记与声明、匹配方案并执行，不手写profile或选方案。当前预测只支持已核Fixed Price Native与Omen/IPFS；订阅2469未适配。generic F及跨专项组合仍未实现，视觉BLOCKED。DeepSeek沿用现余额授权，不扩大为付费Agent/签名/资产操作。文档收口不测试、不联网；无远程配置。

以下保留已完成阶段的验收与原件记录，各轮数量是历史快照，当前统计以本页开头为准。

## 通用基线与共享履约的历史验收（2026-10-18）

本轮按群体调查接入跨工具Mech历史任务履约（交易行为维度），规则及身份来源条件事先固定于ADR-0011。12个身份有共享协议声明；两个旧来源各原七个行为任务实际涉及2、3种操作，合计4种，不依赖市场结算。ADR-0011的第二对象计数笔误在ADR-0012勘误，已引用的原文件不改。新对象按同一协议自动取证，不需运营profile。两个免费MCP事实查询候选缺共同固定块闭环且已有额度/传输缺口，本轮未重试，不把格式合规算作功能通过。

用户提出日常评分只测通用标准覆盖的项目，不能每次提交都等待适配。已记录 ADR-0009：可用性、声明与实际结果一致性、可归属交易履约使用共享项目；业务深度专项按条件附加。协议/证据适配一次供同类对象复用，未知项保留，其他已有评价照常展示。

通用指标与证据条件已固定于 ADR-0010，新增 `service-contract-v1`，三维及30/40/30不变。无预置profile的规范身份已可经API自动采集真实注册、按协议发现资料并发布缺项报告；逐功能记录范围、关联样本和缺证据。已完成3个真实身份的API→worker→PostgreSQL→报告与附件流程，原件见 `runtime/generic-platform-check-20261018T093143Z-c316e720/`：全部链上注册核实，均未取得完整三维分。随后只对新增的MCP描述文件格式做一次受影响实读，未重发其它对象。

当前通用适配器支持注册/协议发现、MCP发现接口可用性和Mech历史交易履约。真实输入、交付及链上归属已取得，但不证明预测概率、事实答案或收益正确；通用功能维度仍未接入，不能声称三维已全部完成。旧增仓/预测路径保留既有政策和原分数；不混用两种政策的样本分母。

### 本轮共用履约与补证结果

- 新增 `mech_task_identity/collection/evidence/resume`：链上桥、service/Mech/getter与tokenURI原件绑定身份，不把提供方域名或收款钱包当执行证明。新对象先冻结一页最多32条中的原七个不同任务，再取交易、请求、交付及CAR；逐工具绑定能力。历史时间和本次取证时间分别展示。
- `python runtime/check_mech_task_evidence.py` exit0：复用2198、2235的原七个行为任务，各7PASS，覆盖4种实际工具；错误身份及伪造判分均拒绝。无外网或新业务请求。结果 `runtime/mech-task-check-20261018T105653Z-850f26e7/result.json`。
- `python runtime/check_mech_task_platform.py` 首次exit0：未配置#2340经真实API/worker/PG发布报告 `50066371-ef1a-4210-91be-3ec833fe9381`。冻结7槽，6PASS，1次文件读取ConnectError，行为无分、PARTIAL；没有换槽或降低七个确定结论门槛。结果 `runtime/mech-task-platform-check-20261018T110044Z-dafecdfe/result.json`。
- 同脚本的下一次复评只补原槽缺件，新增4次公开GET/CAR读取，原六项不重采。该作业 `9b83f0d5-e783-4724-9eae-2e901cd6e4dc` 在报告复核阶段FAILED，脚本exit1：旧/本次注册proof未区分，以及父来源引用集合不一致。修正后，`python runtime/finish_mech_resume_check.py` 仅复用同份原件完成复核、真实PG导入、报告GET200和两个计划附件字节一致，exit0；恢复阶段新增公网请求0。正式报告 `72bbfff4-27bb-4f7b-afd1-8302bf03ee60`：7PASS、行为100，A/F缺项、无综合分。原FAILED作业和旧部分报告保留。结果 `runtime/mech-task-platform-check-20261018T111813Z-cfc50af6/result.json`，原件 `runtime/generic-evaluation-20261018T111817Z-0415f9eb/`。
- 按需补证策略固定于ADR-0012：仅新评价补同计划的None缺项，已有原件/已知FAIL不替换；每个缺失读取只尝试一次，客户端无自动重试。源bundle、完成清单、原计划和依赖摘要一并复核。
- 功能判据调查未找到两个共用、可匿名复核的就绪对象。已有语料的16个验证类身份分属10种原文，API/判据/任务绑定仍缺。只新增2次公开文档GET：ClawSearch为SPA外壳，Beacon为307且不跟随；Prism跳过，采集命令exit1（资料未齐），原件 `runtime/f-document-review-20261018T110842Z-6e736653/`。这些不是业务测试或评分。
- 本轮未改共享类型/评分公式/前端，不重跑已有核心、网络及构建验证；无模型调用、付费业务、签名或链上写入。

用户其后选择先自动挂接已有预测判据扩大完整覆盖，该路径现已由2340、2182实际成功；其余批次状态见本页开头。其它通用查询/验证判据调查后置，订阅路径不默认兼容。

### 本轮真实验证与命令

以下Python命令均使用本目录 `.venv/Scripts/python.exe`；uv实际为 `D:/web3-runtime/tools/uv-env/Scripts/uv.exe`，pnpm构建使用Node22.17.0。

- `python -m unittest discover -s tests -p test_generic_scoring.py -v`：1个必要用例PASS，exit0；含分数、缺项、多功能绑定、重复任务及旧格式兼容。`test_pinned_http.py`同样1个必要用例PASS、exit0；固定已核公网IP并保留原域名TLS/Host，拒绝私网和凭证请求头。两项均未重跑；3份旧报告离线复算分数不变。
- `uv lock --offline`、`uv sync --frozen --offline`、`python scripts/export_contracts.py`与`python scripts/export_api_contracts.py`均exit0。`pnpm run build`最终类型检查及构建exit0；首次构建发现旧报告默认字段在生成TS中可选，修正后通过，新增占位条目展示修正后只重建受影响前端。没有重跑旧测试套件。
- `python runtime/check_generic_platform.py` exit0：3次POST202，3个报告GET200，注册证据下载成功，私有附件均404。报告身份为Base45074、BSC49467、Gnosis2340；普通用户未填写profile/RPC。Brain初始化200、通知202，但工具发现TransportError；保持缺项，没有反复探测。
- MCP远端描述接入：作业 `c891dc87-f630-48d9-aa1e-33e0cc08996e` 已正式COMPLETE，报告 `5b7a2b70-4fe5-47cc-8396-dee2bf5bcdf7` 为PARTIAL。Clicks同一协议发现4个工具，10槽中9PASS、1UNKNOWN、0FAIL，p95为10,734ms，可用性80；UNKNOWN未被当失败扣分，延迟项为0。功能/交易各0样本，无综合分。详细报告见 `runtime/generic-evaluation-20261018T093902Z-e866bab9/report.html`。
- `python runtime/check_generic_descriptor.py` 的发布与错误身份拒绝已成功；辅助脚本在读取computed scores字段时exit1。未重采样，`python runtime/finish_generic_descriptor_check.py`复用原件完成伪造判分拒绝、附件404、网页与当前JS200，exit0。结果原件 `runtime/generic-descriptor-check-20261018T093900Z-0e4c7f79/result.json`；不把首次辅助脚本错误隐写成全程exit0。
- 本轮无模型调用、付费业务或链上写入。浏览器视觉验收继续BLOCKED，网页HTTP200不替代视觉验收。本机运行状态见本页开头。

## 群体覆盖分析完成

- `collect_capability_corpus.py` 已按公开登记范围实际采集，125 次新增资料 GET、无重试或 Agent 业务调用；原件全部保留。最后离线汇总退出 0，含 554 个索引身份；109 个代表身份有详情，72 个声明接口。不是 554 个可测对象，也未据 owner/域名推算提供方数。
- `build_capability_inventory.py` 复用 14 对象、149 条旧声明与 230 个输入文件，退出 0；错误的关键词分类代码已删除，旧快照不改。当前无标签事实库 `runtime/capability-inventory-20261018T081606Z-faf14f32/`，语义判断单列为带引文的配置。
- 两份 Codex 逐项语义映射已完成来源核对：106 种目录原文、81 种旧业务原文；合并 186 个身份有当前直接功能声明。目录的泛角色/未来计划不算具体动作，旧工具内部阶段不冒充独立接口；17 段补充说明留待审阅。
- 一次离线联合计数退出 0：`runtime/capability-coverage-summary-20261018T082645Z-b3787102/`。比较与选择见 [覆盖报告](reference/CAPABILITY_COVERAGE_DECISION_20261018.md)：规划建议的 D 为 92，但最大一项 48 身份共用一种原文；预测有 12 个不同实际 service/Mech，2 个已完整证明，另外 10 个历史充分性未知。预测可作为专项扩展候选；该轮先推进通用项目与自动接入，见ADR-0009；后续用户已批准优先自动挂接既有预测判据，当前结果见本页开头。
- 该轮资料调查与语义整理未新增 DeepSeek/外部模型 API 请求、评分或工程测试；既有有效验证继续复用。该轮结束时平台为33候选/3完整对象/4报告，离线资料池没有冒充网站已接入。后续通用接入统计见本页开头。

## 实际实现

- 新目录使用独立 Python 3.12.4 / uv workspace，Pydantic 2.13.5、httpx 0.28.1 已实际安装验证并锁定；没有父目录源码 import。
- `packages/core` 实现六项候选准入、四态结果与用途类型，保持纯规则。完整准入由六项结果计算，不接受调用方直接指定 READY。
- JSON Schema 与 TypeScript 由共享类型生成；新增六个本机应用契约，OpenAPI 从真实 FastAPI 路由生成，没有三处手写。
- `SafeHttpClient` 默认不发请求；静态目标、显式启用、代理配置、HTTPS 公网地址检查、大小/时间/请求上限、不跟随重定向或重试。401/402/403/429 停止该主机。
- 候选采集 CLI 与固定可信 BSC 读取 CLI 实现；发送前保存范围，响应和观测只追加。BSC CLI 已改为显式传本机 `--source-run`，不绑定本次随机目录。
- 离线聚合核对输入摘要，生成候选准入及限定范围评分的 JSON 和中文 HTML。Vue 网站通过实际 API 展示目录、检索、逐维报告与历史，接入任务自动执行并展示进度；原始证据默认折叠且附件仅允许该报告引用的已校验公共文件。
- `reference/CANDIDATES.md` 记录 5 个实查候选、既有提供方线索和新的 Custos 调研入口。Custos 只属待核实线索，不计为就绪对象或复用通过。未从旧项目导入名单、分数、数据库或证据。
- 本轮新增有来源声明提取、纯规则自动方案选择、历史增仓/披露/三步行为核验及证据派生评分；模型不给分。正式规则、范围和采样先固定，见 ADR-0003～0005。
- 已生成新增共享类型的 JSON Schema / TS。详细报告包含真实输入、披露输出、独立结果和逐样本判据；首屏用中文解释结论、样本及未覆盖能力。
- 新增 FastAPI 0.143.3、uvicorn 0.54.0、psycopg 3.3.6，独立安装、导入验证后锁定。Vue 3.5.44 / Vite 8.3.4 / TypeScript 5.9.3 / pnpm 11.25.0 独立锁文件，实际 Node 22.17.0 构建通过。
- PostgreSQL 17.11 使用本项目独立数据目录、SCRAM 随机密码及 127.0.0.1:55438。当前38候选、35份报告、7个不同对象完整评分、0活动任务；没有SQLite/内存替代。API与worker分进程，活动任务去重、数据库租约及fencing token防止过时发布。

## 首个历史增仓试点的真实结果

首批候选检查保留 **26 条 HTTP 观测**：3 次免费业务查询、11 次资料采集、12 次链上只读请求。这是首批历史数量，不是当前全部调用或成功评价数。后续新增实调用下文与运行记录，不因 HTTP 200 就给满分。

- Brain DeFi #363709：原始注册事件中的内嵌 JSON 明确列出 Operating wallet 与 record 服务，闭合注册身份到公开记录及实际执行钱包的关联；注册持有人、仓位持有人、收款方与执行者分角色核验。包装、兑换和增仓三笔完整核对，不以第一笔包装成功代替整个步骤。
- 实时仓位查询未支持固定 block，仍未评价其动态费用/区间口径。本轮改为事先限定的历史增仓披露与三步行为范围，没有把历史结果冒充实时查询已通过。
- Brain #49467：核实身份存在；所选旧 burn 交易涉及不同代币和执行者，缺迁移/归属证明，保持 UNKNOWN。
- DegenAI：免费资产查询返回数据，ERC-8183 任务线未部署。Arena：查询返回空资料，与目录不同，需独立溯源。DARKSOL：免费业务和链上证明条件未闭合。
- 新线索没有凑数：b1e55ed 的模拟盘不计真实交易，Molttail 的静态解析/演示 fallback 不计真实成功，ACK 身份不自动转给 Etch。

首个限定范围评分已完成：**服务可用性 88.89、功能声明一致性 100、交易行为可靠性 100，综合分 96.67，状态 COMPLETE**。共 24 个真实评价槽位（10 次新可用性、7 条功能披露、7 条不同运行的三步行为）；另有 13 条无动作记录单列为背景 NOT_APPLICABLE，不进入七任务分母。可用性因真实访问延迟而非满分，没有把 HTTP 成功直接记为 100。

首个增仓窄范围只有1个真实对象获得完整分，保留为特例；后续预测自动接入使当前合计增至7个，详见本页开头。至少10个与第二独立提供方同类完整复用目标仍未完成；网站和后台已本机跑通，浏览器视觉未验收。

首次可审阅的[中文详细报告](runtime/evaluation-report-20261018T053613Z-fe5237bc/report.html)：

`runtime/evaluation-report-20261018T053613Z-fe5237bc/`

同目录保留 manifest、report.json、report.html 与 background.json。新版将金额转为普通用户可读单位、列出北京时间采样窗口并解释旧失败如何补齐；复用原件重算，分数不变。首版 `runtime/evaluation-report-20261018T053426Z-ba06f389/` 保留不改。

正式 API 任务 `88a22786-55ec-462e-a7e7-d440f215587c` 于北京时间 13:58:35 接入，14:03:45 自动发布报告 `568a411d-2548-48ed-8df7-1dd7840a903f`，状态 COMPLETE：**可用性 93.09（10 PASS、p95 4,109ms）、功能 100（7 PASS）、行为 100（7 PASS），综合 97.93**。新报告为 [第二次评价](runtime/evaluation-report-20261018T060340Z-4c27cea3/report.html)，重新采集可用性，复用并独立核验已冻结历史原件；旧版保留，同一 Agent 不重复计数。worker 退出 0，没有新增模型调用或链交易。

首批准入报告 `runtime/admission-report-20261017T182038Z-f504c54e/` 及其 26 条观测继续保留。首批 functional/HTTP PASS 仅为采集标记，没有跨用作正式评分槽位，语义说明见 ADR-0002。

## 模型接入与真实证据闭环

用户最新授权：DeepSeek 使用现有余额，余额不足时告知；不设置额外费用或请求数上限，不再等待预算审批，不自动充值。旧费用记录保留但不控制本项目调用，付费 Agent 与资产操作仍未授权。

早期首批实际完成 3 次模型请求，共 39,981 tokens。第一批 DegenAI 与 Brain DeFi 原响应只追加保存；离线逐声明复核后接纳 18+20 条，拒绝 3 条占位/目录之外内容。第二次 DegenAI 响应有一条非原文引用，保留错误，不自动重发。最后离线复核使用原响应，没有新增模型费用；引用通过不代表服务能力已兑现。余额查询显示可用，读数不变不等于没有计费。

现成资料包：`runtime/model-review-20261017T182601Z-ccb0ed3d/`。包含 DegenAI 完整能力发现 JSON（34,408 字节投影）、Brain DeFi 官方功能页 HTML 文本投影（6,336 字节），各自原件/投影摘要及来源分开记录。其旧费用提议只作历史保留，新的调用忽略这些上限字段；不修改原件。

平台已离线自动选中 `liquidity-history-v1`，有来源的记录查询和 Increase 声明匹配该范围，未让用户选择方案。模型、采集命令和原件位置见 [本轮运行记录](docs/runbooks/MODEL_EVIDENCE_LOOP.md)。

历史状态已通过现有 ZAN 凭证实读。官方 BSC 节点的 missing trie node、PublicNode 的 403、ZAN 原认证路径 400 均保留；403 后停止该主机，未绕过。ZAN 密钥只进入私有传输 URL，公开计划与证据不含该段。

- 10 个新可用性槽位全部取得预期响应，耗时 1,422～6,000ms，未把背景资料调用复用为采样。
- 14 条冻结历史任务按功能 7 / 行为 7 分组。交易、回执、固定仓位状态、同块增减事件已取得；功能组额外解包不该被三步行为规则挡住，修正采集器后只补缺失项。
- 注册事实、token 精度、固定块仓位所有权、可信 factory 池来源另有 39 项上下文结果，38 次新读取、1 项复用。未触发新链交易。
- 13 条无实际增仓记录保留为范围外，不计成功或失败。最终核验从原始请求/响应重建，不相信前端或结果文件自报的分数。
- 首次完整离线报告生成退出 0；调整普通用户读法后再次复用原件生成独立新版，退出 0，仍为 88.89 / 100 / 100、综合 96.67。未为展示改动新增外网采样或重跑工程测试。

## 新提供方与不可评分记录

以下保留早期调查结果及未就绪对象。Olas 后续完成情况见本页预测闭环记录，没有复制第三方分数或降低样本门槛：

- Olas：早期 10 月 20 日问题尚未到期，未据此评分；后续选取冻结 cutoff 前 14 个不同已结算问题，完成原始概率、CID/DAG、历史 operator、接手窗口及最终结算核验。2198、2235已出完整报告；2182早期串行run有意中止且原件保留，随后通过自动接入完成综合90.56，不能将早期中止等同于当前状态。
- Custos：官方两个匿名只读入口各一次 ReadTimeout，未取得 HTTP 状态；保留 UNKNOWN，不重试凑样本，也不把网络错误扣为 Agent 失败。
- delu / Clicks：两个目录 GET 200 后，使用已有 ZAN 凭证完成 7 次可信 Base 只读注册核验，退出 0；固定块 52757623。delu 的链上 dataURI 服务列表为空，作者交易日志与身份的执行关联仍缺。Clicks tokenURI 指向的注册文件与 MCP 文档实际 GET 均 200；目录解析 services={} 不代表没有接口。
- Clicks 实际 MCP initialize/tools/list 均成功且只有四个只读工具；一次分账预览 HTTP200，但正文 `isError=true`，上游 1rpc 返回 usage limit，没有业务结果。停止后续该入口请求，不绕过限流，不把传输 PASS 当功能成功。原件 `runtime/candidate-check-20261018T062845Z-66a748a3/`，该采集 CLI 退出 0 只表示原件保存完成。其历史 bootstrap feedback 是给 Agent #1，不能归为 #45074 的真实结算履约。详情见 [扩展记录](reference/CANDIDATE_EXPANSION_20261018.md)。

Base 注册原件 `runtime/base-registration-probe-20261018T062514Z-7cb4f595/`，目录与注册文件原件见扩展记录。上述调用均为 background，不进入正式评分分母；没有新增模型调用、签名、付款或链上写入。

四个新对象已复用 31 条真实观测形成离线准入快照 `runtime/admission-report-20261018T063130Z-e7ee947b/`，六项准入均逐项说明，完整就绪 0 个，不产生声誉分。生成命令与主库导入各退出 0，目录核对为 **33 候选 / 3 完整评分对象 / 4 份报告**，旧报告未改。网站目录已能保留这些不可评分记录；这是扩展记录数，不是达到 10 个完整评分的目标。

后续可行性取得新依据：按截止日前三条交付得到三个原始概率，但它们属于同一个市场，只计一个独立事实。固定块的 CT→condition→proxy→Reality→原题干/模板/选项核验已闭合，市场最终结果为 No；这是市场的 oracle 结算，不是平台独立证明现实事件。首个 pilot 的两份真实 CAR 已逐块、目录链接和文件字节离线验证，六个必要失败控制均拒绝，退出 0，原件 `runtime/olas-car-verification-20261018T064124Z-f938e88c/`。分工消息交叠导致多读一次同一交付 CAR，原件保留，未当成新增业务样本。

预测历史按 [ADR-0008](docs/adr/0008-prediction-history-policy.md) 事先冻结政策：每对象 14 个不同已结算问题分为互斥 7+7，已看 pilot 排除；功能由原始概率与结算推导 Brier 信用分，可用性限定公开历史入口。两个对象均已逐样本核验并发布，具体结果见 [PREDICTION_REUSE](docs/runbooks/PREDICTION_REUSE.md)。

## 实际验证摘要

独立依赖安装、uv lock/sync、类型生成、默认计划、26 条真实采集与离线报告均退出 0。5 个不同工程用例均已有有效通过结果；初次 HTTP 用例遇到临时目录权限问题，仅重跑失败项，后续 HTTP/功能语义改动只跑一个必要回归。未为提交或文档重跑测试。

新增 8 个必要工程用例各已有通过结果，覆盖引用、凭证、核验、评分与自动方案选择；此前 5 个有效结果复用。ZAN 认证传输、数量序列化与完整槽位门槛发生实际变化时，仅重跑受影响用例，不跑整套。共享契约生成退出 0。命令、退出码、真实外网失败与定向补采见本轮运行记录。

首版候选报告桌面截图已实际查看；后续 Chrome/Edge 进程异常，最终桌面与手机显示验收 BLOCKED，未声称通过；新详细报告也尚未完成浏览器视觉验收。

本机平台必要验收记录见 [LOCAL_PLATFORM](docs/runbooks/LOCAL_PLATFORM.md)：

- 真实 PostgreSQL 独立验收库中执行一个关键集成用例，覆盖摘要/分数核对、中文、禁止修改/删除、3 个并发领取者仅一个取得任务、过期租约回收与旧 token 拒绝、API 正常/无资料/私有路径拒绝。首次因验收库缺限定 HBA 条目而失败；只补该库的回环 SCRAM 条目并定向重跑失败用例，`Ran 1 test`，退出 0。此前 13 个有效用例继续复用，不重跑整套。
- `uv lock`、`uv sync --frozen`、共享契约和实际 OpenAPI 生成退出 0；前端类型检查及构建通过。修复真实 API 数据暴露的示例引用/说明问题后，仅重建受影响前端一次。
- 本机网页及四个主要 API 共 5 个 GET 返回 200、提交 202；正式 worker 自动执行并发布新报告。JS/CSS 实际 200 且 MIME 正确，原件 `runtime/local-platform-check-20261018T055831Z-95665164/`。一次验收脚本用字符串比较不同时区而失败，已改为有时区 datetime 比较；复用已完成报告，无重复测量。
- `./scripts/start_local_platform.ps1 -Once` 实际退出 0，复用本项目 PG、启动并检查 API7754，处理另一真实注册标识为 NEEDS_INFO，无报告和分数，旧两份报告不变；脚本退出后自己的 API 已停。默认外网关闭，这个失败路径未发外网请求。PG 保留运行，停止脚本仅管理该项目实例。
- 静态复核发现同一内部 key 可能被不同完整身份覆盖，已在单 SQL upsert 中拒绝并由事务回滚冲突候选。只新增真实 PG 身份回归，验证旧短线索补齐、等价身份及冲突拒绝；测试样例修正后仅重跑该新用例，最终退出 0。未改已发布真实报告，也未重跑此前通过的集成验收。

## 尚未实现或未验收

- 网站/API/worker已本机跑通；未配置对象可自动注册/协议接入，已支持的MCP可用性和Mech历史履约分别出分。未知协议的实际业务及功能正确性仍不能自动评分，桌面/手机视觉验收未完成。
- 第二个独立提供方的同类复用与至少 10 个完整评分对象：未完成；新线索见 [候选调研](reference/CANDIDATE_RESEARCH_20261018.md)。
- PostgreSQL 集成与并发验收已通过；Anvil 集成 NOT_RUN。本轮为真实主网只读历史核验，不依赖 Anvil 或发起新链交易。
- 模型 API 已实际调用；付费 Agent、签名、主网写入、资产交易：NOT_RUN。
- Node 22.17.0 与 PostgreSQL 17.11 已用于实际构建/服务，Foundry 1.8.4 只用于必要 ABI 编解码；Docker 未找到，不影响本机功能闭环。
- 代理已保存用户级 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY；当前命令显式传代理。Codex 桌面重启后的实际重连验收仍为 RESTART_VERIFICATION_PENDING，不重复已通过 HTTP 检查。

## Git

独立仓库根目录与分支已核实：`D:/xjtu_project/block_chain_new/block_chain_new_new`，`codex/local-platform`。当前实现提交包括 `1791a8a`（自动接入）、`01494e8`（展示）及 `07b0d39`（租约/CID）；登记补录已提交 `3091343`；此前共用Mech履约与补证 `b4fbbbe`、契约 `4385363`、自动接入 `5e21b16` 等提交保留。本次常读文档收口未提交，具体hash以git log为准。每批暂存diff检查通过，秘密扫描0命中，不包含runtime、虚拟环境或密钥。旧预测、语料和语义映射提交继续保留，没有改写历史。

新远程 REMOTE_NOT_CONFIGURED；push、PR、部署均 NOT_RUN。未操作父仓库、旧服务、其他分支或共享历史。

既有声明提取共 15 次真实模型请求，留下 14 个对象的 149 条已核来源声明；另有 4 次问题翻译请求、28 题，原响应和 usage 保留。2198 部分声明引用拒绝未重发，4 条中文措辞采用有来源的编辑覆盖，未改变概率或评分。2182早期串行run已中止且原件保留，其后自动接入完整报告见本页开头；两个背景pilot不进入正式分母。新增纯概率、自动选方案及原件派生报告各 1 个必要用例、5 项纯链失败控制均已有 exit 0，旧测试不重跑。

预测闭环完成记录：2198可用性98.20/功能75.66/行为100，综合89.72；2235可用性98.61/功能97.81/行为100，综合98.71。各24槽，真实API202→worker→PostgreSQL发布两任务均COMPLETE、worker均exit0；两个新报告实际GET200，公共证据下载逐字节一致。当轮主库为33候选/3个不同完整评分对象/4份报告；后续通用接入的当前统计见STATUS。详见docs/runbooks/PREDICTION_REUSE.md；不能声称覆盖所有预测工具、实时推理或任意提供方。
