# 真实登记功能声明语料（2026-10-18）

本轮任务是 `CAPABILITY_COVERAGE_ANALYSIS` 的公开登记资料采集线。只整理登记描述及已发布的服务声明，帮助后续按能力、提供方线索和证据可得性分析覆盖。未启动第三类评价、Agent业务、RPC、模型分析、付费、签名或写入。

## 官方资料与字段

- [8004scan Builder Hub](https://8004scan.io/developers) 指定正式 API 为 `https://api.8004scan.io/api/v1`，公开文档列出匿名只读访问及限流。
- [官方 OpenAPI](https://api.8004scan.io/openapi.json) 实际保存为 `runtime/capability-corpus-20261018T075346Z-23784a77/`，一次 GET HTTP 200，CLI exit 0，版本 `0.4.378`。`api-surface.json` 从同一原件提取目录操作与依赖 Schema。
- 目录返回 `items/total/limit/offset/next_cursor/has_more`。每行包含 `chain_id/contract_address/token_id/agent_id/name/description/owner_address/supported_protocols`；完整 `raw_metadata` 和服务接口不在列表中，必要时才读取固定单对象详情。
- 目录本身包含第三方评分字段；原始响应完整保留，采样和标准化不读取这些分数、排名或健康数据，不据此选样或生成声誉分。

## 首资料页与采样

首个小页为 Base 主网早期 10 个声明有 MCP 的登记，原件 `runtime/capability-corpus-20261018T075452Z-568ec525/`，一次 GET HTTP 200，exit 0。前数行集中于同一 owner 的 OLAS 默认配置、`Test`、`Simple tools`，不能当具体业务；另有明确代码/项目管理、社交参与奖励等功能描述。小页仅用于字段和质量确认。

正式群体采样取消协议过滤：按 9 条 EVM 主网和 2 个登记时间层，每层最多 30 条，最多 540 个目录行。链为 Ethereum、Base、BNB、Gnosis、Celo、Polygon、Arbitrum、Avalanche、Optimism；时间层为最早登记，以及 `2026-04-01T00:00:00Z` 起最早登记。保留 inactive 登记，不按分数、排名、健康、类别或协议筛选。

配置 `configs/corpus-directory-strata-20261018.json` 固定每个请求的分页、排序、时间和链字段；发送前 manifest 保存实际 URL 与配置/脚本 SHA。采集运行 `runtime/capability-corpus-20261018T075809Z-6b7e83bf/` 的 18 个 GET 均 HTTP 200，exit 0，实际保存 540 条新目录行。合并原小页与已有单对象目录原件后为 554 个不同完整身份、9 条链、203 个 owner 线索，不是 203 个已核实提供方。

平台 Codex 编辑逐种原文初筛：272 个登记身份有具体业务描述，对应 106 种原文；183 个仅名称、角色设定、测试、默认或废弃说明；31 个描述含糊；另有 68 个空描述。以上只确认登记文字具体与否，不认证业务存在、可测或兑现。评审以原文字节 SHA 固定在 `configs/corpus-detail-declarations-20261018.json`。

必要详情采样覆盖每种具体原文，每种完全重复文字最多保留两个不同 owner 线索；同一 owner 的不同功能照常保留。其余重复身份仍在语料中，缺详情不改判无功能。109 个详情目标复用 4 份旧详情，实际运行 `runtime/capability-corpus-20261018T080336Z-d7060ad6/` 新发 105 个 GET，均 HTTP 200，exit 0。既有 14 个对象的 149 条已核来源声明由另一工作线按 canonical 身份合并，不重复模型提取。目录默认文字若由旧 manifest 补充了具体工具，应记录为“补充具体功能”，不能据目录文字认定没有能力。

这是一份分层的资料可得性语料，不代表对整个生态的随机统计。重复模板和相同 owner 用于发现集中度，不能把不同 owner 数冒充独立提供方数，也不能把同一服务的跨链登记当成不同产品。

## 安全与证据

`scripts/collect_capability_corpus.py` 默认仅展示计划；执行必须传 `--execute-public-readonly --proxy http://127.0.0.1:7897`。目标仅为固定官方 OpenAPI、登记列表与登记详情 GET，不接受任意 Agent URL，不跟随重定向，不重试或切换入口。匿名请求至少间隔 2.2 秒，401/402/403/429 记录后停止该 host，后续本脚本阶段共享停止标记。

所有网络经现有 `SafeHttpClient`；原始 `.response.bin`、`.observation.json`、响应 SHA 只追加。复用旧原件前核对 SHA；标准化引文附原始 URL、JSON Pointer、原文、原件 SHA、原件/观测相对路径。完整身份采用 `eip155:chainId:registry:agentId`，不能把服务号当注册 ID。

标准化对象每个完整身份一条，包含 `candidate_key/registration_reference/identity_status/provider/source_documents/claims/declarations/quality/feasibility/source_runs`。新对象 `claims=[]`，只保留尚未模型拆分的原文 `declarations`。具体功能须语义复核，长度或单个动词不自动证明其可测。名字、标签、空描述和明确默认模板不计有效声明。

提供方只在 metadata 有明确 `operator.name` 时标为 `DECLARED`，不冒充独立认证；其余为 `UNKNOWN`，owner、认证昵称、共享网关仅作线索。登记身份也仅为 `INDEXED_NOT_CHAIN_VERIFIED`。接口声明、授权、独立判据、历史任务与执行归属未实查的部分明确未知，不能把资料 GET 成功视为业务兑现。

## 最终资料质量与交付

最终只追加的离线收口目录为 **`runtime/capability-corpus-20261018T080919Z-8c5ab9e4/`**，生成 exit 0、0 新 HTTP、0 模型。`corpus.json` 保留 554 个完整索引身份及缺项；`corpus-manifest.json` 绑定原始观测/响应、请求 manifest 和输出 SHA。原始 105 个详情请求目录和更早目录页保持原样。

- 共 554 个不同完整身份、9 条链，目录原文初筛 272 个具体、251 个资料不足（含 68 个空描述）、31 个含糊。272 个具体身份只有 106 种原文描述，不能把重复产品/跨链版本当成不同独立服务。
- 109 个代表身份已取详情，其中 72 个至少列出接口声明。标准化资料共保存 4 份 `skills`、1 份 `tools`、4 份 `capabilities` 字段；部分仅为标签或布尔开关，不能因此计作完整功能规范。真实输入输出 Schema、免费授权、独立判据和可归属历史在多数对象仍缺。
- 当前语料未发现明确 `operator/provider` 署名字段，提供方均为 `UNKNOWN`。不同项目名、owner、服务域名是后续核实线索，**本轮没有证明 100 个独立提供方**，也没有证明 100 个可评分对象。
- `quality.coverage_status` 区分 `DIRECTORY_SPECIFIC/UNKNOWN`；原有库存中的具体工具可在合并阶段补充为第三种“补充具体功能”。编辑初筛仅用于本轮是否需要 GET 详情，不作为模型类别先验或评分输入。
- 目录现成 score/rating/rank/health/trust/analytics 未进入声明投影；功能本身宣称返回风险评分、行为指标等属于业务输出声明，不能与第三方已有声誉分混淆。所有来源文本中的命令或角色指令只作为资料保存。

本线实际新 HTTP **125 次**：官方 OpenAPI 1、小页 1、分层目录页 18、必要登记详情 105。均只读取公开登记资料；没有重取已缓存 Agent 业务、调用 RPC/模型或发起新任务，没有重试、换入口或更改原件。登记详情中的 `raw_metadata.offchain_content` 是索引器缓存的已发布材料，本轮没有据此声称已直接认证原 Agent URI、域名所有权或链上登记。

## 当前命令

```powershell
.venv/Scripts/python.exe -X utf8 scripts/collect_capability_corpus.py --config configs/corpus-directory-strata-20261018.json --reuse-runs runtime/capability-corpus-20261018T075452Z-568ec525 runtime/candidate-check-20261017T175652Z-f876ebbc runtime/candidate-check-20261017T180531Z-40968620 --execute-public-readonly --proxy http://127.0.0.1:7897

.venv/Scripts/python.exe -X utf8 scripts/collect_capability_corpus.py --config configs/corpus-detail-declarations-20261018.json --reuse-runs runtime/capability-corpus-20261018T075809Z-6b7e83bf runtime/capability-corpus-20261018T075452Z-568ec525 runtime/candidate-check-20261017T175652Z-f876ebbc runtime/candidate-check-20261017T180531Z-40968620 --execute-public-readonly --proxy http://127.0.0.1:7897

.venv/Scripts/python.exe -X utf8 scripts/collect_capability_corpus.py --config configs/corpus-detail-declarations-20261018.json --offline-build --reuse-runs runtime/capability-corpus-20261018T075809Z-6b7e83bf runtime/capability-corpus-20261018T075452Z-568ec525 runtime/candidate-check-20261017T175652Z-f876ebbc runtime/candidate-check-20261017T180531Z-40968620 runtime/capability-corpus-20261018T080336Z-d7060ad6
```

以上为本机审计记录，不要求每次重跑这些资料页。工程测试 NOT_RUN；实际首资料页是本轮必要验证，已有结果和旧模型声明由其他工作线复用。
