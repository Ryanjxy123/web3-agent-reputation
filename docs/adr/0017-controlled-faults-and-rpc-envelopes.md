# ADR 0017：受控异常与 RPC 回执边界

日期：2026-10-10。范围：后续任务 6；保持既有评价架构及 policy-v1。

## 受控对象

复用 A/D 的 `normal`、`replay`，增加 `intermittent`、`timeout`、`unsupported`、`wrong_executor`。间歇故障按配置 seed 与持久 request_id 的哈希稳定选择，不因重试/重启抹去初次失败。故障配置不进入评分器。错执行者模式仅在明确指定模式且实际本地密钥不同的情况下允许，正常模式继续拒绝声明/密钥不一致；所有模式仍校验回环 Anvil、链实例及合约。已有签名 outbox 不能因模式变化丢失恢复路径。

版本变化使用真实注册 URI/revision 和新快照，不新增身份模型；绑定失效、撤权、版本变化不推断业务失败。测试在冻结前采样正式计划中的单槽位；正向写任务可独立指定 behavioral purpose，绝不同时记作 functional 样本。门槛不变，报告保持 PARTIAL。

## Review 发现及版本决策

规则 5 的 `receipt.status=0x2` 被当作 PENDING_FINALITY，缺失/布尔 status 被当作 SCHEMA_ERROR；合法但互斥的 tx/receipt 位置也与真实重组混用，恢复复读无法保留原 UNKNOWN。这些是平台观测问题。

新正式计划使用 `capabilities@6`、规则 `6`、ReportCore `1.5.0`。在生成依赖交易/回执的业务断言前检查：

- RPC 必要字段的格式，包括固定链身份、head、tx/receipt、按 hash 获取的块；回执 status 必须是 0 或 1。
- 同一个候选交易的 hash、blockHash、blockNumber 及写任务 transactionIndex 在 tx/receipt 之间一致。
- 交易 chainId 与已读取链身份、固定块请求高度与返回高度，以及同高度已确认 canonical/head 的 hash 不得互斥。
- 按 hash 读取的 receipt_block 必须与回执一致，head 不能早于已观测回执。
- 只读查询只要求其使用的字段；合法合约创建交易 `to=null` 是可判定的错误目标，不是格式错误。

畸形 RPC 为 UNKNOWN/PLATFORM_RPC_ERROR，内部互斥为 UNKNOWN/EVIDENCE_INCONSISTENT。canonical 块分叉和真实确认不足仍由原最终性规则处理；合法但错误的执行者、合约、参数或业务事件继续产生已确认业务失败和风险。平台故障不能形成 Agent critical。

只读能力额外以 `query.evidence` 检查固定块位置、canonical 块和 `getRecord` 的 `(bool,bytes32)` ABI；畸形或内部互斥可保留原 UNKNOWN，合法 canonical 分叉仍保持 STALE_EVIDENCE 并阻止冻结，不视为已恢复的观测污染。

`preserve_rpc_unknown` 仅对新规则实际回执证据断言、链观测断言以及原有明确 RPC 错误保留历史 UNKNOWN，恢复后原输入与复读输入分别冻结；在线 Verifier 单列恢复结果。没有原始依据的占位业务断言不能启用例外。原 PASS/FAIL 遇到坏复读仍拒绝冻结。

## 兼容

规则 1–5、ReportCore 1.0–1.4 保留原重放和哈希；已有在途 @5 明确冻结成 1.4。新格式贯通共享类型、Schema/OpenAPI/TS、Worker、报告和独立 Verifier。不改评分公式、权重、20/10/10 样本、80%覆盖、60%充分度、TTL 或合约；无数据库迁移和新依赖。本文只记录设计，实际验收见 STATUS。
