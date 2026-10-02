# ADR 0006：M1 本地快照与双角色绑定

状态：接受；范围：M1-03，受控本地 EOA 路径。

## 决定

注册只建立候选，不代表已核验。refresh 返回 PostgreSQL ingest job；独立 worker 在可信配置的 DemoAgentRegistry 上固定一个区块，读取 ownerOf、agentURI、revisionOf、declaredExecutorOf 和账户代码，复查区块仍 canonical。链实例由操作者部署配置、genesis/code/deploymentInstanceId 核对，注册文件不能提供 RPC。

M1 只接受受控 data URI 的严格元数据结构与受控端点，未知字段（包括 credential 字段）、任意 URL 和重复端点标签均拒绝。这样不会在 agent_uri 中另存一份未脱敏的 credential JSON。name/description 是公开声明，不应填写秘密。快照 hash 固定 core；证据引用放在 core 外，避免绑定证明产生循环哈希。快照没有自动继承 binding。

确认操作只支持已声明的 anchor_record，版本比较与追加写入在同一事务内完成。快照刷新、确认及绑定提交统一锁定所属 agent，避免旧版本在刷新后提交。RPC 与文件准备均在数据库锁外；ingest 的快照和 job result 同事务保存，进程在完成标记前退出后复用相同 snapshot_id。竞争 refresh 不覆盖后来版本。

owner 与 executor 分别签 EIP-712 role=1/2。core 用 eth-account 编码/恢复与 eth-keys 的明确坏签名异常；纯函数不取时钟、不访问网络。domain 和 message 严格沿用 EVIDENCE_AND_CONTRACTS：平台实例 salt、注册链/合约、Agent/snapshot/端点 hash、执行链实例、随机 nonce、300 秒有效期。端点 hash 排除本地 endpoint_id 标签，包含实际 scheme/host/port/path/method/protocol。错误签名不消费 nonce；有效提交在 PostgreSQL 行锁内原子消费，仅一次成功。签名前后都读取当前链身份；proof 记录核验区块证据，不声称对未来身份永久有效。

合约钱包/带代码账户只返回 UNKNOWN/BINDING_UNVERIFIED，不执行 EIP-1271 或假造 EOA 支持。未来 planner 在任务前还要核验 binding、快照、授权及当前身份。

证据先按 credentials-v1 脱敏，再 JCS，hash=Ethereum Keccak(stored bytes)。临时文件 fsync 后用不覆盖 link 原子发布；数据库只追加。失败事务可能留下无引用内容文件，不影响已冻结证据；读取时复核长度与 hash。此卡不提供垃圾回收。

## 兼容性与验证

数据库表/迁移不变；AgentSnapshot 新增默认空 evidence_refs，AgentView 新增 current_snapshot_id 与 SNAPSHOT_CAPTURED 状态，JobView 新增 snapshot_id，新增 BindingChallengeView；由共享类型生成 Schema/OpenAPI/TS。旧快照可以读取，但新绑定流程要求本轮真实 capture 和人工 review。

真实 PostgreSQL + Anvil 测试覆盖双签、错 Agent/endpoint/domain/nonce/角色/签名人、全零坏签名、过期、并发消费、旧快照、链上声明变更、合约账户 UNKNOWN、进程恢复、竞争 refresh、敏感元数据拒绝。独立 API/worker 原生 smoke 对 A/D 都做真实签名与链读取；D 的绑定有效只说明执行身份，不代表任务结果正确。

本卡不完成评价任务、报告、上链发布或离线复核；这些仍按 M1-04 至 M1-08 实现。
