# 真实公共 Agent 候选与扩展记录

更新日期：2026-10-18。以下均为只读官方资料调研结果，未调用 Agent 业务接口或 RPC，未独立核验链上身份和交易；不属于已通过准入或已评分对象。

| 候选 | 已有资料与拟评业务 | 当前缺项 | 后续动作 |
| --- | --- | --- | --- |
| [DegenAI](https://degenai.dev/erc8004) | 官方标注 Ethereum agentId 23121，声明仓位、订单、余额和历史查询免费只读 | 接口实际可用性、注册核验、时间与缓存口径、Agent 自身可归属的执行交易证据均未核实 | 在授权范围内验证注册和公开只读查询，可与 HyperLiquid 官方资料对照；独立查找执行关联 |
| [Agent Arena](https://agentarena.site/) | 官方标注 Base agentId 18500，声明 Agent 注册资料查询接口免费 | 接口实际可用性、注册核验、Agent 自身可归属执行历史未核实 | 验证其声明的资料检索业务；自身身份核验单列，寻找执行关联 |
| [Synthesis Agent](https://github.com/darks0l/synthesis-agent) | 作者仓库标注 Base agentId 31929、执行钱包、任务合约及交易链接 | 未核实免费公开业务接口，交易与任务关联也未独立核验；资料读取失败不能判为 Agent 业务失败 | 查明公开业务入口与调用条件；有可信链上证据后核验执行关联，保留为历史行为候选 |

DegenAI 对照资料：[HyperLiquid 官方 Info API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)。DegenAI 文档提到约 5 秒缓存，不预设固定区块逐字段一致。

当前完整三维证据准入通过数：0。此数字是已核实状态，不代表这些对象最终不可测；完整评分至少 10 个仍是验收目标。

新增或排除候选时记录来源、实际检查结果、缺项和后续动作；明确区分未检查、资料缺失、尚未适配、缺授权与确认失败。不得为凑数或预期分数筛选，不把不可测记录删除后失去后续扩展线索。
