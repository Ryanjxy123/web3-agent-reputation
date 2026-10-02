# 合约、执行绑定、证据承诺与复核

## 1. 三个自研本地合约
自研合约不声称是完整ERC-8004标准实现。无需复制其完整注册/声誉市场。
所有ABI由编译产物导出；Solidity编译器/Foundry/OZ依赖需锁定。下列接口名/参数在M0确定后不能各成员自行改名。

### DemoAgentRegistry
目标：受控Agent身份、owner、URI、声明执行地址、revision、deployment_instance_id；声明执行地址仍需签名绑定。
```solidity
constructor(bytes32 deploymentInstanceId);
function register(string calldata agentURI) external returns (uint256 agentId);
function ownerOf(uint256 agentId) external view returns (address);
function agentURI(uint256 agentId) external view returns (string memory);
function revisionOf(uint256 agentId) external view returns (uint64);
function setAgentURI(uint256 agentId, string calldata uri) external;
function setDeclaredExecutor(uint256 agentId, address executor) external;
function transferOwnership(uint256 agentId, address newOwner) external;
function deploymentInstanceId() external view returns (bytes32);
```
register的msg.sender为owner；更新仅owner；转让递增revision并清除声明执行地址。注册/URI/声明地址/转让必须发带agentId与revision的事件。
不实现ERC721全功能，不宣称tokenURI兼容；外部ERC reader走真正tokenURI，不能因名称相似共用错误ABI。
部署instance id必须每次全新reset重新随机生成并上链；相同chainId和创世块并不能独立区分本地重置。

### DemoRecordRegistry
```solidity
event RecordAnchored(address indexed executor, bytes32 indexed requestId, bytes32 recordHash);
function anchorRecord(bytes32 requestId, bytes32 recordHash) external;
function getRecord(address executor, bytes32 requestId)
    external view returns (bool exists, bytes32 recordHash);
```
key=(msg.sender,requestId)。禁止零requestId/零recordHash；同key第二次写入统一revert DuplicateRequest（包括相同hash），绝不覆盖。
真正的HTTP幂等在Agent ledger：重复请求返回已有任务/tx，不应再次发交易；合约唯一键是最后一道业务去重，不是对网络恰好一次的保证。
no payable、no token、no外部调用、no可升级代理。其他执行者可用同requestId，但平台只认可已绑定executor，防止抢先写入他人记录替代本Agent。

### EvaluationAnchor
```solidity
function anchorReport(bytes32 agentKey, bytes32 reportHash,
                      bytes32 policyHash, bytes32 previousReportHash)
    external returns (uint64 sequence);
function head(address evaluator, bytes32 agentKey)
    external view returns (bytes32 reportHash, uint64 sequence);
function lookup(address evaluator, bytes32 agentKey, bytes32 reportHash)
    external view returns (bool exists, bytes32 policyHash,
                           bytes32 previousReportHash, uint64 sequence);
event ReportAnchored(address indexed evaluator, bytes32 indexed agentKey,
    bytes32 indexed reportHash, bytes32 policyHash,
    bytes32 previousReportHash, uint64 sequence);
```
采用经锁版本的OpenZeppelin AccessControl或等价明确角色实现：部署者admin、EVALUATOR_ROLE发布；两者不是Agent业务执行者。
同(evaluator,agentKey)序号递增；首次previous=零hash；否则必须等于当前head，错误引用revert。
相同reportHash重复调用：已有且policyHash/previous一致则返回原sequence，不追加新记录；不一致revert。同一已发布报告不能更改字段。
禁止update/delete报告接口。修正报告新hash、new previous、supersedes旧report；不要删旧证据。
本地角色私钥分开；开发链可重置，链上承诺只体现演示和可复现价值，不声称生产级不可篡改。

## 2. 执行地址归因（项目自定义EIP-712）
ERC-8004的agentWallet是收款地址，不能直接拿它的所有历史交易计分。[S01]
基础版只接受EOA直接执行。智能合约钱包、代理、AA、转发器、多级委托未支持时标UNKNOWN，不强套tx.from=钱包规则。
M1就要有受控owner+executor签名及真实恢复验证；M2完善失效/转让/重放/过期/错误角色测试。不能先在DB写VERIFIED当替代。

domain：name=`Web3AgentReputationBinding`；version=`1`；chainId=注册链；verifyingContract=注册合约；salt=平台实例32-byte标识。
这里verifyingContract是域隔离字段，不意味着ERC注册合约实现了本项目签名方法。
Binding message固定字段：
```text
bytes32 agentKeyHash
bytes32 snapshotHash
address executor
bytes32 endpointHash
uint256 executionChainId
bytes32 executionChainInstanceHash
bytes32 nonce
uint64 issuedAt
uint64 deadline
uint8 signerRole                # 1=owner, 2=executor
```
owner和executor分别签对应role的相同业务上下文。校验签名恢复地址、owner在指定块真实ownerOf结果、nonce一次性、deadline、链/endpoint/snapshot完全一致。
即便owner=executor也签两个不同role消息；不能把一份旧“控制钱包”签名跨Agent复用。
endpointHash按规范化的已确认scheme/host/port/path/method/protocol对象做JCS+keccak，不包含token；token轮换与端点业务版本变化分别管理。
snapshot_hash本身不包含binding proof，避免签名/快照循环。
协议签名规范并不自带完整业务重放保护；nonce/域/用途/期限是本项目必须实现的逻辑。[S08]

## 3. anchor_record 必须核验的独立断言
受信RPC实际chainId/本地instance匹配；snapshot+review未替换；执行binding在任务时有效；任务预先持久化且request_id未被其他任务使用；发送前保存执行链链头见证；tx存在且to=允许record合约；tx.from=已绑定EOA；receipt.status=1；receipt blockHash仍在canonical chain且满足确认策略；event log.address=record合约；event executor/requestId/recordHash均匹配；事件位置和链区块处于任务窗口内。
requestId不可预测且首次持久化使用是防旧交易复用主条件，不能单靠“时间很近”。时间比较记录平台接收/发送与链区块上下文，本地可精确控制，外链不能假设区块时间等于网络送达时间。
合约decode必须固定ABI，检查topic/event签名，防同名伪造日志。只看calldata或只看tx.to不足以替代事件与回执核验。
已成功但requestId不同→TASK_ID_MISMATCH；摘要不同→RECORD_HASH_MISMATCH。若RPC不可读→UNKNOWN，不做确定失败。
确认策略是受信chain config；local可以1块但明确local-demo。公共链软确认与finalized必须分别标记；不自称任意N确认绝对终局。
读取后、报告冻结前检查blockHash仍canonical；后来重组追加revocation/re-evaluation事件并在current_validity提示，不修改旧字节。

## 4. 保存、脱敏和摘要
先删Authorization/Cookie/API Key、隐私字段；保存实际脱敏后bytes。blobHash=Keccak-256(stored bytes)，绝不能声称是未保存原文的hash。
Keccak-256不是NIST SHA3-256；不得使用hashlib.sha3_256替代。
JSON规范化用RFC8785兼容库及正式测试向量；不拿sort_keys=True当等价实现。[S07]
跨语言约定：大整数十进制string，时间固定格式，分数整bp，禁止重复key、不合法Unicode及NaN；UTF8无BOM。对象key按JCS，数组顺序显式定义；manifest按evidence_id排序、assertions按assertion_id、slots按slot_id，禁止从无序set输出数组。
source raw bytes可包含上游浮点字段：它们作为原始blob字节哈希，不混入需要整数约束的report数值计算；归一化时只取支持字段。

```text
blobHash           = keccak256(actual stored bytes)
policyHash         = keccak256(JCS(frozen policy object))
snapshotHash       = keccak256(JCS(snapshot core))
manifestHash       = keccak256(JCS(evidence_manifest))
reportHash         = keccak256(JCS(report_core))
```
report_core包括manifestHash/policyHash/snapshotHash、固定统计、结论、适用范围、代码/规则版本、链实例信息、前报告引用、已知限制。
reportHash字段本身、签名、锚定txHash、anchor确认进度不得进入自身hash输入。reportHash另作metadata、anchor receipt、数据库索引。

## 5. 报告包布局
```text
report_core.json
evidence_manifest.json
policy.json
snapshot_core.json
run_plan.json
claims_review.json
bindings.json
observations.json
assertions.json
schemas/                          # 固定数据格式，不含可执行代码
blobs/<64-hex-hash>.bin
anchor_receipt.json               # 未请求时status=NOT_REQUESTED；不是伪造已确认
FORMAT.md
```
所有非receipt业务文件均列入受report承诺的manifest，或由report核心直接引用它们的内容hash；不得留下“改了observations仍算包完整”的未承诺文件。
manifest条目包括evidence_id/path/blobHash/bytes/media_type/source/observed_at/collector_version/redaction_profile/chain/block/trust_group。
禁止manifest自包含自身hash；report_core不放manifest中形成循环。FORMAT为说明不代表业务真值；代码不放包里自动执行。
证据体不含秘密；signed raw tx若为了恢复保存，只能在平台受限outbox，不导出全量签名材料。

## 6. 独立复核步骤与能力分级
verifier安装于新的环境，不要求平台DB/API/内部文件路径。唯一可复用依赖是公开core和固定版本规则。
A安全解包：ZIP文件/解压总量/文件数上限；拒绝绝对路径、..、盘符、Windows反斜杠穿越、symlink、重复路径/大小写冲突、压缩炸弹；不下载任何包内链接。
B内容一致：严格Schema→每blob byte hash→manifestHash→policy/snapshot等hash→reportHash。缺文件=INCOMPLETE，已知hash不符=FAIL。
C规则复算：从固定run plan/observations/bindings/EVM记录重跑受支持断言，再按purpose归并slots和统计，最后跑policy；不只相信report自带stats。未知rule version=INCOMPLETE/UNSUPPORTED_RULE_VERSION，不能从包里import Python补齐。
D链上锚定：只用用户可信配置指定RPC/chain/contract/evaluator，核对真实事件、storage、reportHash/policyHash/previous/sequence、canonical block和确认状态。不能相信包自己给的RPC/合约/发布者。
E可选业务在线重核：重新取任务交易/receipt/log并比对；对已知特定RPC信任边界如实说明。历史网页响应无法在线重现，不由hash推断采集者诚实。

分别输出 `content_integrity` / `rule_recomputation` / `anchor_verification`；可另列 `business_evidence_replay`。离线anchor为NOT_CHECKED，不能展示“全部链上验证通过”。
离线包内自洽不能防恶意者重算所有hash后做一个新包；必须有外部信任锚、可信签名或链上记录才能发现“整个承诺被替换”。测试必须覆盖两种攻击。
即使可信锚通过，也只证明那份材料被那个评价者承诺过，不证明评价者从未伪造链下观测。

## 7. 存证并发和不确定广播
按(evaluator,agentKey,anchor_chain_instance)串行化冻结/发布；读取确认head后固定previous。不能让两个worker同时拿同一个previous而默默重写报告。
CAS冲突：保留原报告，刷新head并生成明确新revision/supersedes；禁止修改已交付report_core来换previous。
签名服务按(chain,address)协调nonce；持久化nonce、signed_tx_hash和受限signed bytes后再广播。广播结果未知先查hash和Anchor.lookup，允许重广播同一raw tx，不重新签新nonce制造重复版本。
平台报告生成成功与上链成功分开；网络失败不改变Agent评分，UI显示未确认/可重试。
