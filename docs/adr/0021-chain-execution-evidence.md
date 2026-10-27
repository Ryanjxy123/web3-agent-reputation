# ADR-0021：真实资产执行证据与评分分开发布

状态：2026-10-23实施。依据用户本轮授权，将“与区块链深度结合”作为主目标；资产交易、已有签名、授权和智能账户执行均纳入评价范围。操作者的新签名、资金与主网写入另需具体授权。本次全部使用公开历史只读证据。

## 决定

固定三维仍为服务可用性、功能声明一致性、交易行为可靠性，30/40/30；不修改已有政策、报告、样本分母或阈值。新增`chain-execution-evidence-v1`是背景事实核验快照，不是新的评分政策。三维解释可以引用同一真实操作的不同事实，但不将其重复加入F/B评分槽位，不由成功样本产生100分。

优先选择真实执行交易的Olas/Omen交易者，区别于已评价的Mech研究供应者。先留存官方索引30对象，再固定累计下注次数排序的前10个，不因缺项替换；每对象核验最近一次公开买入。该选择用于证明多对象共用执行核验，不能估计完整失败率或所有提供方覆盖。

共用规则`olas-safe-omen-evidence-v1`不按Agent ID分支：

1. 在交易前一区块核对Olas Service Registry的服务→Safe、配置哈希、注册实例、Safe owner/threshold。配置CAR每块重验哈希、重建UnixFS，取得链上配置所指的真实功能声明。
2. 交易/回执/区块/事件按链号、交易哈希、区块哈希、交易位置绑定，并检查至少64块确认。EOA提交者与Safe执行账户分别展示，不把收款钱包或relayer当执行者；当前群体由注册实例提交，若是relayer且缺独立内层签名者归属证明则UNKNOWN，不判业务失败。
3. 核Safe代理运行时代码；预期runtime取自官方部署工厂的历史`proxyRuntimeCode()`，工厂代码与官方codeHash匹配。历史masterCopy及实现codeHash也须与官方v1.3.0一致。观察真实已有ECDSA签名和Safe内层ExecutionSuccess/Failure，不单凭外层status=1，不声称平台独立恢复了签名公钥。
4. 解码Safe/MultiSend中的buy与可选approve；同笔授权核spender/额度，直接buy核历史allowance。比对已签金额、方向、最低接收、FPMMBuy、wxDAI实际转出及CTF实际到账。用固定块`getCollectionId(0,condition,1<<outcome)`和`getPositionId(collateral,collection)`独立绑定条件头寸ID。
5. 另留固定买入前256块全部匹配Safe结果事件，包括内层失败。该窗口混有其它业务、不含外层回滚和未提交任务，仍不当作买入完整分母。未适配或缺原件为UNKNOWN；有完整证据的明确矛盾才FAIL。

A缺真实服务可用性样本；F缺7个独立任务及总体采样；B缺与F独立的7任务和完整尝试/任务关联。因此本批新对象只发布事实、样本、缺项，不产生综合分。未来扩展数值评分须另立版本化政策，不能就地扩大本快照含义。

## 数据与兼容性

共享类型先定义于core，再生成JSON Schema/TS/OpenAPI。`AgentSummary`兼容增加有来源的profile及完整历史报告计数；停止用report.scope覆盖功能简介。注册链和业务链分别取证，不能互相推断。已发布report.json和DB报告行保持。

新增`agent_chain_evidence`只追加表及保护触发器；`Repository.initialize()`增量建表即可，不清库、不回填或重写旧报告。新API提供Agent快照及其附件白名单，另为旧报告提供从已绑定原件解释出来的交易视图。旧客户端可忽略新增字段；回退应用时保留新增表和原件即可。

公开分发包仅含必要原件、观察记录、请求计划和摘要。离线导入按输入哈希、原始请求参数、RPC结果、CAR及确定性业务规则重建，不接受包里的自报分数；不覆盖冲突路径。私钥、RPC/LLM秘密、数据库不进入包。

## 验证

以固定10对象生产来源重放验证多对象共用；必要负例覆盖Safe内层失败、未知入口、错误头寸ID、源文件篡改和Olas身份不得误走ERC-8004实时采评。旧Brain三步视图复用已有正常/篡改验证。真实PG追加与API附件白名单、原报告保持、前端构建及页面检查在本轮实施报告记录，不重跑无关旧测试。

## 一手来源

- [Olas Trader](https://github.com/valory-xyz/trader)
- [Olas Predict注册/索引常量](https://github.com/valory-xyz/olas-predict/blob/main/constants/leaderboard.ts)
- [Safe部署资料](https://github.com/safe-global/safe-deployments/tree/main/src/assets/v1.3.0)
- [Safe执行与内层结果](https://docs.safe.global/reference-smart-account/transactions/execTransaction)
- [FPMM业务合约](https://github.com/gnosis/conditional-tokens-market-makers/blob/master/contracts/FixedProductMarketMaker.sol)
- [Conditional Tokens](https://github.com/gnosis/conditional-tokens-contracts/blob/master/contracts/ConditionalTokens.sol)
