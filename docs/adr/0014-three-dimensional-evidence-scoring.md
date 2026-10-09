# ADR 0014：三维冻结证据评分

日期：2026-10-10。范围：后续任务 4；沿用模块化单体和 policy-v1。

## 规则与分母

新增 `formal-evaluation-v1` 套件、`capabilities@3` 断言模板和 ReportCore 1.2.0。
`three-dimensional-v1` 从每个冻结输入重新执行纯规则，再按槽位的互斥 measurement purpose 聚合。
不新增评分依赖，不接受客户端统计或分数，不改 policy-v1 的工程基线参数。

- A 服务可用性：只使用 availability 槽位首次 POST 的原始 HTTP CAS 和一致的 Observation。
  n 为初次请求可归因且可判定的槽位；s 为有效协议结构响应；l 为其中响应时延不超过 3000ms 的槽位。
  `A=0.8*s/n+0.2*l/n`，最低 n=20。业务错误不自动成为结构响应失败，链 RPC 故障不撤销已证明的接口响应。
- B 功能声明一致性：每个必需声明能力等权，`B=mean(0.2*D+0.8*PASS/decided)`。
  D 需要已归因 HTTP 方法/能力结果的结构证据；人工确认声明本身不给 D=1，明确不支持才给 D=0。
  每能力至少 10 个已判定功能槽位，覆盖至少 80%，EVALUATION 规定的必要类别均须由真实事实证明。
  未测试和范围外声明仍保留在充分度分母，不能只挑高分能力。
- T 交易行为可靠性：只使用 behavioral 目的、正向、明确接受且可归因的独立写任务；`T=correct/decided`，最低 10。
  correct 必须通过既有交易、执行者、目标、参数、事件、任务关联、窗口和最终性断言。
  只读画像 T 为 NOT_APPLICABLE，不记零分。

UNKNOWN 不进入已判定成功率，却留在适用计划覆盖分母。经过冻结适用性重判的 N/A 排除对应不适用分母。
任务成功率为全部任务 PASS/(PASS+FAIL)，单独输出；它与 A/B/T 和综合分有不同分母。
每槽位贡献、映射引用、类别缺口随 raw_statistics 冻结。计算保持有理数，最后输出 bp 时 HALF_UP。
写入权重仍为 30/40/30，只读为 35/65；门槛仍为 20/10/10、80%、Q>=60%、TTL=86400 秒。

## 必要用例和版本隔离

正常基准 TaskEnvelope 继续严格校验，发送前持久化。v3 负例仅允许固定模板对受控 endpoint 的请求做明确变异：
非法摘要格式、禁止目标、非本地链 ID、过期 deadline。保留合法 ExpectedFacts 和授权基准；实际发送 payload 的哈希
由相同纯模板重建并比较。正确拒绝要求对应 HTTP status 和明确错误码；缺响应为 UNKNOWN，接受无效请求为 FAIL。
这些是功能测试，不计行为失败，也不由平台直接向禁止合约或另一条链广播。

v3 的 get_tx_status NOT_FOUND 只表示：在已核验链身份及固定 canonical 查询块所限定的观测中，独立 RPC
同时返回 transaction=null、receipt=null，Agent 返回 NOT_FOUND。它不声称永久不存在，不能证明别的 RPC 或将来仍找不到。
旧 v1/v2 对双 null 保持 UNKNOWN；旧报告不会因新规则被重判升级。
交易成功/回滚/pending 和存在记录的定位参数必须指向实际样本，缺少时保持 PARTIAL，不能造 hash 当成功样本。

## 冻结、复核与兼容

平台复用逐槽发送、数据库 fencing、原 request_id reconcile、CAS、报告发布锁和 anchor outbox。
只有全部槽位 settled 才核验，全部已核验才冻结。每槽原始输入、冻结链复读、最终响应和初次响应分别进入既有索引。
Verifier 从 ZIP 独立重判全部槽位、重建三维分母、评分和任务成功率并逐字段比较；不调用 Agent，不连接平台 DB/API。
多槽位执行复用一轮受控 HTTP 客户端；同步数据库、客户端初始化及签名复算在线程中执行，避免阻塞租约心跳。
报告材料和评分在 fenced 写入之前组装，最终事务只保存已计算结果；不延长租约或绕过 fencing。

ReportCore 1.0/1.1 和 task-replay-v1 的原有组合保留原计算路径；1.2 必须配正式套件和 v3。
新增可选字段在旧版本序列化中省略，历史哈希保持稳定。Schema/OpenAPI/TS 从共享类型生成。
无需数据库迁移，历史报告和证据继续只追加；离线一致性仍不能证明采集者诚实。
