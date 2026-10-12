# ADR 0027：公共刷新预算按有限采集会话恢复

状态：已采纳；2026-10-12。范围 OPS-1，复用 ADR0019/0020/0021，不增加日/小时窗口、队列、依赖或数据库迁移。

实际 PostgreSQL/API/Worker 反例：同一个 IdentityService 的 8 次健康刷新，前 6 次成功，第 7/8 次没有快照，累计 HTTP=64，旧身份当前状态成为 UNVERIFIED。SafeHttpClient 的 64 次尝试本是每客户端的有限采集会话上限，缓存 Reader 使它错误覆盖整个 Worker 生命周期；不存在应当等待的日/小时恢复窗口。

每个未开始、获准的新 ingest 使用新 Reader/client，一次正常注册采集为 10 次请求；客户端在成功、失败或取消后 finally 关闭，64 次与失败计数、付款/协议 sticky stop、出口白名单、DNS/TLS 和零自动重试保持。只恢复新会话的资源预算，不延续已耗尽/付款停止的会话，也不回退任务授权配额。

复用 PublicReadonlyEgress 的固定 origin PostgreSQL session advisory lock、public.egress/public.egress.complete 审计和 fenced 短事务，给 identity 阶段使用。两个固定 origin 按一致顺序持锁，所有请求在 socket 前核对租约、公共开关、当前快照和持久预算；沿用共享 origin 节流记录，防止新 client、不同 Worker/进程重启绕过至少 1 秒间隔，也与现有公共评价/复核共享控制。锁只控制 I/O 会话，不在网络期间持数据库事务。

取消不能停止已经运行的 SQL 线程。获取锁时等待该线程结束并 invalidate 异常连接，真正关闭 PostgreSQL session；不能只 close 归还池。退出清理受 shield 保护，完成审计失败时持 origin 锁等待完整间隔，随后释放并继续传播数据库异常，防止仅用较早的请求开始记录放行下一会话。独立 Review 对这两项边界均用真实 PostgreSQL 复现旧失败、新通过。

refresh 继续锁 Agent 并拒绝同时存在 QUEUED/LEASED/RETRY_WAIT ingest；拒绝信息说明需等待当前任务完成。public_read_started 和保存后的 public_identity 恢复路径不创建新客户端、不重发、不新增重复快照。结果保存失败的重领保持 UNKNOWN/DISPATCH_UNCERTAIN；只有后续独立获准的 refresh 自动获得新预算，不需数据库修改或服务重启。

已耗尽会话通过既有 JobView.reason_code 显示 REQUEST_QUOTA_EXCEEDED，身份判断仍分别给平台 RPC/网络 UNKNOWN，不冒充用户 GRANT_QUOTA_EXHAUSTED 或远端业务 FAIL。Job 的处理完成不表示身份验证成功。没有新增共享字段，历史快照、原始 Evidence Bundle、三维评分、充分度、独立 Verifier 与 SEC 修复语义保持。

验证应覆盖连续 8+ 次健康读取、单会话耗尽/不合法重用/下一新作业恢复、并发 API/Worker、重启持久节流、fencing/取消/client 关闭、开始与保存的数据库故障、无重发恢复，以及公共评价/复核控制的回归。真实测试与独立 Review 结果另见本轮验收记录。
