# ADR 0010：发布 outbox 与独立证据复核

日期：2026-10-03。范围：M1-07/M1-08；仅受控本地 Anvil。

## 决定

报告发布先在 PostgreSQL `anchor_jobs` 中保存链实例、nonce、已签名交易原文及交易哈希，再广播。`signer_nonces` 按链实例和发布者串行分配 nonce；广播异常只按已保存哈希恢复，不重新生成 request 或交易。回执写入追加式 `anchor_receipts`，不回写 `report_core`，因此回执变化不会改变报告哈希。

`packages/verifier` 只依赖 `reputation-core` 和 web3.py。CLI 在不提供 RPC 时执行安全 ZIP、manifest、全部 CAS 承诺、证据重放、断言/统计/评分重算，并把链上状态报告为 `NOT_CHECKED`。提供操作者明确的 `--rpc-url` 后，CLI 重新核对链实例、发布交易、合约记录、策略哈希、previous 哈希和确认深度；绝不读取包内 RPC 地址。

ZIP 不解压到文件系统；拒绝路径穿越、重复成员、符号链接、超大成员和高压缩比，且只允许 manifest 承诺的成员及固定格式文件。

## 兼容与限制

无需数据库迁移；M0 的 outbox/receipt 表已存在。发布密钥只从本地 runtime secret 读取，signed transaction 永不进入 bundle。`local-demo` 只证明本地 Anvil 语义，不代表公网最终性。

SEC-3 的回执/发布上下文一致性与离线、任务链、Anchor 的证明边界见 [ADR0025](0025-verifier-publication-identity.md)。回执未进入摘要不意味着其身份可与已承诺 publication 矛盾；所有原版本均拒绝这种不一致。
