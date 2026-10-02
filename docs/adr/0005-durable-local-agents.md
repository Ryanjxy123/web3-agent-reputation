# ADR 0005：本地部署与独立 Agent 账本

状态：采用；2026-10-02。

部署只接受显式本地 RPC（127.0.0.1 或 Compose anvil），要求 chainId=31337 且 clientVersion 为 Anvil，不继承环境代理。六个角色随机独立生成：admin、evaluator、A/D 的 owner 与 executor。随机密钥/签名交易只写 Git 忽略 runtime，不使用公网账户；资金由受限本地 anvil_setBalance 提供。

setup outbox 在广播前保存签名 bytes/hash，命名操作重启后先按原 hash 查询、必要时仅重播原 bytes。完整部署重用前独立核对 code/genesis/on-chain deploymentInstanceId；未完成部署另以 Anvil instanceId 识别 reset。发现不一致拒绝复用，保留旧目录供检查，不自动删除历史。

Fixture 各有独立 SQLite task ledger，平台不能读取或直接写入。SQLite 仅用于受控服务自身账本，平台队列仍使用 PostgreSQL。POST 先冻结 request/payload，再返回 accepted；同 request+payload 返回已有状态，异 payload=409。签名 nonce/raw/hash 提交后才能广播；未知广播先查 hash，恢复不换 nonce。nonce 由同一账本事务串行预留，合约唯一键作最后去重。

D 的异常模式仅在 fixture 私有配置中：seed 实际写入另一随机 request/hash，D 收到新任务时返回这笔真实成功候选交易。平台看到的 metadata 不含模式，也不接收预设评分；必须由后续独立链断言识别不匹配。

新增 LocalDeployment/DeployedContract 和 ControlledTaskView/TaskResult 共享类型；Schema/TS 均生成。部署配置是操作者可信输入；不接受注册文件、HTTP 请求或 evidence bundle 指定新 RPC。

验证包含真实 Anvil 的双 seed、角色分离、HTTP 幂等、磁盘重开、签名后/广播后退出恢复、并发 nonce、D 成功反例和真实 anvil_reset。原生 HTTP 服务重启后再提交原请求，必须返回相同 txHash 且不产生第二条业务事件。当前 smoke 使用 synthetic snapshot，仅证明协议链路，不冒充完整平台评价。
