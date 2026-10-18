# 已有149声明的来源语义审阅

本轮由 **Codex逐项语义审阅81种不同业务原文**，映射到 **14 个实际注册身份的149条声明**。配置为 `configs/inventory-semantic-review-20261018.json`，绑定无关键词标签的事实库存 `runtime/capability-inventory-20261018T081606Z-faf14f32/records.json` 的实际 SHA-256。语义工作由Codex模型完成，没有新增DeepSeek或其他外部模型API请求、网络请求、新评分或工程测试。

每条 `mappings[]` 保留 canonical 注册标识、candidate_key、claim_id、原 operation、业务原文 SHA、连续业务引文及原始 source_citations。每项 capability 给出中文名称、action、domain、当前声明状态、是否计入当前 D、独立操作或内部阶段以及Codex审阅理由。资料明示的别名还绑定同 Agent 的目标 claim 作为依据。

**D仅表示有来源的当前业务声明，不表示可用或可测M。** 现有工具/schema、授权、独立结果、任务归属及样本充分性仍需另外判断。原149条声明不删除：146条有当前功能声明；Brain c18仅雇佣价格条款、c20明确未上线，以及4134 c13只有“Default LLM”泛定位，分别保留为SUPPORTING_TERM / NOT_LIVE / UNKNOWN，不增加当前D。

## 动作覆盖

同一个 Agent 可进入多行，不能相加为对象总数；同一 Agent 的模型变体或多条重复声明也不重复计身份。

| action | 当前声明涉及的不同Agent D | 说明 |
| --- | ---: | --- |
| read_query | 2 | 账户、资产、市场资料、运行历史或Agent Card查询 |
| derive_forecast | 12 | 实际业务语义声明生成事件概率，不含读取市场已有概率 |
| calculate_plan | 2 | 自动化条件评估、图表中的清算簇估计、仓位计划 |
| execute_write | 2 | 下单、规则变更、额度充值、平台仓位或收入操作；不表示获准主动调用 |
| monitor_alert | 2 | 条件监测、区间检查或定时报表推送 |
| research_content_code | 13 | 其中6个有通用模型/图表等独立操作声明，另外7个仅含预测或裁决的内部证据阶段，不能称13个独立研究接口 |
| verify_attest | 3 | 依据记录判断已发生事件或关闭后市场结果；没有声称链上写入投票 |
| other | 1 | A2A消息交换；未把通信端点推为链上操作 |

具体 capability 比动作簇更细，例如成交历史查询与衍生品下单分别统计；动作簇和 capability_id 都不是新增评分方案。提供方仍按来源声明处理，不能把UNKNOWN提供方、owner或模型品牌相加当成独立提供方。

## 对语义混淆的处理

- Degen 的 `get_trade_history` / `get_open_orders` 是查询，`hyperliquid_order` 明确是创建、修改和撤销订单。`prediction_market_*` 返回市场现有状态、隐含概率或规则，不产出预测，也不裁决市场。
- 图表中的 `liquidity` 是盘口热力图资料，不是流动性管理；清算簇是基于未平仓量变化的估算，原文明确不是交易所报告。
- `deepmind-optimization` 原文是通过优化prompt作预测，不是通用数学优化求解器。GPT/Claude/TEE等品牌、环境或输出概率示例不增加功能类别，声称TEE也不证明可调用远程验真。
- 2469/2267的 `superforcaster` 原文只有“runs superforcaster prompt”，先记通用提示词执行；SME两工具只声明构造问题专家角色，不从名称或概率示例补出预测承诺。同一工具若原文明示prediction，则单独按实际文字归类。
- 4110的 `resolution_evidence_pack` 实际描述为binary forecaster，按预测归类；其 `resolve*` 描述是依据记录搜索证据、判断has_occurred并返回vote，归结果判定，不能因p_yes示例改成预测或因vote字样改成链上投票。
- 4134两个别名由同metadata明确的“Alias for”关系及目标工具声明共同支持。`Default LLM`没有明确业务，继续UNKNOWN。
- Brain的免费look明确不签用户仓位；付费计划仍是计划；WBNB-only储备区间明确no trade，不把全部增仓分支都说成兑换。设计尚未构建的用户仓位执行不算当前D，价格和时间本身也不是新功能。

Codex语义映射生成时只用程序核对实际claim/canonical、原文摘要、连续引文及计数，不使用关键词分类。实际生成命令退出0；无标签事实库存离线生成也退出0。旧含 `capability_proposals` / `semantic_draft_capabilities` 的runtime快照保留历史，但这些字段已废弃，不能进入新的推荐输入；统一模型投影同样剔除了它们。
