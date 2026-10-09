# ADR 0011：三能力共享任务模板

日期：2026-10-09。范围：本轮第 1 项，复用 M0/M1。

保留 TaskEnvelope/TaskResult 单模型，按 capability_id 校验必要字段和互斥字段。读取显式 query_tx_hash 或 executor/request/hash 与固定块；写入仍用不可预测 request_id 和 synthetic input。不增加网络协议、数据库表或依赖。

API 每 run 仍为一个槽位；只读允许无执行绑定，POST /tasks 是查询提交协议而非链写入。授权合同地址可不同于演示配置，planner 固定目标代码 hash，collector/fixture/reconcile 均按冻结目标工作。当前 ABI 仍是既有演示接口。

新字段在旧 anchor wire 的默认情况下不进入序列化，避免已冻结任务 hash、响应格式和幂等请求 hash 漂移。新读取任务必须完整携带其字段，不能借默认值构造虚假的 tx/log。

RPC null 或非 canonical 数据只提供观测缺口；读任务不把交易回滚等同查询失败。冻结时点不可恢复时诚实 UNKNOWN。共享 Schema/OpenAPI/生成 TS 同步更新；生成 TS 不代表实现前端。

验证：正常与错误输出、查询缺失/回滚/待确认、RPC 异常和固定块边界；真实 PostgreSQL、独立 HTTP Agent 和 Anvil；旧 M1 与历史 bundle 回归。实际命令和结果以 STATUS 为准。
