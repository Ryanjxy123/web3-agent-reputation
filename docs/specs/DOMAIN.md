# 领域数据、状态和持久化契约

## 1. 统一表示
所有内部 UUID 用 UUID4；task request_id/nonce 用 CSPRNG 32 bytes，格式 `0x`+64小写hex。实验 seed 只控制故障模式和合成输入类别，不替代不可预测挑战。
`chain_id`、`agent_id`、EVM金额/大整数在 JSON 中为无前导零的十进制字符串；DB 用 numeric(78,0) 或经校验文本，不用 JS Number。
地址持久化为 `0x`+40小写hex；可另存 checksum 展示值。hash 为 `0x`+64小写hex。
时间为 UTC ISO8601，固定毫秒精度，如 `2026-10-02T10:00:00.000Z`；DB为timestamptz；时延以整数毫秒。
禁止 NaN/Infinity、不稳定浮点和重复 JSON key。分数使用 `score_bp`，0..10000，对应0..100分；Q使用 `sufficiency_bp`，0..10000，对应0..1。
空值必须与状态/原因组合；0是实际零分，不是未知占位。

## 2. 身份不是一个整数
`AgentRef = {namespace:'eip155', chain_id, registry_address, agent_id}`。
`agent_key_text = namespace + ':' + chain_id + ':' + registry_address + ':' + agent_id`；此拼接是项目内部键，不冒称 ERC 新增标准字段。
`agent_key_hash = keccak256(UTF8(agent_key_text))`，用于自研合约。
身份所在链 `registry_chain`、任务执行链 `execution_chain`、报告锚定链 `anchor_chain`分别存。P0受控执行只允许一个local instance，不默认三者永远相等。
本地实例另外记录 `genesis_hash + deployment_instance_id + registry_code_hash`。只有chainId不够区分Anvil重置。
source_type 为 controlled / public_registry / replay；replay 还记录原来源和回放时间，不冒充实时采集。

## 3. 最小领域对象
| 对象 | 必填内容 | 不变量 |
|---|---|---|
| Agent | AgentRef、source_type、created_at | 复合身份唯一，未核实候选不冒充已验证Agent |
| Snapshot | agent_ref、owner、agent_uri、原始资料引用、normalized_metadata、endpoint集合、read_block_number/hash、captured_at、snapshot_hash | 只追加；hash核心不含自身hash/绑定签名，避免循环 |
| ClaimCandidate | source_evidence_id、field_path、quote、start/end、polarity、candidate_capability、extractor_version | 字符位置定义为Unicode code point，不能用UTF-16偏移混算；未识别声明保留 |
| ClaimReview | snapshot_hash、review_version、confirmed_claims、unsupported_claims、mapping_refs、actor、reason | 人工只能确认映射，不能写分数；更正生成新review |
| BindingProof | snapshot_hash、executor、endpoint_hash、typed_message、owner_signature、executor_signature、nonce、deadline、status、verification_evidence | 收款地址≠执行地址；过期/转让/换端点不继承 |
| AccessGrant | snapshot_hash、endpoint_ids、capabilities、methods、paths、chain_instances、contract_allowlist、rate/concurrency、expires_at、operator、consent_ref | 默认拒绝；不能用metadata自授权 |
| RunPlan | run_id、固定快照/review/policy/模板/dataset、evaluated_profile、全部planned slots、expected facts、grants、planning_time | 发任务前冻结；只追加诊断attempt，不能删失败槽位 |
| CaseSlot | slot_id、capability_id、purpose、case_kind、required_class、expected_outcome、deadline、request_id | purpose唯一；正向行为组必须独立于功能组 |
| Attempt | slot_id、attempt_no、dispatch_state、started/ended、http_status、error_origin、evidence_refs、diagnostic_only | 重试不是新统计样本；不存在“最终成功覆盖原失败” |
| Assertion | assertion_id、slot_id、rule_id/version、outcome、reason_code、expected、observed、evidence_refs、critical | 不得无证据产生确定失败；UNKNOWN必须有reason |
| TaskLink | request_id、candidate_tx_hash、verified_tx_hash、executor、block_number/hash、log_index、match_status | 候选hash与已核实关系分开；重复tx不能借用加分 |
| ReportCore | 所有版本hash、观察窗口、scope、stats、scores、sufficiency、assertion_refs、manifest_hash、previous_report_hash、limitations | 不含anchor txHash；不可覆盖 |
| AnchorReceipt | report_hash、trusted_chain_key、contract、publisher、tx_hash、sequence、block/hash、confirmation、status | 与report分开；广播≠确认 |

Snapshot hash 的核心包括身份、URI、owner、受控规范化字段和原始metadata blob hash、观测区块；不含 bindings/claims review/run/report。资料同内容重复观测可复用内容但追加read observation；owner/URI/endpoint变化必须形成新版本。
接口展示 `declared` / `observed` / `verified` 三类字段，不把反向域名声明变成已验证钱包归因。

## 4. 状态分层（不要复用同一个 status）
AtomicOutcome：PASS / FAIL / UNKNOWN / NOT_APPLICABLE。
DimensionState：COMPLETE / PARTIAL / UNKNOWN / NOT_APPLICABLE。
RunStatus：QUEUED / RUNNING / PARTIAL / COMPLETED / FAILED / CANCELLED。
RunStage：SNAPSHOTTING / PLANNING / PROBING / EXECUTING / VERIFYING / SCORING / REPORTING / DONE。
JobStatus：QUEUED / LEASED / RETRY_WAIT / SUCCEEDED / FAILED / CANCELLED。
DispatchState：NOT_SENT / SENDING / ACKNOWLEDGED / DISPATCH_UNCERTAIN / RESOLVING / SETTLED。
AnchorStatus：NOT_REQUESTED / QUEUED / SIGNED / BROADCAST / CONFIRMING / CONFIRMED / FAILED / REORGED。
VerificationStep：PASS / FAIL / INCOMPLETE / NOT_CHECKED。验证报告无效不是Agent负面评分。

Run COMPLETED 表示执行与报告生成完成，不代表Agent每项通过。全是确定失败也可完成测评。
Run PARTIAL 表示部分流程有未知/阻塞，但已有不可变报告可读；后续补充信息生成新report revision。
没有足够证据的正常结束不使用HTTP 500。进程故障恢复看jobs，不靠修改Agent分数。

## 5. 原因码最小集合与归因
| 原因码 | 通常结论 | 归因与处理 |
|---|---|---|
| AUTH_REQUIRED / ACCESS_NOT_GRANTED | UNKNOWN | 缺授权，不进入Agent失败分母 |
| UNSUPPORTED_PROTOCOL / MAPPING_UNCONFIRMED | UNKNOWN | 平台适配/映射不足 |
| CAPABILITY_EXPLICITLY_UNSUPPORTED | FAIL（声明维度） | 已声明支持但合法请求明确不支持，保留响应 |
| BINDING_UNVERIFIED / BINDING_EXPIRED | UNKNOWN | 不推断钱包任务归属 |
| IDENTITY_CHANGED / CHAIN_INSTANCE_CHANGED | UNKNOWN或失效标记 | 冻结旧事实，停止新调用，创建新快照 |
| PLATFORM_RPC_ERROR / PLATFORM_NETWORK_ERROR | UNKNOWN | 不扣Agent分；记录错误环境 |
| RATE_LIMIT_PLATFORM_EXCEEDED | UNKNOWN | 平台超约定配额，不怪Agent |
| RATE_LIMIT_UNATTRIBUTED | UNKNOWN | 不能判断责任 |
| SERVICE_TIMEOUT | FAIL（仅符合负载且观测健康） | 未满足该次服务窗口；不是人格恶意 |
| SCHEMA_ERROR | FAIL | 已收到且能确定输出违反已确认协议 |
| SEMANTIC_MISMATCH | FAIL | 可判定业务结果不一致 |
| TX_WRONG_CHAIN / TX_WRONG_TARGET / TX_WRONG_EXECUTOR | FAIL或UNKNOWN | FAIL需有独立证据；只有一串未知hash时不推断在哪条链 |
| TASK_ID_MISMATCH / RECORD_HASH_MISMATCH / LOG_EMITTER_MISMATCH | FAIL，通常critical | 成功交易也不能通过任务归因 |
| TX_REVERTED | FAIL | 仅已接受、可归因正向委托计行为失败 |
| PENDING_FINALITY / RPC_RECEIPT_NOT_FOUND | UNKNOWN/等待 | null receipt 不足以证明“假交易” |
| ACCEPTED_TASK_DEADLINE_EXCEEDED | FAIL | 健康观察覆盖、已接受、超过任务窗口；无需断言hash造假 |
| INSUFFICIENT_SAMPLES / INSUFFICIENT_COVERAGE / STALE_EVIDENCE | 维度PARTIAL | 不生成完整总分 |
| NOT_DECLARED_READ_ONLY | NOT_APPLICABLE | 只读画像没有行为维度 |
| CANCELLED_BY_OPERATOR | UNKNOWN/未执行 | 不能归因Agent失败 |
| CONTENT_HASH_MISMATCH / MISSING_EVIDENCE / ANCHOR_NOT_CONFIRMED | 复核状态 | 属平台/材料问题，不改Agent分数 |

严格区分“查不到”与“确定无关”：假hash只在格式错误或有其他确定证据时作为输出错误；正常长度hash在RPC暂时无回执时未知。超时判定必须保存独立健康观察及deadline。

## 6. 数据库表与关键约束
PostgreSQL + Alembic，UUID主键，所有FK/index/unique在迁移里创建，不只写Python校验。

| 表 | 必须的唯一键/索引与约束 |
|---|---|
| agents | UNIQUE(namespace,chain_id,registry_address,agent_id) |
| candidates | UNIQUE(source,external_id)，含raw source ref与核实状态 |
| snapshots | UNIQUE(agent_fk,snapshot_hash)，按agent/captured_at索引，禁止业务API覆盖 |
| claim_reviews | UNIQUE(snapshot_fk,review_version) |
| binding_challenges | UNIQUE(nonce)，一次性消费/过期检查与验证同事务 |
| bindings | snapshot_fk+executor+proof_hash唯一，状态变化用verification event留痕 |
| access_grants | snapshot_fk+actor+expiry，撤权事件append |
| runs | UNIQUE(actor_id,idempotency_key)，保存request_payload_hash；相同key不同payload冲突 |
| jobs | run_fk,type,state,available_at,lease_until,lease_token,attempts,max_attempts,last_error，索引(state,available_at) |
| case_slots | UNIQUE(run_fk,slot_key)，UNIQUE(request_id)，purpose CHECK |
| attempts | UNIQUE(slot_fk,attempt_no)，不得删除覆盖原attempt |
| observations/assertions | slot_fk,evidence_refs,rule_version；采集数据append-only |
| task_links | UNIQUE(chain_instance_id,executor,request_id)，txHash本身不作全局唯一任务凭证 |
| evidence_blobs | UNIQUE(blob_hash)，path仅系统生成；byte_count与mime、redaction_profile |
| evidence_manifest_items | UNIQUE(report_fk,evidence_id)，带引用角色、source_operator/rpc trust group |
| reports | UNIQUE(report_hash)，run_fk+revision唯一，core hash/previous/supersedes |
| anchor_jobs | UNIQUE(anchor_chain_instance,contract,publisher,report_hash)，receipt独立 |
| signer_nonces | UNIQUE(chain_instance,address)，持久化分配与signed outbox关联 |
| audit_logs | actor/action/target/request_id/time/safe_summary；不记录credentials |

API角色不能UPDATE/DELETE原始证据和已发布报告；受限应用角色/专用repository确保只追加。数据库超级用户仍能改数据，是明确的信任边界。
证据写入：先限流脱敏→临时文件→fsync/atomic rename到内容地址→DB事务登记；失败产生孤立blob可延后GC，不得反过来先登记“已存在”。
GC只删未引用的临时/孤立对象；已锚定报告引用blob不可自动删。备份必须包含DB、证据、开发链实例元数据。

## 7. API Schema单一来源
`packages/core/models` 的Pydantic v2 DTO为数据契约来源；业务模型不引用ORM。
由脚本导出 JSON Schema + FastAPI OpenAPI，并生成TS客户端类型；CI重新生成后 `git diff --exit-code`。
scoring_reference.py只是公式参考；生产DTO迁移保持golden不变。统计由观察派生，不能允许外部用户调用“提交stats直接得权威报告”。
Schema初始version为 `1.0.0`；新增可选字段可兼容，删除/重命名/意义变化升major并配显式迁移器。
