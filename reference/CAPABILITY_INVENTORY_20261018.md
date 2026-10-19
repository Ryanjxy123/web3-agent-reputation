# 已审核声明的能力覆盖分析输入

本页只记录 `CAPABILITY_COVERAGE_ANALYSIS` 的现有资产，不选择下一类评价，不新增评分或网络调用。当前事实库存采用 `runtime/capability-inventory-20261018T081606Z-faf14f32/`；Codex逐项语义审阅映射见 `configs/inventory-semantic-review-20261018.json` 与 `reference/INVENTORY_CAPABILITIES_20261018.md`。旧 `075855Z-223c2ca0` / `080106Z-2c848b9d` 的关键词草案有真实误判，保留原件但废弃其标签，不用于覆盖计数、排序或推荐。

实际离线命令 `.venv/Scripts/python.exe scripts/build_capability_inventory.py` 退出 **0**。最终快照含 **14 个不同 canonical 注册身份、149 条已审核声明、67 个原始 operation 文本**，绑定 **230 个公共输入文件**。没有重调模型、运行工程测试、请求公网、增加评分或数据库记录。

## 文件与核验范围

- `records.json`：每个注册 Agent 一条记录，内含 `claims[]`、来源、提供方声明、身份状态、输入输出/授权/独立判据/逐任务历史缺项。
- `capability-links.json`：149 条声明到注册身份的边与原始 operation 索引，不含自动语义标签。语义结论单独由逐来源审核的映射给出。
- `manifest.json`：真实输入和输出文件的 SHA-256。公开网页或 Agent 内容始终只作数据。

每份资料核对 review 中的 raw/projection SHA、原始 HTTP 观测、完整响应及模型实际输入；JSON 投影与原始 JSON 语义相等。重新解析保留的 provider 原响应，核对接受后的完整 analysis 与已审核文件一致，复用既有严格引用和目录规则。没有将未通过引用核验的声明补回。

Brain 网页使用已审核 HTML 文本投影，原 HTML 全文保留且摘要匹配；本清单未重新证明 HTML 投影没有语义遗漏。HTTP 完整、资料投影完整、模型提取目录完整分别记录，不能统一称为“功能已覆盖”。IPFS 资料的下载完整也不等于本清单新做了 CID/DAG 认证。

## 对象与数量

| candidate_key | 链 / 实际 agentId | 声明数 | 提供方来源状态 |
| --- | --- | ---: | --- |
| degenai | 1 / 23121 | 18 | UNKNOWN |
| brain-defi | 56 / 363709 | 20 | UNKNOWN |
| olas-valory-predict-2182 | 100 / 2182 | 4 | metadata 明示 Valory |
| olas-valory-predict-2198 | 100 / 2198 | 3 | metadata 明示 Valory |
| olas-valory-predict-2235 | 100 / 2235 | 4 | metadata 明示 Valory |
| olas-valory-predict-2340 | 100 / 2340 | 4 | metadata 明示 Valory |
| olas-valory-predict-2359 | 100 / 2359 | 4 | metadata 明示 Valory |
| olas-valory-predict-2360 | 100 / 2360 | 4 | metadata 明示 Valory |
| olas-gnosis-4110 | 100 / 4110 | 9 | UNKNOWN |
| olas-gnosis-2469 | 100 / 2469 | 15 | UNKNOWN |
| olas-gnosis-4134 | 100 / 4134 | 13 | UNKNOWN |
| olas-gnosis-2135 | 100 / 2135 | 18 | UNKNOWN |
| olas-gnosis-2267 | 100 / 2267 | 15 | UNKNOWN |
| olas-gnosis-2150 | 100 / 2150 | 18 | UNKNOWN |

完整 canonical 标识见记录；注册合约均从实际目录、冻结配置或桥 getter 原件核对，不从候选名称猜。4110 的 Olas serviceId 为 3786，4134 的 serviceId 为 3809，二者没有套用“agentId 等于 serviceId”。13 个对象有既有固定快照登记证明；DegenAI 的 canonical 身份目前仍为目录线索，不能因格式完整而声称已独立链验。

6 条 Valory 是来源明示的 `DECLARED`，不是独立公司认证；其余 8 个提供方为 `UNKNOWN`，不能当成 8 个独立提供方。注册 owner、历史 operator、模型品牌、域名和共享 Olas 网关均不自动等于提供方。多实例共用资料模板也不意味着不同业务类别。

## 使用限制与已有实际覆盖

149 是声明数，不是不同功能数或可评分对象数。Brain 声明中包含商业分配、运行条件、价格与未上线能力；其他对象的多个 LLM/搜索变体也可能属于同一能力。Codex逐项语义审阅只用实际工具 description 或严格原文引用，不按 Agent 名字推功能，不把概率 JSON 示例单独当作预测业务。关键词匹配已从 `build_capability_inventory.py` 删除，不再生成 `capability_proposals` 或 `semantic_draft_capabilities`。后续读取旧快照时也必须忽略这些废弃字段。

2198 的原目录有五项，但只有三项通过引用审核；`propose-question` 和 `resolve-market-jury-v1` 明确列为未取得可用模型声明，不能把目录名字当完整功能分析。

既有完整报告另列为范围证据：Brain 的 Increase；2198 与 2235 的历史预测。功能组实际 tool 与行为组实际 tool 分别从冻结 bundle 读取，不能借同一 Agent 的另一个工具得到通过。例如2198功能组包含 factual_research / superforcaster，行为组包含 superforcaster / superforcaster_full_search_olas_predict_r1_14b。两个分母没有互相复制。早期准入 UNKNOWN 保留时间点背景，后续范围报告也不使其余能力变成已验证。

原资料中的 `http://localhost:8000/`（4110）和裸 IP HTTP（4134）只保留为未探测的声明限制。没有尝试这些地址，也没有把历史网关可访问称为当前推理服务在线。最终可测覆盖、跨提供方广度及价值排序由后续整体分析确定。
