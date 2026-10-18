# Olas Gnosis Mech 候选发现

日期：2026-10-18。一次匿名只读目录查询取得 **40 个不同 Mech 合约、40 个不同 Olas service_id**。随后三批核查 24 个新实例，**22 个身份关联通过、2 个运营者查询 UNKNOWN**，共取得 17 份实际 manifest，其中一份只有工具名、仍缺具体声明。没有新增完整评分，不能把不同运营地址直接解释为不同组织。

## 官方源码对照

- [mech-client 的 client.py](https://github.com/valory-xyz/mech-client/blob/main/mech_client/infrastructure/subgraph/client.py)：`query_mechs` 使用实体 `meches`，默认按 `totalDeliveriesTransactions` 降序；字段为 Mech 身份、factory、交付交易计数及 service 的 ID、交付计数和 metadata。GitHub blob SHA：`5658cc5055e7e24a27fba6cb9e0952c967186c42`。
- [queries.py](https://github.com/valory-xyz/mech-client/blob/main/mech_client/infrastructure/subgraph/queries.py)：列表过滤交付交易数大于 0，最终展示 20 条；同时提供 factory 类型映射。`query_erc8004_agent_id` 明确区分 Olas service_id 与 ERC-8004 agent_id。GitHub blob SHA：`07373e1f81d2347b61f8ef343a5ca83bf7ce0a2e`。
- [官方 mechs.json](https://github.com/valory-xyz/mech-client/blob/main/mech_client/configs/mechs.json)：Gnosis 使用 `graph` 方言，marketplace 地址正是 `https://api.subgraph.autonolas.tech/api/proxy/marketplace-gnosis`。GitHub blob SHA：`b08a07da0122f0100010c987f1b7c7aeda82c6e7`。以上记录的是文件 blob，不冒称上游 commit。

官方原始目录查询未显式设置服务端 `first`。本次保留相同实体、字段和排序，加上 `first: 40`，用唯一一次有界查询寻找至少 9 个不同 service，避免靠重试或分页扩大请求。没有取 karma、提供方评分或第三方 reputation 分。

## 实际执行与原件

默认计划命令已执行，退出 **0**，`execution_enabled=false`，不联网：

```powershell
.venv/Scripts/python.exe scripts/discover_olas_candidates.py
```

随后通过已授权的执行环境网络权限，仅执行一次真实目录读取，退出 **0**：

```powershell
.venv/Scripts/python.exe scripts/discover_olas_candidates.py --execute-public-readonly --proxy http://127.0.0.1:7897
```

证据目录：`runtime/olas-discovery-20261018T063948Z-f38a1edd`。发送前已写入 manifest，记录固定目标、完整 GraphQL、请求上限 1、脚本摘要及源码对照。实际 HTTP 200，响应完整，10,747 字节，观测耗时 1500 毫秒；没有重试、重定向或换端点。

| 原件 | 内容 |
| --- | --- |
| `manifest.json` | 发送前范围与查询 |
| `olas-mech-directory.observation.json` | 真实请求观测 |
| `olas-mech-directory.response.bin` | 原始 GraphQL 响应 |
| `result.json` | 按 service_id 合并后的目录线索与缺项 |

响应 SHA-256：`9e1c439bbeb21442aa8202dbcc1ff987568b02b3de3846be60aee7ffb2228b07`。解析得到 raw_rows 40、distinct_mech_contracts 40、distinct_services 40、services_with_indexed_deliveries 40、data_gaps 0。HTTP 成功与交付计数均只属于发现证据，不代表业务正确、服务当前可用或完整任务已可靠完成。

所有网络仅经过 `SafeHttpClient`，脚本默认关闭，目标和 GraphQL 固定，没有任意 URL 参数。没有安装或执行官方远程代码，没有请求新预测任务、IPFS、RPC、模型、签名、支付或资产操作，也未运行工程测试。

## 首批选取的 9 个不同实例

2182 正在另一条核验线上处理，以下保留发现阶段选取的另外 9 个 service。首批优先保留索引中存在 metadata 的对象，尽量减少完全相同资料的重复；这是资料可测性的推进顺序，不是声誉排名，也没有按预期评分筛选。下表资料状态是目录阶段快照，后续身份结论见后文；各自完整 metadata hash 保留在原目录 `result.json`。

| Olas service_id | 本次索引 Mech 地址 | Mech 交付交易计数 | 本轮资料状态 |
| --- | --- | ---: | --- |
| 2198 | `0x601024e27f1c67b28209e24272ced8a31fc8151f` | 861815 | 有 metadata，身份桥与任务核验待完成 |
| 3098 | `0x33ca1e117c4254b2ee8cd7ef1621739431a37396` | 390899 | 有 metadata；与 3118 的 hash 相同，运营/版本关系待核实 |
| 2235 | `0xb3c6319962484602b00d5587e965946890b82101` | 125039 | 有 metadata，身份桥与任务核验待完成 |
| 2340 | `0xdb78159e9246ec738f51c2c9cb1169b5c0e45fee` | 64782 | 有 metadata，身份桥与任务核验待完成 |
| 2359 | `0x818df8dcd43d716a7263798c99a2fc8e27010711` | 59885 | 有 metadata，身份桥与任务核验待完成 |
| 2360 | `0x11c4389bf449991d69f89f941c3e79d5d828f1bc` | 25279 | 有 metadata，身份桥与任务核验待完成 |
| 3783 | `0x2d64fee808fba217aee1210e3574432c31edcdab` | 1843 | 有 metadata，身份桥与任务核验待完成 |
| 3786 | `0xe444eeaa1ffd2113b273d99e21ea82d0f03bc0e0` | 1452 | 有 metadata，身份桥与任务核验待完成 |
| 3066 | `0x154e5f443d4f1e0745f91283fc3ce69afede3311` | 1260 | 有 metadata，身份桥与任务核验待完成 |

这些地址的 factory 字段均为 `0x8b299c20f87e3fcbff0e1b86dc0acc06ab6993ef`，官方客户端将其映射为 Fixed Price Native。目录阶段只核对索引记录和官方映射，后续身份阶段另读链上 getter；没有将 factory 名字当作业务成功或支付授权。

其余已取回对象全部保留在原件和分组结果中。例如 3264、3254 有索引交付记录但 metadata 列表为空，作为待补资料目标保留。2469、2010 的 factory 对应 NvmSubscription Native；历史读取线索仍可保留，不因此获得订阅、签名或付费请求授权。

## 去重、版本与尚缺的证据

分组键为 `(Gnosis chain 100, Olas service_id)`。同一 service 下出现多个 Mech 地址时会合并，不各算一个独立 Agent。本次 first 40 内恰好每个 service 只有一个 Mech，但它不是全量历史查询，不能断言每个 service 都没有旧合约、升级或其他支付版本。

3098 与 3118 的 metadata hash 都是 `0x5dd1607ad2e4a1e68014bbd52e0451899e3f2faf6427cfc8cfbeddec492be228`。这提示可能复用同一份服务资料；本轮既不将不同 service 擅自合并，也不声称已证明不同运营者或独立业务实现。后续须核对服务登记、运营钱包与具体任务关联。

两个交付字段也不能互换或相减当作失败率。例如 2182 的 Mech 计数为 912445、service 计数为 912351；3826 的 Mech 为 185、service 为 0。定义和索引范围尚未逐项核对，原值完整保留。官方源码还说明部分计数混合链上请求与链下请求的链上结算，未交付的链下请求不一定可见，因此这些计数不能充当本项目的可用性或可靠性分母。

上表记录目录发现阶段的原始线索；其当时的 `NOT_CHECKED` 原件保留。后续身份阶段已直接读取官方 Bridger 的实际映射，没有请求另一服务注册索引。实际 service_id 与 agentId 的区别见下表。

正式三维评价还需验证具体业务声明、真实历史请求/结果、链上请求与交付的归属/时间/语义对照，以及预先固定且互不复用的采样集合。目录与身份准入不计入完整评分对象数量。

## 首批身份准入与原件

脚本 `scripts/probe_olas_discovery_identities.py` 使用独立公开配置 `configs/olas-discovery-identities.json`，保持同一可信 Gnosis RPC、IdentityRegistry、ServiceRegistry 和 Bridger。复用已有 2182 原件验证链号及区块 **48,815,687**，区块哈希 `0x7311c246d521d721727a156d9f5b96102828f6ebf270c028de3defb73ad4ebe5`；没有重发旧链号、header 或 2182 成功请求。

依次读取 Bridger `mapServiceIdAgentIds(serviceId)`、实际 agentId 的 `ownerOf/tokenURI`、候选 Mech 的 `serviceId/serviceRegistry/getOperator`，再 GET 实际 tokenURI。每一阶段发送前分别写入精确 URL、JSON 请求和输入摘要。登记文件必须列出实际 agentId、完整注册合约和匹配的 Olas 服务网页；Mech→service→ERC-8004 的关联由上述链上读数独立闭合，不能拿登记文件里的 `agentWallet` 代替执行身份。

所有登记持有人均为 Bridger `0x6e8f740f23f07ce129daa59786926feca8c2d2f3`。这与下列 `getOperator` 地址是不同角色；固定快照的运营地址还不能自动用作所有历史任务的执行者。

| service_id | 实际 ERC-8004 agentId | 固定快照运营地址 | 身份结果 |
| --- | ---: | --- | --- |
| 2198 | 2198 | `0xbce2a5a3f60cf752e5b509dbad604a114c7e64a9` | PASS |
| 3098 | 3394 | 未取得；getter 回退 | UNKNOWN |
| 2235 | 2235 | `0x65a59c9ea02076edf470bcff7eacec1ba4e592bd` | PASS |
| 2340 | 2340 | `0x2e049fa653aaa4e1b599eb129ae05cc381171642` | PASS |
| 2359 | 2359 | `0x8b4698d74c3166dc6e6ec9fe4015cbe8031d70e8` | PASS |
| 2360 | 2360 | `0x36acadad5a3638b4dfd405d351855aabbe9dbf45` | PASS |
| 3783 | 4107 | `0xae27589d8175250c81907e01b0d956b69c4854b1` | PASS |
| 3786 | 4110 | `0x5679002d468614c785cde0d107c1107aba3dd7b8` | PASS |
| 3066 | 3354 | `0xe8bd5af41118608fee83cec0568bf2601ee2103e` | PASS |

完整注册前缀为 `eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:`，最后拼接本表实际 agentId。3098 的 `getOperator` 返回 RPC code 3 / execution reverted，其他登记 getter 已保留；没有重复调用、跳过错误假称通过或扣业务分。它的历史运营身份尚可另行核实。

本机已执行命令如下；随机目录只用于审计，不是以后默认应重跑的固定输入。

```powershell
# 默认关闭：退出 0，无网络
.venv/Scripts/python.exe scripts/probe_olas_discovery_identities.py --identity-run runtime/olas-history-probe-20261018T060841Z-ff48df5e --discovery-run runtime/olas-discovery-20261018T063948Z-f38a1edd

# 新增 62 次背景请求：退出 1，部分身份 UNKNOWN
.venv/Scripts/python.exe scripts/probe_olas_discovery_identities.py --identity-run runtime/olas-history-probe-20261018T060841Z-ff48df5e --discovery-run runtime/olas-discovery-20261018T063948Z-f38a1edd --execute-public-readonly --proxy http://127.0.0.1:7897

# 只读原件离线修正：退出 1，8 PASS / 1 UNKNOWN，新增网络 0
.venv/Scripts/python.exe scripts/probe_olas_discovery_identities.py --identity-run runtime/olas-history-probe-20261018T060841Z-ff48df5e --discovery-run runtime/olas-discovery-20261018T063948Z-f38a1edd --retained-run runtime/olas-discovery-identities-20261018T064733Z-c4d2f161

# 复用全部旧身份/登记请求，仅新增 8 次 manifest GET：退出 1
.venv/Scripts/python.exe scripts/probe_olas_discovery_identities.py --identity-run runtime/olas-history-probe-20261018T060841Z-ff48df5e --discovery-run runtime/olas-discovery-20261018T063948Z-f38a1edd --retained-run runtime/olas-discovery-identities-20261018T064733Z-c4d2f161 --fetch-manifests --execute-public-readonly --proxy http://127.0.0.1:7897
```

首个身份原件 `runtime/olas-discovery-identities-20261018T064733Z-c4d2f161` 保留 9 次映射、45 次 getter、8 次登记 GET，全 HTTP 200。其中一项 RPC 正文回退。初版解析误将 2182 的可选 benchmark 链接当通用条件，导致 3 个无 benchmark 的登记被漏计，原 `result.json` 保留为 5 PASS。

修正程序后仅离线核对既有原件，新目录 `runtime/olas-discovery-identities-20261018T065031Z-26339715` 得到 8 PASS / 1 UNKNOWN，新增请求 0。没有覆盖首版 result、manifest、响应或观测。

随后 `runtime/olas-discovery-identities-20261018T065216Z-3ff423d4` 复用 62 条既有观测，新增 8 次 manifest GET，均 HTTP 200 且为 JSON 对象。其 `requests_observed=70` 是 62 条引用加 8 条新观测，**不是新发 70 次请求**。退出 1 仍表示 9 个身份尚有 1 个 UNKNOWN，不代表 8 个 manifest 下载失败。所有新旧原件均只追加。

## 可供声明分析的真实资料

8 个 manifest 的精确观测及响应路径为上述 `065216Z-3ff423d4` 目录下的 `service-{service_id}-manifest.observation.json` / `.response.bin`。该目录另有 `model-material-index.json`，逐个列出实际注册身份、源 URL、响应字节及 SHA-256、工具描述与输入输出路径；没有调用模型、工具或 analytics，也没有复制第三方分数。

| service_id / agentId | 实际资料 | 字节数 | 当前适用性 |
| --- | --- | ---: | --- |
| 2198 / 2198 | factual_research、superforcaster、问题生成、jury 判定、Olas Predict R1，共 5 项工具声明与输入输出 | 8827 | 可分析预测和判定声明；不同工具分别核验 |
| 2235 / 2235 | factual_research、superforcaster、校准搜索版、Olas Predict R1，共 4 项 | 7324 | 二元预测声明有具体输出 schema |
| 2340 / 2340 | 同类 4 项；实际不同 Mech 与运营地址 | 7324 | 二元预测声明有具体输出 schema |
| 2359 / 2359 | 同类 4 项；实际不同 Mech 与运营地址 | 7324 | 二元预测声明有具体输出 schema |
| 2360 / 2360 | 同类 4 项；实际不同 Mech 与运营地址 | 7324 | 二元预测声明有具体输出 schema |
| 3783 / 4107 | python_code_validator、repair、execute，共 3 项 | 5036 | 属代码工具；描述与预测输出模板不一致，不能硬套预测方案 |
| 3786 / 4110 | prediction_estimate、factual_research、superforcaster、jury 等 9 项 | 14785 | 可分析预测声明；jury 声明与通用输出模板有差异，逐工具处理 |
| 3066 / 3354 | Nephyr 风险管理、天气、钱包、回测、echo，共 5 项文字声明 | 1215 | 有实际功能文字，未给参数/schema；不能直接套二元预测或只测 echo 代表全部功能 |

各 IPFS URL 均来自实际登记文件的 manifest 服务，并与原目录该服务的 metadata CID 相符；只读 GET 固定官方 `gateway.autonolas.tech/ipfs/f01701220…`，没有访问资料内的业务 URL。保留网关字节不等于完成 CID/DAG 内容认证，该项当前仍 NOT_VERIFIED；进入历史判分还需验证声明/任务来源、具体输入输出、历史执行归属和独立判据。

前 5 个 manifest 的运营者文字均为 Valory，不能因运营地址不同就说是 5 个独立组织；3786 的资料 URL 为 localhost，没有主动访问它，也不能据此否定其链上历史可评价性。首批 8 份资料在此冻结，后续候选使用新配置、新运行目录。

## 第二批：严格沿原目录次序续查 6 个

配置 `configs/olas-discovery-identities-v2.json` 记录固定排除集合（2182 及首批 9 个 service），从原 40 条降序目录的剩余对象取前 6 个：3118、3264、3254、3440、3446、3443。没有重查目录，没有依据预测结果或期望分数筛选；其中 5 个目录 metadata 本来为空，仍按顺序保留并核实。

脚本新增固定配置选项 `--config`，可选本轮三个固定版本。链号、RPC、三个合约、快照及配置顺序仍严格验证，第二批选择必须和原目录排除后的前 6 个完全一致。登记若没有实际 manifest URL，记录缺项，不猜 CID、不把通用描述当充分业务承诺。

```powershell
# 默认关闭：实际退出 0，无网络
.venv/Scripts/python.exe scripts/probe_olas_discovery_identities.py --config configs/olas-discovery-identities-v2.json --identity-run runtime/olas-history-probe-20261018T060841Z-ff48df5e --discovery-run runtime/olas-discovery-20261018T063948Z-f38a1edd --fetch-manifests

# 实际退出 1：部分身份 UNKNOWN，资料缺项保留
.venv/Scripts/python.exe scripts/probe_olas_discovery_identities.py --config configs/olas-discovery-identities-v2.json --identity-run runtime/olas-history-probe-20261018T060841Z-ff48df5e --discovery-run runtime/olas-discovery-20261018T063948Z-f38a1edd --fetch-manifests --execute-public-readonly --proxy http://127.0.0.1:7897
```

原件 `runtime/olas-discovery-identities-20261018T065746Z-e62daa67`：**41 次新背景请求**，为 6 次桥映射、30 次 getter、5 次登记 GET，全部 HTTP 200。没有主机停权或限流，没有重复旧对象成功请求，没有追加模型/业务/analytics 请求。RPC 正文仍逐项解析，没有以 HTTP 200 宣称全部身份通过。

| service_id | 实际 agentId | 身份结果 | 当前资料缺口 |
| --- | ---: | --- | --- |
| 3118 | 3418 | UNKNOWN | getOperator 回退 code 3；不继续该对象登记/manifest；与 3098 同 metadata，不称为独立提供方 |
| 3264 | 3587 | PASS | 登记名 genbeep-camwel44，通用 AI 描述，无 manifest/工具声明 |
| 3254 | 3577 | PASS | 登记名 dronhus-rotlim20，通用 AI 描述，无 manifest/工具声明 |
| 3440 | 3764 | PASS | 登记名 furgus-gonlus95，仅“A set of agents placing bets”，无 manifest/工具声明 |
| 3446 | 3770 | PASS | 登记名 yonzez-leti69，仅同类下注描述，无 manifest/工具声明 |
| 3443 | 3767 | PASS | 登记名 sunar-dimnim43，仅同类下注描述，无 manifest/工具声明 |

这批没有实际可取的 manifest 链接，因此新增 manifest GET **0**。5 个身份 PASS 不代表准入六项齐全或可以进入三维评分；没有拿名字、下注标签或历史计数批跑声明分析。运营地址及完整证据引用保留在本批 `result.json`。截至第二批累计核查 15 个新实例，13 个身份关联通过、2 个运营者读取 UNKNOWN；本记录不替代尚未完成的历史样本核验。

## 第三批：未查且确有 metadata 的 9 个对象

独立配置 `configs/olas-discovery-identities-v3.json` 在原目录中排除前 16 个已查 service（含另一条线上的 2182），保留实际有 metadata 的剩余对象，并按原顺序取 9 个。这个选择只依据资料可得性，不读取预测好坏或第三方声誉分。第一、二批资料缺项不改写，也不通过猜 CID 补齐。

实际命令退出 **0**，不为新配置重复工程测试或重跑旧采集：

```powershell
.venv/Scripts/python.exe scripts/probe_olas_discovery_identities.py --config configs/olas-discovery-identities-v3.json --identity-run runtime/olas-history-probe-20261018T060841Z-ff48df5e --discovery-run runtime/olas-discovery-20261018T063948Z-f38a1edd --fetch-manifests --execute-public-readonly --proxy http://127.0.0.1:7897
```

原件 `runtime/olas-discovery-identities-20261018T070037Z-aecda7f0`：**72 次新背景读取**，为 9 次映射、45 次 getter、9 次实际 tokenURI 登记 GET、9 次实际 manifest GET，全部 HTTP 200，9 个身份关联 PASS；没有停止条件、重试、旧成功请求重发、模型调用或新业务任务。每阶段先写 manifest，观测与响应只追加。2469 为 NVM 支付类型，本轮仅取得公开资料，未购买订阅、付费、签名或发起任务。

| service_id | 实际 agentId | 实际 manifest 业务 | 当前适用性 |
| --- | ---: | --- | --- |
| 2469 | 2469 | 15 个工具，包括 prediction-online/offline、superforcaster、reasoning/rag、resolve | 有工具描述与输入输出；历史路径需使用对应 NVM 合约语义 |
| 3809 | 4134 | PT-95 Predict Mech：明确二元预测、web search、p_yes/p_no/confidence/info_utility，13 个工具 | 可做有来源声明分析，尚未核验真实历史任务 |
| 3791 | 4116 | Resolution Evidence Collector：source-bound 证据包；可透明返回调用者市场先验，confidence/info_utility 为 0 | 明确声明不浏览、不预测、不交易、不做市场裁决；不能硬套预测准确率 |
| 3661 | 3985 | 16 个工具名，通用 AI 描述，没有 toolMetadata | 只有名字仍不充分，不批跑模型或声称预测承诺齐备 |
| 2135 | 2135 | 18 个工具，含 binary prediction、reasoning/rag、superforcaster | 有实际工具描述与输入输出，按具体工具选择范围 |
| 2267 | 2267 | 15 个工具，同类 prediction、reasoning/rag、resolve | 有实际工具描述与输入输出，按具体工具选择范围 |
| 3795 | 4120 | Omen Probability Calibration Mech：冻结 isotonic 校准 | 声明无 LLM/浏览/钱包动作；须核校准输入和固定规则，不扩大为通用预测能力 |
| 2150 | 2150 | 18 个工具，同类 prediction、reasoning/rag、superforcaster | 有实际工具描述与输入输出，按具体工具选择范围 |
| 3798 | 4123 | Omen Liquidity Calibration Mech：流动性条件下 thin/thick 冻结 isotonic 映射 | 同属校准声明，不能只看标准概率字段就断言功能一致 |

本批精确证据 key 为 `service-{service_id}-manifest`，同目录对应 `.observation.json` / `.response.bin`。`model-material-index.json` 列出每份真实 URL、实际身份、文件摘要、字节数、工具声明与输入输出 JSON 路径，供根后续只分析充分资料；原件包含更完整上下文。未请求资料中的业务域名或 analytics 链接。

三批共新增 **183 次**身份及资料背景读取，加最初唯一目录请求共 **184 次**；离线分析引用次数不重复计为网络请求。首批 8 加第三批 9 共 17 个 manifest 网关原件仍未在本线完成 CID/DAG 认证，不因下载成功给功能或可靠性满分。三维完整评分目标仍至少 10 个，当前既有完整评分对象仍为 1，后续须按冻结政策选真实历史任务并独立核验。

## 24 实例的离线准入快照

新增冻结事实配置 `configs/olas-candidate-reviews-20261018.json`，保留实际 service_id、实际 ERC-8004 agentId、canonical 标识、Mech、运营地址、实际 tokenURI 和 manifest 缺项；没有修改旧 `configs/candidate-reviews-20261018.json` 或任何旧快照。前 5 个 Valory key 与模型资料一致，为 `olas-valory-predict-{service_id}`；其他为 `olas-gnosis-{actual_agent_id}`，例如服务 3786 对应 `olas-gnosis-4110`。已有 9 候选不在本次 24 记录中重复生成。

准入逐项区分：22 个登记资料关联 PASS、2 个 UNKNOWN；16 个取得具体功能声明，8 个仍不足。所有对象的业务接口、独立核验、历史执行关联和可归属逐任务历史仍待补，**完整就绪 0**。当前固定状态的 Mech/operator 关联已保存，但不能回推历史控制权；目录交付计数也不能代替履约样本。没有把这些缺口扣成 0 分，没有制造业务 FAIL。

通用离线 builder 保留原位置参数用法，新增显式 `--config`；新配置冻结全部观测和响应文件的 SHA-256，并在渲染前逐项验证。实际执行仅一次，退出 **0**：

```powershell
.venv/Scripts/python.exe scripts/build_expansion_admission.py --config configs/olas-candidate-reviews-20261018.json
```

输出 `runtime/admission-report-20261018T071049Z-f95cbda3`，包含 `admission-report.json`、中文 `admission-report.html`、`observations.json`、`manifest.json`。共 24 候选、0 READY，引用 **186 条不同既有观测**及其原始响应：本线原 184 条 HTTP，加复用 2182 的链号/固定 header 两条；372 个源文件摘要均已核对。manifest 明确 `network_requests_performed=0`、`scores_computed=false`，没有把引用数算为新请求。本子任务没有重新采集、调用模型、运行工程测试或导入数据库；DB 导入交由根执行。

## 2182 登记时间的独立补件

登记先后另行核验，不从当前桥映射反推历史。新增 `scripts/probe_olas_registration.py` 默认关闭，固定 2182，先用公开索引定位一笔铸造交易，再按可信 Gnosis RPC 核交易、回执和精确区块头；不从区块 0 盲扫日志。官方 Bridger 源码 `_register` 在 ERC-8004 `register` 后发出 `ServiceAgentLinked(serviceId,agentId)`，可与同笔 ERC-721 mint 共同核对。该事件签名已用本机 `cast keccak` 独立计算一次，退出 0。

首次请求 [Gnosis 官方文档所指的 Blockscout](https://docs.gnosischain.com/tools/Blockchain%20Explorers/blockscout) NFT 索引，实际 HTTP 301，未跟随。原件 `runtime/olas-registration-probe-20261018T071415Z-5e0465c4`，1 次新 GET，退出 1；当前旧 explorer 主页转向 Gnosisscan，不能假定旧 API 仍可用。

随后显式选择现有 [8004scan 公共目录](https://api.8004scan.io/api/v1/agents/100/2182) 的固定索引，实际 GET HTTP 200，链、注册合约、tokenId 均匹配，定位到 **block 44507431**、交易 `0xbe932f173bb3ce3979ef4b6242e83c3b18bb2e24ee55f30f7bc91f9fa46a4d49`。唯一回执读取遇到 HTTP 未取得 / ConnectError，按无重试规则停止，未读交易与 header。目录日期尚未作为链上登记时间采用。

```powershell
# 原 Blockscout：退出 1，保留 301，不自动跟随
.venv/Scripts/python.exe scripts/probe_olas_registration.py --identity-run runtime/olas-history-probe-20261018T060841Z-ff48df5e --execute-public-readonly --proxy http://127.0.0.1:7897

# 显式8004scan索引：退出 1，GET200后receipt ConnectError即停止
.venv/Scripts/python.exe scripts/probe_olas_registration.py --identity-run runtime/olas-history-probe-20261018T060841Z-ff48df5e --index-provider 8004scan --execute-public-readonly --proxy http://127.0.0.1:7897
```

第二次原件 `runtime/olas-registration-probe-20261018T071704Z-9d6c9ac9` 保存 2 次新请求及发送前 manifest。独立补件 `runtime/olas-identity-supplement-20261018T071732Z-be7554a5/identity-supplement.json` 只复用原 `head` 的 method/params/value `0x2e8de87` 及两份原件摘要，保留 `registration_gap`，**没有填写 registration_time**。其 manifest 绑定来源观测和响应，不含凭证。后续若确认可以补缺，用 `--index-provider 8004scan --index-run runtime/olas-registration-probe-20261018T071704Z-9d6c9ac9` 复用索引，不重发目录 GET；登记需回执/区块头双核后才完成。本节 3 次新读取属于 2182 登记补件，不混入前述 24 对象的冻结 184 条调查请求。

根随后明确授权独立补缺阶段：复用成功索引，receipt、transaction、header 各读一次，失败仍不自动重试。实际补采三项均 HTTP 200，退出 **0**：

```powershell
.venv/Scripts/python.exe scripts/probe_olas_registration.py --identity-run runtime/olas-history-probe-20261018T060841Z-ff48df5e --index-provider 8004scan --index-run runtime/olas-registration-probe-20261018T071704Z-9d6c9ac9 --execute-public-readonly --proxy http://127.0.0.1:7897
```

原件 `runtime/olas-registration-probe-20261018T071931Z-6fc803a1` 核实登记交易正是前述哈希，区块 **44507431**、hash `0x697eb533c9a45ba3117b4b5c3861b922c17582f2b43d5531756d0fe7d29d2a2b`、timestamp **1770210845**，即 **2026-02-04 13:14:05 UTC / 北京时间21:14:05**。成功回执中精确 ERC-721 mint(0→Bridger,#2182) 为 log 317，随后精确 `ServiceAgentLinked(2182,2182)` 为 log 325；实际交易、回执和区块头归属一致。这次才采用链上登记时间，与目录索引时间分开。

完整独立补件为 `runtime/olas-identity-supplement-20261018T071947Z-878ebc14`，包含原 `head` proof、`registration_time`、transaction/receipt/header 各自原 method/params/value/evidence；manifest 绑定全部原件与来源观测。旧缺项补件和失败请求保留不改。该回执共铸造 #2156～#2190 的 35 个 token，**不含新 first5 的身份**，不能借本次日期给它们补登记时间。登记调查累计新增 6 次 HTTP，本子任务未做评分或模型调用。

## first5 预测历史配置与采集

新增 `configs/pilots/olas-predict-{2198,2235,2340,2359,2360}-v1.json`，沿 2182 冻结 policy、chain、registry、N/hash、confirmation_head、cutoff 与有界页数，只替换实际 candidate key、Mech、服务号、真实 agentId、已取得的登记原件及摘要。5 个配置实际通过现有 `PredictionProfile.load`，退出 0，没有改变评分政策、补造声明或重复模型分析。

先只启动 2198 一个新增 collector，默认 2 个独立只读并发，与旧 2182 进程分开；原始任务 Mech 与事件仍独立核验。复用链号、head、快照、首批身份及已有市场/历史原件，遇到跨进程共享 host 停止标记不删除或更换端点。

2198 实际运行 `runtime/prediction-history-20261018T072135Z-26548298` 已退出 **0**：非 pilot，预先保存的计划为 READY、14 个独立市场、14 个任务，实际新增 418 次只读取证。完整 `bundle.json` 已交给根的独立报告核验流程；采集 READY 不等于三维已评分，未手工读取输出筛选概率或重做模型。

随后按根确认启动第二个实例 2235，复用已完整 2198 原件和相同固定市场状态，仍默认 2 并行；未启动其余三个 profile。运行 `runtime/prediction-history-20261018T072524Z-fc00242b` 已自然收尾、退出 **0**：非 pilot、READY、14 个独立市场和 14 个任务、432 次新只读取证，未触发共享 host 停止标记。两份 bundle 均已交根独立核验，不由本子任务直接给分；各自登记时间不得套用 2182。

用户随后明确调整优先级：先证明第一类的多对象复用，未证明时保持单对象窄试点。2198、2235 的本轮已启动取证保留，自然收尾后停止扩大第二类；2340、2359、2360 仅有 profile，未启动 collector。本子任务转为核查已有 LP 同类线索，不能用第二类的两个 READY 证明第一类已经通用。
