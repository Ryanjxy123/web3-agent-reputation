# Zyfai 真实交易 Agent 的完整评分可行性

日期：2026-10-23。task_id：`FULL_SCORE_TRADING_AGENT_DISCOVERY`。本页只记候选调查，不表示已取得完整交易任务、已适配或已评分。

结论：找到两个不同 owner 的公开注册线索及共同再平衡声明，但本轮尚未确认两个可完整评分对象。实际匿名 MCP 初始化返回401，个人历史需认证；停止该主机后未重试或绕过，未执行资产操作。

## 两个对象与来源层级

| 线索 | 注册标识 | 索引中的 owner / agentWallet | 服务声明 | 当前证据层级 |
| --- | --- | --- | --- | --- |
| Zyfai Rebalancer | `eip155:8453:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:58937` | `0xd9f2e2cdb9d5110cfe7f2b0b698c98e5931d96f1` | `https://mcp.zyf.ai`、官方网页 | 8004scan公开索引HTTP200；未完成固定块链上注册独立核验 |
| Zyfai Rebalancer | `eip155:1:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:29103` | `0x8da1c4130c8c7a1e40a50dba0b43bea93639892d` | 同上 | 同上；注册在Ethereum不能推出业务只在Ethereum执行 |

发现来源为[Base条目](https://api.8004scan.io/api/v1/agents/8453/58937)和[Ethereum条目](https://api.8004scan.io/api/v1/agents/1/29103)。本项目不引用其中的声誉分、健康分或“verified”标签作为自己的结论。两个身份均指向共享服务，不据此断言两个独立提供方，也不将登记钱包直接视作实际Safe执行账户。

## 实际接口读取

使用项目`DiscoveryEvidence → SafeHttpClient`、显式代理`http://127.0.0.1:7897`，原件目录`runtime/trading-discovery-zyfai-20261023/`。六次真实网络请求，另一次因已认证失败停止而未发出；请求、响应、观察与SHA256均留存。

| 请求 | 实际结果 | 说明 |
| --- | --- | --- |
| 官方ERC-8004仓库Agent Card | 200 | 模板/方法资料，不是两个实例的交易原件 |
| 官方MCP仓库README | 200 | 可发现接口；不能将README演示当实例运行结果 |
| 两个8004scan条目 | 各200 | 取得声明及索引身份资料 |
| MCP域名的`/.well-known/agent-registration.json` | 404 | 本次未取得可选域名控制证明，不推出服务不存在 |
| `POST https://mcp.zyf.ai/mcp`，`initialize` | 401 | `Missing or invalid Authorization bearer token`；缺认证，非Agent业务FAIL |
| 同端点`tools/list` | NOT_SENT | 401后触发既有host stop，不重试，不借另一路径绕认证 |

官方[当前连接文档](https://docs.zyf.ai/docs/sdk/mcp-server)明确区分公开发现与个人账户访问：账户、仓位、收益、历史需认证会话；旧README不能替代当前生产权限。本轮未注册账号、发起OAuth、新建钱包、签名或充值。

## 三维缺项

| 固定维度 | 可取材料 | 目前不能出分的原因 |
| --- | --- | --- |
| 服务可用性 | 有正式MCP服务地址 | 未认证访问401；不能给每个实例分配共享平台健康分，未采正式10A槽 |
| 功能声明一致性 | 再平衡、权限约束、收益机会及证明方法有官方说明 | 未取得两个实例的真实决策输入、版本化规则、对应区块数据及交易效果，不能把声明或ZK示例当PASS |
| 交易行为可靠性 | SDK声明历史含交易hash、再平衡说明等 | 未取得实例Safe/授权绑定和足量原始任务，未形成独立7B；成功历史列表也不自动包含失败尝试 |

官方[历史接口](https://docs.zyf.ai/docs/sdk/api/get-history)包含`transactionHash`、`rebalanceLog`及可选证明关联字段；这表明存在值得申请只读导出的资料格式，不说明上述两个实例实际已有全部字段或足够样本。其`amount`是操作后的仓位余额，实际移动量应看`deltaAmount`，旧记录可缺该字段，不能把整个余额当作单次资金移动。

官方[Session Keys说明](https://docs.zyf.ai/docs/product/control/session-keys)有权限范围和目标注册表约束。后续须核验历史Safe、模块和授权状态；owner/agentWallet不等于会话执行密钥，更不等于任意合约调用许可。

官方[ERC-8004与ZK技术页](https://docs.zyf.ai/docs/product/execution/8004)明确称该层为proof of concept，并列出测试网地址及公开输入。其[示例仓库](https://github.com/ondefy/erc8004-implementation)的证明方法不能替代本轮两个真实实例的生产证明，也不能仅由证明有效推出链下APY输入真实或对应交易完成。

## 后续进入条件

保留为同语义的高价值扩展目标。只有取得可授权读取的多个实例服务、实例EOA→Safe及历史权限证明、真实任务/决策与交易闭合，确认至少7F和另一组7B可取后才考虑共用适配。单独取得普通用户OAuth或平台API key，并不自动允许读取其他owner的私人历史；需要具体实例的授权或官方公开证据导出。

本轮生产代码、评分、数据库与网页均未改。工程测试`NOT_RUN`，未改代码无需重跑前轮测试；网络调查结果见上表。
