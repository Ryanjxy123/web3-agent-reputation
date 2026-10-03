# ADR 0007：受限授权、冻结任务和持久化发送恢复

状态：接受；范围：M1-04，单 anchor_record 功能槽位。

## 授权与计划

M1 授权请求只指定 snapshot、已确认 endpoint、max_tasks、interval、到期时间和 consent_ref；服务器从可信部署固定 anchor_record、POST /tasks、GET /tasks/{request_id}、执行链实例、record 合约、并发 1。返回的 AccessGrant 展示完整权限，不能把 metadata 当授权或使用通配范围。有效期最多 24 小时；单任务窗口 60 秒，授权与双签都必须覆盖该窗口。

创建 run 先验证 Idempotency-Key 与 payload hash；重放原请求返回原 run，即使它已完成或原授权后来过期。相同 key 换 body 返回 409。新 run 在短事务内锁定 Agent，检查当前 snapshot/review/binding/grant，预留 lifetime task quota，同时保存 run、唯一 CSPRNG request_id、合成凭证及其摘要、expected facts、NOT_SENT 事件和 job。一个 Agent 同时只有一个 QUEUED/RUNNING run；取消或未发送的任务仍消耗已预留配额，避免配额回退竞争。

计划和即时发送前的真实注册链读数都保存为证据。随机合成数据不是用户业务数据；重试不会重生 challenge/request_id。purpose 固定 functional，不复用为可用性或行为样本。评分门槛不变。

## 执行和恢复

每次 HTTP 前重新检查 grant、快照、scope 与 deadline；按持久化的 request start 时间等待最小间隔，等待和网络均在 DB 锁外。POST 前重新核对身份/双签/EOA，先 fenced 提交 SENDING 和 append-only attempt，再调用 SafeHttpClient。HTTP 时延在保存证据前计时结束，包含响应读取，不包含后续链查询或证据落盘。

服务端 status_path 只作为数据核对，始终自行构造固定 /tasks/{原 request_id}。响应、attempt、dispatch event 不覆盖。保存 txHash 仅表示 candidate，不能据此声称业务 PASS。

恢复 SENDING/未知状态先 GET 原任务，再通过可信 RPC 的 getRecord 和固定 ABI event 查询原 executor/request_id。只有 Agent 明确 TASK_NOT_FOUND、链也无该记录且仍获授权时，才允许相同 id/payload 重投；最多两个 POST 意图。取消未发送任务停止写入；取消已发送任务继续只读核对。撤权后不再访问 Agent HTTP，只允许可信 RPC 找回已发送记录。无证据证明健康超时时返回 UNKNOWN 原因，不把平台 RPC/网络故障扣给 Agent。

所有进度与完成写入带 PostgreSQL job lease/fencing；独立 heartbeat 保持租约。claim 使用短 advisory transaction lock，使全局最多两个有效 evaluate 租约的配额检查原子化；ingest 不占用执行配额。过期 worker 无法提交状态，但网络边界已开始的请求无法撤回，仍依靠 Agent 持久幂等与合约唯一键去重。这里没有宣称外部调用恰好一次。

可恢复 worker 异常按 5/10/20/40/60 秒退避并有尝试上限；耗尽时同步标识 run 的平台执行失败，不冒充 Agent 业务 FAIL。M1-05 将接入独立业务断言，M1-06/07 负责部分报告与发布复核。

## 兼容与验证

复用 M0 表和 persist_plan，新增可选的 synthetic_input、planning_evidence_refs、cancel_requested 等共享 DTO 字段及授权/评价 API 类型；不新增 DB migration。API 的 settled 表示发送流程已收束，未完成独立断言的槽位仍计 unknown。

测试使用真实 PostgreSQL、Anvil 和独立 uvicorn Agent。关键恢复用例令独立 worker 在真实 HTTP 返回后用 os._exit 退出，新 worker 接管后只查询原任务，检查一个 POST 和一条链上业务事件。另测发送前崩溃、同 key 并发、授权配额、全局租约配额、取消、撤权后的 RPC 恢复、真实拒绝连接 UNKNOWN。测试 Agent 环境不传平台 DATABASE_URL/operator token。

本机测试暂占受控端口 9101；测试前停止 demo A，测试只终止自身创建的服务，不杀未知占用者。Linux CI 独立执行同一真实 HTTP 流程。公网出口和 M2 多能力样本不在本卡范围。
