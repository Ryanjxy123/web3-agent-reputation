# 架构与目录契约

## 1. 架构选择
模块化单体，不以目录数制造微服务。一个业务服务包拥有数据与编排，API/worker 分进程启动；规则 core 和 verifier 是可安装的独立 Python 包。前端与合约各用自己的工具链。
这是对 PRD 原建议目录的工程细化：保留接口边界，把 `services/api` 和 `services/worker` 合为 `services/platform` 的两个入口，避免复制模型、连接配置和部署依赖。不是改变业务目标。

## 2. 最终目标目录（多数文件由 Codex 创建，不能误认为已经存在）
```text
web3-agent-reputation/
├── AGENTS.md / PLAN.md / README.md
├── pyproject.toml / uv.lock              # workspace，成员显式列出
├── .python-version                     # 3.12，patch 在环境锁记录
├── apps/web/
│   ├── package.json / pnpm-lock.yaml
│   ├── src/api/generated/               # 由 OpenAPI 生成，禁止手改
│   ├── src/pages/                       # agents, detail, runs, report, history, verify
│   ├── src/components/evidence/
│   └── tests/
├── services/platform/
│   ├── pyproject.toml
│   ├── src/reputation_platform/
│   │   ├── api/                         # routes, auth, errors, response views
│   │   ├── worker/                      # scheduler, leases, handlers
│   │   ├── application/                 # use cases: ingest/run/report/anchor
│   │   ├── adapters/
│   │   │   ├── registries/              # demo_registry, erc8004_reader
│   │   │   ├── discovery/               # scan8004
│   │   │   ├── protocols/               # controlled_http_v1, a2a_card_only
│   │   │   └── evm/                     # RPC collection / EOA proof service
│   │   └── infrastructure/
│   │       ├── db/                      # ORM / repositories / transactions
│   │       ├── jobs/                    # claim/reconcile/outbox
│   │       ├── network/                 # SafeHttpClient / trusted RPC clients
│   │       └── evidence_store/          # append-only content-addressed blobs
│   └── migrations/                     # 单一 Alembic head
├── packages/core/
│   ├── pyproject.toml
│   └── src/reputation_core/
│       ├── models/                      # Pydantic 领域DTO；不使用ORM对象
│       ├── ports.py                     # Protocol 接口
│       ├── claims/                      # 原文定位、否定、确认候选
│       ├── capabilities/                # 三能力模板及静态注册表
│       ├── assertions/                  # 对采集材料作确定性断言
│       ├── scoring/                     # 槽位统计、分项、充分度、接入建议
│       ├── evidence/                    # hash/JCS/manifest/report packing
│       └── scoring_reference.py         # 本包已提供，完整平台的回归参考
├── packages/verifier/
│   ├── pyproject.toml
│   └── src/reputation_verifier/          # offline / online / cli；不依赖 platform
├── packages/schemas/generated/          # JSON Schema 与 OpenAPI 发布快照
├── contracts/
│   ├── foundry.toml / src/ / test/ / script/
│   └── abi/                             # 自研合约生成ABI，不手写
├── fixtures/agents/
│   ├── pyproject.toml
│   └── src/fixture_agents/              # 持久化task ledger + 正常/异常配置
├── fixtures/datasets/                   # 种子、标签、golden，非运行数据库
├── configs/
│   ├── policies/ / examples/
│   ├── capabilities/ / dictionaries/
│   └── runtime/                         # Git忽略；本地部署与可信配置
├── third_party/erc8004/                 # Pinned ABI/spec/license，不fork完整产品
├── scripts/                            # setup / deploy / seed / demo / verify
├── tests/                              # reference / unit / contract / integration / security / e2e
├── docs/ / .github/
└── compose.yaml
```

## 3. 依赖方向（强制）
```text
Vue -> API -> application -> ports
                     |         ^
                  core      adapters / infrastructure
                     ^         |
               worker --------+
                     ^
              独立 verifier -> core （不依赖 platform）
```
core 只接受显式数据、固定策略、显式评估时间；不读系统时钟、不用全局随机数、环境变量、DB和网络。
链上采集器负责“取回交易与回执”，业务核验器负责“断言是否匹配”，评分器负责“汇总已判定槽位”；三者不得揉成一个方法。
前端不拥有规则算法；导入器不能写观察结论或报告分数；报告页面不拼装任意 SQL。

## 4. 稳定扩展接口
以下 Python `Protocol` 是目标签名，M0 转为可测试共享类型：
```python
class RegistryReader(Protocol):
    async def read(self, ref: AgentRef, at: ReadContext) -> SnapshotCandidate: ...
class DiscoverySource(Protocol):
    async def list_candidates(self, query: DiscoveryQuery) -> CandidatePage: ...
class ClaimExtractor(Protocol):
    def extract(self, document: SourceDocument) -> list[ClaimCandidate]: ...
class ProtocolAdapter(Protocol):
    async def execute(self, task: TaskEnvelope, grant: AccessGrant) -> AttemptObservation: ...
    async def lookup(self, handle: TaskHandle, grant: AccessGrant) -> AttemptObservation: ...
class CapabilityTemplate(Protocol):
    def plan(self, context: PlanningContext) -> list[CaseSpec]: ...
    def assert_result(self, expected: ExpectedFacts, evidence: EvidenceView) -> list[Assertion]: ...
class ScoringPolicy(Protocol):
    def evaluate(self, inputs: FrozenRunInputs) -> ScoreResult: ...
class EvidenceStore(Protocol):
    def put_redacted(self, data: bytes, meta: EvidenceMeta) -> EvidenceRef: ...
    def read(self, ref: EvidenceRef) -> bytes: ...
```
接口返回 DTO，不返回 ORM 实例/活动 HTTP Response。网络权限与链配置只能由受信注入，模板不能扩大授权。
静态注册表形如 `REGISTRIES['erc8004-v1']`、`PROTOCOLS['controlled-http-v1']`、`CAPABILITIES['anchor_record@1']`。
允许将来换解析器/协议/策略，但不得基于外部文件内容动态加载包。

## 5. 数据流
agent_ref → registry snapshot → claims + confirmed mapping + binding proof + grant → frozen run plan → durable jobs → HTTP observations → EVM observations → atomic assertions → slot outcomes → frozen stats → policy-v1 scores → report_core/manifest → anchor outbox → receipt → verifier。
一个 run 绑定确定的 snapshot_hash / review_version / policy_hash / template版本 / dataset版本；中途改变创建新 run，不把旧请求换到新身份下。

## 6. 进程与网络
Compose 服务目标：postgres、anvil、migrate（一次性）、deploy（显式一次性）、fixture-agent、api、worker、web。
fixture-agent 不连接平台数据库；拥有独立 task ledger volume。平台只可通过 HTTP 与其交互，不能读异常模式来给分。
control 内网连接数据库/API/worker；demo 内网连接受控Agent/Anvil/worker。未明确需要的服务不互通；不挂载 Docker socket。
web 默认 127.0.0.1:5173，api 127.0.0.1:8000；Anvil RPC 对宿主只绑定 127.0.0.1:8545；数据库不对公网发布。
公开注册读链用受信 RPC 配置；公共 URI 使用单独安全出口。外部网络开关默认关闭，M3 安全测试通过才启用。
容器 Python/Node 依赖与 named volumes 隔离宿主 `.venv`/`node_modules`；不让 Windows 与Linux混用依赖目录。

## 7. 配置、数据和代码版本
策略配置使用 JSON（整数基点），加载后严格校验；如增加 YAML 编辑入口，必须先转换为同一冻结 JSON，哈希只计算冻结后的实际策略内容。
每个版本号同时带内容 hash；单有 `v1` 字符串不足以防内容漂移。
运行报告记录 Git提交+dirty标记；正式验收必须用clean commit，开发 dirty 报告要标注。
密钥/令牌用 env 引用，never 写进 policy/Schema；部署地址在 configs/runtime，不是编译时常量。

## 8. 并行协作边界
A/负责人：workspace、API、DB、jobs、集成；B：core、用例、评分、实验；C：contracts、RPC证据、绑定、verifier；D：web、操作/发布说明。
共同改动区：core/models、generated schemas、policy和合约ABI须评审。只有统一契约通过后才允许模块并行。
一个迁移任务只改一个受控 Alembic head；并发迁移在合入前 rebase/merge revision，不在主线留下多个未处理 head。
