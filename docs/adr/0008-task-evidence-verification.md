# ADR 0008：独立采集与确定性任务关联

日期：2026-10-03。范围：M1-05；仅受控 Anvil / EOA / anchor_record。

## 决定

发送恢复只产出候选交易。SETTLED 事务同时入队 verify；独立 worker 从操作者配置的 RPC 读取原始 JSON-RPC result，保存链身份、合约代码、发送前链头、交易、回执、日志、区块与 canonical block。证据保留十六进制数量，避免 JSON 浮点精度损失，不包含 RPC URL 或私钥。HTTP 服务标签不进入判断。

共享 RecordVerificationInput 固定计划、快照、review、双角色签名、授权、实际意图持久化时间和发送前注册见证。平台在数据库连接之外采集和保存 CAS 字节，然后用租约 fencing 在同一事务追加断言、TaskLink 和审计。事务后重试根据已有 TaskLink 幂等返回；旧 worker 不可覆盖结果。无需迁移数据库。

core 的 verify_record 不访问网络、数据库、环境变量或当前时间。先验证快照摘要、review、意图、EOA 身份和双签名（含注册链/合约及平台实例 domain salt）、授权及链实例；缺归因上下文为 UNKNOWN。随后逐项检查交易链/执行者/目标/calldata、回执、canonical/finality、固定事件签名/发出合约/执行者/request/hash/位置/窗口。单条可归因 FAIL 保留其他 UNKNOWN；只有全部必要断言通过才填 verified_tx_hash。

窗口同时要求记录区块高于规划与紧邻发送前的链头，并处于发送时间至 deadline 内。EVM 时间戳为整秒，时间上下界按秒比较，保存原毫秒时间供审计；不能用时间接近替代不可预测 request_id 与预先持久化。即使 request/hash 相同，发送前已存在的记录也不能证明本次执行。

断言 ID 由 slot_id/rule/version 的确定性摘要生成，目的仅为回放标识一致；它不是挑战值。request_id、绑定 nonce 和合成输入继续由平台 CSPRNG 生成。

## 兼容与限制

ExpectedFacts 新增可选 target_code_hash。新计划固定目标字节码摘要；旧计划不补写，缺此证据时 UNKNOWN。新增四个共享验证模型，JSON Schema/OpenAPI/TS 一起生成。API 新增 GET /api/v1/evaluations/{run_id}/verification。

M1 当前只有一个 anchor_record 功能槽位，尚无完整评分/报告。local-demo 一块确认是本地演示策略，不代表公网最终性。平台 RPC 故障、缺回执、换链、缺身份证据不转换为 Agent 失败；已确定错误任务/摘要保留具体原因及 critical_conflict。

离线回放证明保存材料与规则的一致性，不证明采集者诚实、数据库从未复用 request_id 或历史 HTTP 的真实性。链上在线复核须用复核器自己的可信配置；报告冻结前 canonical 再检和导出/发布归 M1-06/07。

## 验证方式

真实 PostgreSQL、独立 HTTP A/D、真实 Anvil：A 全部必要断言 PASS；D 返回成功回执，但 request/hash 不符而 FAIL；另发送真实错误执行者/错误合约交易，预写匹配记录后再调 Agent，连接另一 Anvil，以及读取不存在的交易。保存证据再经纯规则回放要求结果完全一致。

字段篡改测试单列为捕获材料的确定性规则测试，不冒充新链交易。完整结果记录于 STATUS；原生独立 API/worker smoke 输出 verification-smoke.json，后续完整 M1 仍须真实报告/存证/独立复核验收。
