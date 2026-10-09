# 三能力任务模板

M1 与 capabilities-v1 的单槽位路径保留，当前使用 @2，历史 @1 保留旧规则兼容。
正式评价使用 formal-evaluation-v1 / capabilities@3，一次预冻结互斥用途的多槽位计划；不增加协议适配器。

| 能力 | 输入 | 输出 | 独立断言 |
|---|---|---|---|
| get_tx_status | 链实例、query_tx_hash、固定查询区块号/hash、deadline | 查询的交易 hash、SUCCESS / REVERTED / PENDING / NOT_FOUND、查询区块号/hash | 独立 RPC 查询原 hash；确认回执交易/区块/canonical/finality，再逐字段比返回值 |
| verify_record | 链实例、目标合约、record_executor、record_request_id、预期 record_hash、固定区块号/hash | exists、实际 hash、matches、查询参数和区块 | 固定块调用 getRecord(address,bytes32)，独立检查 ABI 布尔值/hash 和全部返回参数；再次核对 canonical 块 |
| anchor_record | 链实例、授权目标合约、新 request_id、新 synthetic record_hash、deadline | 候选交易 hash、executor、record_hash | 独立交易/回执/事件匹配执行者、目标、calldata、emitter、request/hash、位置、发送后窗口及确认深度 |

只读能力不签名/广播业务交易，也不要求绑定执行钱包；仍须当前声明快照、人工确认映射、显式调用授权、冻结发送意图和原始 Agent 响应。写入能力继续要求双签执行绑定、持久 request_id、重启先 reconcile 和授权合约范围。

目标合约由操作者授权并冻结地址/字节码 hash，Agent 可使用不同地址。本轮支持既有 anchorRecord/getRecord/RecordAnchored ABI；其他 ABI 留给后续静态适配器，不能静默当成已验证。

查询正确报告“交易回滚”“记录不存在”或“记录摘要不匹配”可以 PASS，因为评价的是查询答案是否真实。平台 RPC 未见交易不能证明全网不存在，故 NOT_FOUND、节点 mempool 视图分歧、历史时点无法恢复、缺失/畸形 RPC、重组或确认不足均不能直接算 Agent FAIL。冻结块之后才上链的交易，历史查询无法充分重建时为 UNKNOWN。

v3 的 NOT_FOUND 明确限定为已核验受信链及冻结观测的 RPC 视图；候选 hash 必须与查询 hash 一致，RPC 两项确切 null、固定查询块 canonical、Agent 明确返回 NOT_FOUND 才可 PASS。
它不是全网或永久不存在的证明。v1/v2 继续将双 null 视为 UNKNOWN；新规则不改写历史报告。

正式套件沿用 EVALUATION 的 20 个可用性槽位、每声明能力 10 个功能槽位、10 个独立已接受写行为槽位。
只读画像不执行行为槽位。可用性优先只读能力；纯写声明缺少安全无副作用入口时 A 仍 UNKNOWN，综合分保持 PARTIAL。
操作者可以提供 transaction_cases（success/revert/pending）及既有记录的 executor/request/hash，仅用于定位；平台独立 RPC 核验实际类别，缺少或错误来源是证据缺口，不默认扣 Agent 分。
负例仅对明确授权的受控 Agent 发送固定无效 payload，比较明确拒绝 status/code；平台不直接向禁止目标广播。
初次 POST 与最终轮询分别冻结，重试不能替换可用性初次样本。完整评分、分母与版本见 ADR 0014。

Evidence 保留原始 HTTP、解析结果、冻结任务/快照/授权/绑定及独立 RPC 值；解析值与原始响应不一致必须显式暴露证据缺口。离线重放仅证明材料内部一致，不能证明采集者诚实或历史 HTTP 的真实性。

旧本地 seed 的注册声明和持久账本保留；新 seed 才声明三能力。需要演示只读能力时创建新的隔离部署/seed，或由操作者正常更新注册声明并重新捕获快照，不能修改旧冻结证据冒充支持。
