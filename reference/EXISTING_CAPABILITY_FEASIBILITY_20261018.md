# 既有 14 对象的预测能力与可测性事实表

日期：2026-10-18。任务为 `CAPABILITY_COVERAGE_ANALYSIS`。仅离线审阅已有材料，没有新网络、模型、历史采集、评分或工程测试；没有设计第三类评价。

## 计数口径与结论

输入为 [records.json](../runtime/capability-inventory-20261018T080106Z-2c848b9d/records.json) 和 [capability-links.json](../runtime/capability-inventory-20261018T080106Z-2c848b9d/capability-links.json)。前者 SHA256 为 `82f91eef15c113aaaa4ac3fb315f69cfb8b55fa153ab949dabd028adbda27b62`；后者为 `3dfaf9eb9de9a348fe9088e99c33f901648c942c73d7400b7a7b7ad5fc525bf3`。清单含 14 个不同 canonical 引用、149 条已保留声明和 149 条映射记录。映射中的 `capability_proposals` 是草案，本表不将其作为语义分类或可测结论。

- **12 个对象有真实原文支持的二元概率预测业务声明。** 另外两个在本批资料中没有这种声明：DegenAI 的预测市场资料查询、Brain 的增仓/仓位规划不能因此算作概率预测。
- **6 个预测对象满足当前采集器的注册文档结构前置条件。** 这只是静态结构可通过，不表示它们的全部历史调用/支付路径已适配，更不等于历史充分。
- **2 个预测对象已被完整历史与已发布三维报告证明可评：2198、2235。** 它们各有 14 个不同有效已结算市场、互斥 7 功能/7 行为任务及 10 个全新可用性槽位。
- **其余 10 个预测对象的历史充分性统一为 UNKNOWN。** 已有材料不能证明其中任何一个各自具有至少 14 个不同、有效已结算、原始工具与声明匹配的问题。UNKNOWN 不是“已证明没有历史”。2182 的背景 pilot 和中止批次也不能算正式 14 槽计划。

本表使用同一对象条件合取：业务声明、输入输出、身份/协议适配、读取许可、独立判据和任务历史不能从不同对象拼接。“声明 12／当前注册模板 6／完整已证 2”是不同层次，不能相互替代。

## 输入输出说明不等于强约束概率 Schema

表中 12 个预测对象均有 `ipfs-v0.1` 声明；所选最小证据工具的输入为 text，外层输出 Schema 要求 `requestId`、`result`、`prompt`，其中 `result` 是字符串，其示例含 `p_yes/p_no/confidence/info_utility`。

这足以证明提供方**声明了概率输出形态**。但所选 12 条证据均未将内层概率定义为必填 numeric 属性，也未在该 Schema 中约束有限值、[0,1] 或两项和为 1。因此不得写成“12 个对象已有强约束概率 Schema”。正式报告仍须解析真实交付、核对工具/原题/时间，并以核心规则检查数值及独立结算。下表 `T/R` 专指上述 text 输入与 result 字符串概率示例。

## 逐对象事实

共同注册合约 `R = 0x8004a169fb4a3325136eb29fa0ceb6d2e539a432`；表中 `chain:agentId` 的完整 canonical 为 `eip155:{chain}:R:{agentId}`。服务号另列，不能默认等于 ERC-8004 编号。S01～S14 的原件和模型投影见文末。

| canonical 简写／对象 | Olas service | 业务原文与输入输出证据 | 当前方案前置条件 | 历史资格与本轮结论 |
| --- | --- | --- | --- | --- |
| `1:23121` DegenAI | 不适用 | S01 的 `prediction_markets_browse/detail/positions` 查询现有市场、隐含概率、仓位和订单；没有在本批声明中提出自身概率估计 | 不属于 Gnosis/Olas/Omen 预测历史模板；注册仍为目录线索 | 不能用市场数据返回或交易历史笔数计入预测覆盖；本对象其他能力另论 |
| `56:363709` Brain DeFi | 不适用 | S02 的 Increase、实时仓位查询、收费计划等；未见二元事件概率预测声明 | 已有的是 BSC 增仓特例，不属于本预测模板 | LP 已有 COMPLETE 不转给预测能力；不新增预测对象数 |
| `100:2182` | 2182 | S03 `/toolMetadata/superforcaster` 明确二元市场预测；T/R | 已有桥/服务 getter 绑定，注册 JSON 有符合现代码的 operator URL | 有可信背景 pilot；正式批次 INTERRUPTED、268 条观测保留，无 14 槽计划/bundle/分数；充分性 UNKNOWN |
| `100:2198` | 2198 | S04 同一工具明确二元市场预测；T/R | 当前模板已实际运行 | 14 市场及完整报告已证；三维 98.20/75.66/100，综合 89.72；仅限已评工具/任务 |
| `100:2235` | 2235 | S05 同一工具明确二元市场预测；T/R | 当前模板已实际运行 | 14 市场及完整报告已证；三维 98.61/97.81/100，综合 98.71；仅限已评工具/任务 |
| `100:2340` | 2340 | S06 同一工具明确二元市场预测；T/R | 固定块桥、serviceId/registry/operator 已核；注册 operator 字段符合当前模板 | 只有身份、声明与 profile；没有本对象正式历史 cohort，14 市场充分性 UNKNOWN |
| `100:2359` | 2359 | S07 同一工具明确二元市场预测；T/R | 同上；它曾作为其他任务的优先 Mech，不等于那些任务由它实际交付 | 不能把 2182 的接手成功移给它；本对象 14 市场充分性 UNKNOWN |
| `100:2360` | 2360 | S08 同一工具明确二元市场预测；T/R | 固定块绑定已核，注册 operator 字段符合当前模板 | profile 不等于采集结果；本对象 14 市场充分性 UNKNOWN |
| `100:4110` | **3786** | S09 `prediction_estimate` 明确估计未来事件概率；T/R；另有独立的市场裁决声明 | 桥/getter 的同服务关联已核；注册 JSON 没有当前代码要求的 operator 服务 | 当前采集器身份条件会拒绝；支付/调用及 14 市场原件未证，不是只缺一个展示字段 |
| `100:2469` | 2469 | S10 `prediction-offline/online` 明确二元市场预测；T/R；通用 TEE relay 和收盘裁决另算 | 同服务关联已核但无 operator 服务；此外目录 factory 是 NvmSubscription Native 对应实现 | 订阅支付/任务事件路径是否适用现核验尚未证；14 市场充分性 UNKNOWN |
| `100:4134` | **3809** | S11 `prediction-online` 明确 live web search＋LLM 的二元市场预测；T/R；`default/openai-*` 通用补全另算 | 桥/getter 同服务关联已核，但无 operator 服务 | 当前条件拒绝；本对象实际调用、历史控制、独立结算及 14 市场充分性 UNKNOWN |
| `100:2135` | 2135 | S12 `superforcaster` 明确二元市场预测；T/R；普通 OpenAI 请求转发不因此成为预测 | 同服务关联已核，但无 operator 服务 | 当前条件拒绝；其他声明或目录交付数不能证明 14 市场，UNKNOWN |
| `100:2267` | 2267 | S13 `prediction-offline/online` 明确二元市场预测；T/R；市场裁决另算 | 同服务关联已核，但无 operator 服务 | 与 2469 共享声明原件内容不等于共享任务历史或同一支付实现；充分性 UNKNOWN |
| `100:2150` | 2150 | S14 `superforcaster` 明确二元市场预测；T/R；普通模型调用另算 | 同服务关联已核，但无 operator 服务 | 与 2135 共享声明模板不提供本对象的任务原件；14 市场充分性 UNKNOWN |

“同服务关联已核”仅复用已保留固定块资料，不能前推任务发生时的控制关系。未完成对象还需各自的任务时间、原始 Request/Deliver、CID/DAG、实际交付者与历史 operator、支付/接手条件、原题到 Omen 问题/条件及最终结算绑定。没有以 analytics accuracy 或目录总交付量代替这些证据。

## 必须排除的语义混合

1. **查询市场资料不是自行预测。** DegenAI 的 browse/detail 返回市场已有的隐含概率与规则；positions 返回持仓/订单。这些原文支持的是资料查询，没有证明 Agent 新估计未来事件概率。
2. **已关闭市场裁决不是事前预测。** 4110 的 `resolve-market-jury-v1`/`resolve_market_jury` 描述要输出 `is_valid/is_determinable/has_occurred/vote`，而通用输出模板仍带 p_yes 示例，存在资料内部不一致；不能把这个示例升级成未来预测声明。2469/2267 的 `resolve-market-reasoning-gpt-4.1` 明确用于市场关闭后，也不算该预测工具的覆盖。
3. **通用模型或编码能力不由概率模板决定。** 2469/2267 的 `openai-*` 描述为 TEE 中的 prompt relay；4134 的 `openai-*`/`default` 为 general completion；2135/2150 的普通 OpenAI 请求声明仅说转发模型请求。即使共用预测输出标题或示例，也不单独算概率预测；没有明确编码业务声明时也不猜成编码能力。
4. **事实研究要看完整业务链。** S03～S08 的 `factual_research` 不止“核查事实”，原文明确事实取证后输出二元市场概率，可纳入该声明的预测能力；它不是因为名称或 p_yes 字段被归类。S09 的 `resolution_evidence_pack` 虽名称近似裁决，其 metadata 描述实际为 binary forecaster，需按此原文理解，不能按 key 自动分类。

## 现有适配缺口与许可

`services/platform/src/reputation_platform/prediction_evidence.py:333` 精确要求注册文档包含 `https://{mech无0x}-100.mech.valory.xyz` 的 operator 服务。2340/2359/2360 等有此字段；4110、2469、4134、2135、2267、2150 的已保留注册 JSON 均没有它。因此后六者是**当前实现的前置条件不支持**，不是链上身份不存在或 Agent 业务失败。

这六个也不能统称为“删一条域名检查即可评价”。[既有目录原件](../runtime/olas-discovery-20261018T063948Z-f38a1edd/olas-mech-directory.response.bin)记录：2469 的 factory 为 `0x65fd74c29463afe08c879a3020323dd7df02da57`，其余本表 11 个预测实例为 `0x8b299c20f87e3fcbff0e1b86dc0acc06ab6993ef`。既有[官方映射调查](OLAS_DISCOVERY_20261018.md)将前者标为 NvmSubscription Native、后者为 Fixed Price Native。本次没有其任务级支付/Request/Deliver原件，故不能假设订阅支付和已验 FixedPrice 路径相同，也不能无依据断言全部事件签名不同。**事件、费用约束及历史调用的实际兼容性仍 UNKNOWN。** 其余实例 factory 相同也不能替代任务核验。

后续通用履约路径已复用可信RPC下的Mech.serviceId/serviceRegistry/getOperator、官方桥映射、注册URI原件及历史任务，替代提供方域名条件；两个旧对象和未配置#2340已有验证，见ADR-0011/0012与STATUS。此实现尚未迁入旧预测专项，不改变本表其余对象的14市场充分性UNKNOWN；不能按名字写例外、把agentWallet当执行者或接受metadata任意RPC。

本批 12 个预测对象的声明访问字段均为 unknown。已有用户授权的公开只读取证和成功历史文件访问，不等于可以创建收费预测、签名、购买订阅或付款。2198/2235 的已发布结果只证明那些历史文件可读取；其他对象的具体任务 CID、可访问性与完整 CAR 仍待事实核实，本轮不查询。

## 去重与未知边界

按完整 canonical、实际 Mech、链上 service 三层检查，本批预测子集均为 **12 个不同 canonical／12 个不同 service／12 个不同 Mech**，未发现以同 Mech 或同 service 多注册重复计数。实际 ERC #4110 对应 service3786、#4134 对应 service3809；二者不再把服务号作为另一个 Agent 计数。

2469 与 2267、2135 与 2150 分别共享 manifest 内容摘要，但注册、Mech 和服务不同。共享模板不自动合并身份，也不增加独立业务类别或独立提供方数。清单中六个 Valory 实例的 provider 状态是资料自述 DECLARED；另外六个预测实例为 UNKNOWN。不能由模型名、域名缺失、不同钱包或 factory 推定提供方数量，跨提供方覆盖尚不能量化。

两个完成报告分别为 [2198](../runtime/evaluation-report-20261018T074802Z-2378ca3d/report.json)、[2235](../runtime/evaluation-report-20261018T074803Z-c4f9fbe0/report.json)。2182 的[中止记录](../runtime/prediction-history-20261018T070812Z-bb2164f7/interrupted.json)明确无正式 plan/bundle，不计完成。未完成十个对象：2182、2340、2359、2360、4110、2469、4134、2135、2267、2150，均没有在本次审阅中获得“各有至少 14 个不同有效已结算且工具匹配问题”的证明。

以上是限定材料内的声明与可测性判断，不宣称穷尽 Agent 的全部功能。元数据只复用已保留 HTTP 原件、摘要和既有身份关联，本轮没有新验证其 IPFS DAG 或业务真实性。

## 来源索引

每行 S 编号与上表对应；JSON 工具证据定位在 `toolMetadata`，DegenAI 在 `capabilities`，Brain 在保留 HTML/投影。完整摘要、观测和引用 JSON Pointer 可回查输入 records.json。以下原件与投影均来自新工作区。

| 来源 | 完整 canonical | 业务原件／投影 | 原件 SHA256 前12位 |
| --- | --- | --- | --- |
| S01 | `eip155:1:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:23121` | [原件](../runtime/candidate-check-20261017T175652Z-f876ebbc/degen-discovery.response.bin)／[投影](../runtime/model-review-20261017T182601Z-ccb0ed3d/degenai.source.txt) | `42bdb6b7ef47` |
| S02 | `eip155:56:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:363709` | [原件](../runtime/candidate-check-20261017T180114Z-bc374bd3/brain-defi.response.bin)／[投影](../runtime/model-review-20261017T182601Z-ccb0ed3d/brain-defi.source.txt) | `8fa8fc0990f0` |
| S03 | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2182` | [原件](../runtime/candidate-check-20261018T055429Z-100ff385/olas-manifest-2182.response.bin)／[投影](../runtime/model-review-20261018T065247Z-d2d75c1a/olas-valory-predict-2182.projection.json) | `45345aa9a117` |
| S04 | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2198` | [原件](../runtime/olas-discovery-identities-20261018T065216Z-3ff423d4/service-2198-manifest.response.bin)／[投影](../runtime/model-review-20261018T065549Z-7efbdf07/olas-valory-predict-2198.projection.json) | `4c220260d1e3` |
| S05 | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2235` | [原件](../runtime/olas-discovery-identities-20261018T065216Z-3ff423d4/service-2235-manifest.response.bin)／[投影](../runtime/model-review-20261018T065549Z-7efbdf07/olas-valory-predict-2235.projection.json) | `81204437f471` |
| S06 | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2340` | [原件](../runtime/olas-discovery-identities-20261018T065216Z-3ff423d4/service-2340-manifest.response.bin)／[投影](../runtime/model-review-20261018T065549Z-7efbdf07/olas-valory-predict-2340.projection.json) | `a0f01903a1eb` |
| S07 | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2359` | [原件](../runtime/olas-discovery-identities-20261018T065216Z-3ff423d4/service-2359-manifest.response.bin)／[投影](../runtime/model-review-20261018T065549Z-7efbdf07/olas-valory-predict-2359.projection.json) | `9a945b056e8b` |
| S08 | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2360` | [原件](../runtime/olas-discovery-identities-20261018T065216Z-3ff423d4/service-2360-manifest.response.bin)／[投影](../runtime/model-review-20261018T065549Z-7efbdf07/olas-valory-predict-2360.projection.json) | `4973e90a5b6d` |
| S09 | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:4110` | [原件](../runtime/olas-discovery-identities-20261018T065216Z-3ff423d4/service-3786-manifest.response.bin)／[投影](../runtime/model-review-20261018T070719Z-920e0463/olas-gnosis-4110.projection.json) | `91a23bd869cf` |
| S10 | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2469` | [原件](../runtime/olas-discovery-identities-20261018T070037Z-aecda7f0/service-2469-manifest.response.bin)／[投影](../runtime/model-review-20261018T070719Z-920e0463/olas-gnosis-2469.projection.json) | `9311bb7d0397` |
| S11 | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:4134` | [原件](../runtime/olas-discovery-identities-20261018T070037Z-aecda7f0/service-3809-manifest.response.bin)／[投影](../runtime/model-review-20261018T070719Z-920e0463/olas-gnosis-4134.projection.json) | `4f8795fcdbf0` |
| S12 | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2135` | [原件](../runtime/olas-discovery-identities-20261018T070037Z-aecda7f0/service-2135-manifest.response.bin)／[投影](../runtime/model-review-20261018T070719Z-920e0463/olas-gnosis-2135.projection.json) | `3c5e841f4d40` |
| S13 | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2267` | [原件](../runtime/olas-discovery-identities-20261018T070037Z-aecda7f0/service-2267-manifest.response.bin)／[投影](../runtime/model-review-20261018T070719Z-920e0463/olas-gnosis-2267.projection.json) | `9311bb7d0397` |
| S14 | `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2150` | [原件](../runtime/olas-discovery-identities-20261018T070037Z-aecda7f0/service-2150-manifest.response.bin)／[投影](../runtime/model-review-20261018T070719Z-920e0463/olas-gnosis-2150.projection.json) | `3c5e841f4d40` |

登记与同服务关联另见 [2182固定块读取](../runtime/olas-history-probe-20261018T060841Z-ff48df5e/manifest.json)、[2182桥绑定](../runtime/olas-binding-probe-20261018T061400Z-0673d417/manifest.json)、[first5及3786身份](../runtime/olas-discovery-identities-20261018T064733Z-c4d2f161/result.json)、[后续Gnosis身份](../runtime/olas-discovery-identities-20261018T070037Z-aecda7f0/result.json)。这些目录保留对应 method/params、观测和响应；汇总 result 不能代替原件。
