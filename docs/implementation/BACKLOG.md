# 可执行任务卡与依赖

每张卡结束：更新STATUS，记录命令与真实输出，检查diff/secrets，做一个可解释逻辑提交。任务“已有文件”不等于通过；不能用TODO/空函数完成卡片。
任务前读对应spec；所有 `/api` 路由统一 `/api/v1`。M0/M1完成后先交接，不自动扩成所有P1。

## M0：目标环境与契约（先完成）

### M0-01 仓库保护与现状审查
- 输入：本地路径、预期remote、现有文件；依赖：无。
- 操作：pwd、git status、branch、remote、log、顶层文件；识别本地是否已有git、origin是否匹配、远程HEAD/内容是否可读。
- 输出：`docs/implementation/ENVIRONMENT.md`（不含用户名/密钥）、STATUS；按runbook选择clone/init/reconcile，不删除已有工作。
- 验收：已有改动完整保留，功能分支明确；auth失败与empty remote分开；不是仓库时git_doctor安全退出。
- 建议提交：`chore: record repository baseline`；无identity/有未知改动时只报告，不代设身份。

### M0-02 工具链与工作空间
- 依赖：01。文件：root pyproject/.python-version/uv.lock；四个Python包pyproject；web package/pnpm-lock；contracts foundry配置。
- Python基线3.12、Node基线22；具体patch/uv/pnpm/Foundry/solc/容器tag与digest按实际兼容锁定，不用latest/nightly。既有兼容栈优先保留并写ADR。
- uv成员显式列四包，platform/verifier/fixture通过workspace=true依赖core；schemas仅数据目录。core可独立安装。
- 验收：干净环境 `uv sync --locked`；能导入core/platform/verifier；`pnpm install --frozen-lockfile`；`forge build`。不能手写假锁。
- 提交：`chore: bootstrap reproducible workspace`。

### M0-03 共享领域契约
- 依赖：02；读DOMAIN/API。文件：core/models、ports.py、静态registry、schemas/generated、web生成types脚本。
- 实现Ref/Snapshot/Claim/Grant/Binding/Run/Slot/Attempt/Assertion/Report四态与reason枚举；边界参数严格校验。
- 验收：超大agentId不丢精度、错误hash/地址拒绝、unknown必须reason、readonly与writeprofile互斥；生成Schema后git diff无漂移。
- 完成字段样例供前端用，注明fixture，不连接真实页面冒充已测。
- 提交：`feat(core): define versioned domain contracts`。

### M0-04 数据库与任务存储
- 依赖：03；文件：platform/infrastructure/db、migrations、repositories。
- 建全部核心表与约束；先落agents/snapshots/claims/bindings/grants/runs/jobs/slots/attempts/evidence/assertions/reports/anchor_outbox/audit；可按DOMAIN拆2–3小提交。
- 只追加/唯一/外键/UTC约束；jobs租约+fencing；业务事务和网络调用分离；APIfetch参数化。
- 验收：真实PostgreSQL迁移空库→head；重复key拒绝；rollback；两worker SKIP LOCKED不同job；不能用SQLite证明队列正确。
- 提交：`feat(platform): add persistence and leased job repository`。

### M0-05 安全本地环境与API骨架
- 依赖：04；文件compose/env.example、SafeHttpClient demo policy、api auth/error/health、worker入口。
- 默认仅loopback发布；fixture网络独立；所有变更API要token/role；精确demo host白名单；公网开关关闭。
- init生成本地随机token不提交Git；API不持evaluator私钥，worker中进一步区分publisher权限。
- 验收：健康检查DB；未授权POST=401/403；不能从注册URI访问宿主内网；未知host拒绝；secret不出日志。
- 提交：`feat(platform): add authenticated local runtime`。

### M0-06 CI与基础质量门槛
- 依赖：02/03/05；文件.github/workflows/ci.yml、tests和开发scripts。
- 增加ruff/typecheck/unit/schema drift/frontendcheck/forge tests/Postgres integration；固定CI job名，规则保护后使用同名checks。
- 两类命令分开：check-bootstrap仅检本包参考；test必须跑实际代码。主CI禁止把被skip的关键集成显示成全部通过。
- 验收：新clone可复现；CI不需要付费服务/公网Agent/生产secret；fork PR不能获得写权限或secret。
- 提交：`ci: enforce offline reproducible checks`。

### M0-07 上游版本准备（不阻塞本地M1）
- 依赖：01；文件third_party/erc8004、configs/upstream-lock.json；读ERC8004。
- 仅能真实取到时锁commit/ABI/license/OpenAPI；无法下载记录BLOCKED，保持external enabled=false。不要猜agentId。
- 验收：锁filehash可重算；差异升级生成新版本；当前来源与自研模块标注清楚。
- 提交：`docs(integration): pin upstream references`（只有真锁成功才用pin措辞）。

## M1：真实纵向闭环（首次Codex会话的目标上限）

### M1-01 三个自研演示合约
- 依赖：M0-02/03；读EVIDENCE_AND_CONTRACTS。
- 文件contracts/src/{DemoAgentRegistry,DemoRecordRegistry,EvaluationAnchor}.sol、test、script、abi。
- 实现owner/版本变更、executor+request唯一存证、评价者权限+前向hash+单调序号+重复发布幂等。使用维护中的库需锁许可与版本，不copy未经检查代码。
- 测试：零字段/重复record/错owner/非evaluator/错误prev/不同publisher隔离/不能覆写/事件字段全；记录gas仅为实际测量。
- 提交：`feat(contracts): add local identity record and report anchors`。

### M1-02 部署、幂等seed与正常Agent
- 依赖01/M0-05；文件scripts/deploy/seed、fixture_agents/ledger/protocol、runtime生成配置。
- Anvil真部署三个合约、分离admin/evaluator/executor；seed创建A正常+D借用交易模式；持久ledger先存task意图再签名/广播。
- 受控JSON协议真实执行anchor_record并提供任务查询；D预存另一request成功tx，返回该候选tx但不告诉平台其异常模式。
- 测试：同request同payload返回原task/tx，异payload409；服务重启不丢ledger；seed两次不重复创建；链reset不复用旧部署配置。
- 提交：`feat(fixtures): implement durable normal and replay agents`。

### M1-03 本地注册快照、确认与最小可信绑定
- 依赖02/M0-03/04；文件demo reader、snapshot service、binding proof、capability mapping/API。
- seed只登记声明地址，平台仍核对owner与executor；实现nonce/snapshot/endpoint/链绑定与双角色EIP712签名的本地EOA路径。禁止仅信任JSON地址。
- M1只需anchor_record的人工确认映射；完整同义词提取留M2。外部复杂钱包unknown，不假造支持。
- 测试：错Agent/endpoint/expired nonce/另一签名人/旧snapshot拒绝；refresh新版本不继承旧binding。
- 提交：`feat(identity): bind local agent snapshots to executors`。

### M1-04 任务计划、领取与恢复
- 依赖03/M0-04；文件planner/worker/jobs/protocol adapter。
- 创建一次anchor_record功能slot，request和synthetic input发送前持久化；grant再次检查；attempts不可覆盖；重启先lookup/events reconcile。
- 不拿业务任务兼做availability/behavior统计。M1只有小样本，报告必为partial。
- 测试：重复Idempotency-Key不新建run，body不同409；worker发送后落ACK前退出不重复record；旧lease不能写回；cancel不删已发tx。
- 提交：`feat(worker): execute and reconcile idempotent task slots`。

### M1-05 采集器与确定性业务断言
- 依赖04；文件adapters/evm、core/assertions/record、evidence store。
- 独立受信RPC读tx/receipt/block/log，固定保存候选tx与原始脱敏字节；按spec逐项检验chain/instance/executor/target/receipt/event address/request/hash/deadline/finality。
- NULL receipt→待确认或unknown，不直接断言伪造；错摘要/无关成功tx必须FAIL并给具体原因。
- 测试：A PASS；D RECEIPT_SUCCESS但TASK_ID_MISMATCH等FAIL；wrong chain/contract/executor/hash；RPC中断UNKNOWN。
- 提交：`feat(evaluator): verify task-to-chain evidence independently`。

### M1-06 冻结报告与证据包
- 依赖05；文件core/evidence、platform/report builder、bundle export。
- 接入reference的初始规则与统计适配器，固定版本/评估时间；不改min20/10/10来制造总分。报告含assertions/slots/evidence/limitations，状态partial、overall=null。
- 用经过测试JCS库和Ethereum Keccak；sha3_256替代必须被测试拒绝；manifest内无hash循环，证据先脱敏再hash。
- 测试：相同包字节hash一致；字段顺序不影响JCS；关键字段变更hash变化；大整数不会浮点丢失；无密钥泄露。
- 提交：`feat(reports): create immutable partial reports and evidence bundles`。

### M1-07 发布与独立复核
- 依赖06/01；文件anchor_outbox/publisher、packages/verifier/cli、api/export/anchor。
- outbox持久化签名tx/nonce候选状态；广播超时先按tx hash和合约记录reconcile。Receipt单独保存，不回写report_core。
- verifier不连接平台DB/API：校验包→重做断言/统计/评分→外部受信配置核对链锚定。离线结果不得叫“链上已验证”。
- 测试：原包offline内容/重算PASS；online本地锚定PASS并标local-demo；改单blob/hash/score/policy失败；删文件INCOMPLETE；整包重算后的篡改由旧锚定识别。
- 提交：`feat(verifier): independently verify evidence and anchors`。

### M1-08 最小演示与交接
- 依赖01–07/M0-06；文件scripts/demo、tests/e2e、docs/runbooks、STATUS。
- 从API触发A/D，由worker执行；导出至少两份真实报告，发布至少一份并验证，复制一份改动后验证失败。可先极简页面或CLI，不做排行榜。
- 包含启动/迁移/部署/seed/demo/verify目标命令的真实实现，退出码非零表示失败。报告放Git忽略runtime，仅审过的脱敏样例可另存fixtures。
- 必须通过ACCEPTANCE的M1 gate，记录commit/环境/chain instance/命令/结果。不通过不能勾M1或继续主网/LLM。
- 提交：`test(e2e): demonstrate normal replay and tamper cases`。

## M2：完整评价与可重复实验

### M2-01 三能力与声明提取
- 依赖M1；core/claims/capabilities、dictionaries、case datasets。
- get_tx_status/verify_record/anchor_record；词典+否定+原文offset候选，人工review追加；未知/未覆盖声明不消失。
- 每能力10功能例包含正反例；正确拒绝非法输入为PASS，绝不计T失败；准备60条草稿标注、按模板分train-like开发/验收集，两位成员实审后才称人工真值。
- 测试：中文否定、混合/歧义、offset精确、不从未支持描述执行新工具。
- 提交：`feat(evaluator): add versioned capability suites and claim review`。

### M2-02 三维聚合与公平缺失
- 依赖01；scoring聚合器、schema/API展示、reference。
- A20slot、每cap10function、T10独立positiveaccepted；所有分母只按slot；unknown/NA/零样本、Q与当前失效overlay；映射冲突/requiredclasscoverage。
- 测试：完整36参考测试+真实slot派生golden；同原始证据重算一致；wrongpurpose不能计两次；关键冲突不被高总分或partial隐藏。
- 提交：`feat(scoring): derive three-dimensional evidence-based reports`。

### M2-03 A–H样本与版本/绑定异常
- 依赖01/02；fixture modes/datasets/e2e。
- A正常、B不稳定、C夸大、D无关交易/错摘要、E少样本、F关系未知、G版本变化、H只读；来自服务真实行为，不读取模式打分。
- F不为获得T样本越过授权/绑定前置；H无写入任务；G旧报告保留但新服务不能继承。
- 测试：八类预期结果+归因；异常模板标记controlled而不是现实主体负面标签。
- 提交：`test(fixtures): cover eight controlled evaluation scenarios`。

### M2-04 消融与策略敏感性
- 依赖03；scripts/experiment、datasets冻结、实验记录。
- B0只有可用性；B1加receipt未关联；B2完整。5个固定实验seed，任务request仍独立CSPRNG；保存失败/unknown而非删去。
- 记录每类判断、falsepositive/falsenegative/unknown与适用分母；不得伪造“实测准确率”。多个阈值只做敏感性，不偷偷用验收集挑最好policy覆盖v1。
- 提交：`test(experiments): add reproducible internal ablations`。

## M3：真实可用的产品与安全恢复

### M3-01 六页前端
- 依赖M0-03/M1-08；web路由/生成client/组件/tests。
- 列表添加、详情声明与已验证分区、任务进度、证据报告、同类历史对比、复核。run每2s轮询，终态停止，错误可理解；列表游标分页。
- risk原因优先，总分null直说暂不生成；Q非概率；source标签、local-chain标签；不跨profile/policy比较。mock仅前端独立开发模式，不影响正式演示。
- E2E从UI创建→等待→展开assertion→export；禁止页面手算权威分数。
- 提交可拆3–4个页面逻辑PR。

### M3-02 公网安全出口与权限
- 依赖M0-05；SafeHttpClient/public resolver/egress policies/securitytests。
- HTTPS/端口域名allowlist、IPv4/IPv6与DNS pin、TLS hostname、禁跳转、trust_env=false、体积/深度/并发/配额；嵌套metadata同样受控。
- 验收SSRF矩阵全通过且不能触达敏感目标；DNS TOCTOU测试不是只调用一次is_global；默认disabled，管理员授权后才能启用。
- 权限/限流/zipbomb/pathtraversal/secretredaction覆盖。不可用网络不得被误计Agent低信用。
- 提交：`feat(security): enforce safe bounded external access`。

### M3-03 恢复、发布并发、当前有效性
- 依赖M1-07/M2；reconciler、current-report projection、fault tests。
- 同Agent并发run/anchor正确串行；检测owner/endpoint变更、RPC链reset/reorg；旧事实不改，只追加失效标记和重评。
- worker/API/fixture/RPC分别中断恢复，证据部分缺失可解释；备份DB+blobs+fixtureledger+deploymentconfig并恢复一次。
- 检查1个run的slot总量与计数/进度一致，失败不会无限重试。
- 提交：`test(recovery): verify crash-safe evidence and publishing`。

## M4：公开生态与交付

### M4-01 ERC-8004/8004scan只读接入
- 依赖M0-07/M3-02；按ERC8004文档完成adapter、固定HTTP/RPC fixtures、live命令。
- 目标3公开候选/至少1真实快照；owner/URI由RPC独立确认；rate/auth/unsupported记录；API分页和registry范围完整。
- 不要求公网Agent都支持本协议，不授权就不主动跑业务；公开导入从不直接生成总分。
- 测试：自定义registry、巨型ID、URI变化、缺key/429/schema变动/服务故障；live结果与cache/replay分开。
- 提交：`feat(integration): import public registry snapshots`。

### M4-02 全量验收、测试报告与发布
- 依赖全部P0；ACCEPTANCE表逐项附证据；测实际运行环境和API性能，不能把目标值写结果。
- fresh clone setup/demo/test/verify，导出SHA256文件清单、依赖许可、已知限制、安全复核、版本tag；检查正式比赛匿名材料副本，当前比赛细则负责人复核。
- 本地开发仓库维持真实Git协作；匿名导出排除.git/个人路径/成员信息/远程链接，不改写团队git历史来“匿名”。
- 提交：`docs(release): publish verified implementation and test records`。

## 首批可并行分工
M0-03契约冻结前由负责人主导；之后B做M1-05/06、C做M1-01/03/07、A做M1-02/04集成、D做生成client/证据组件。
接口变更先小PR同步；M1-06/07必需双方共同核对哈希依赖图。每个PR附输入输出、失败路径、测试命令与新成员可复現步骤。
