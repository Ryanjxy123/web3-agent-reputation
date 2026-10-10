# 任务 6：受控异常验证

本轮基线为 main `68ee882`。复用 A/D、持久任务账本、Worker、Evidence Bundle 和独立 Verifier；不新增槽位架构、不改变 policy-v1。正式评价机制已经存在，本轮可截取真实计划中的单槽位形成小样本报告，必须保留 PARTIAL，不能以少量重复运行凑成正式总分。

## 实现前固定的预期

以下预期来自业务规格和可观测事实，不从评分器输出生成。bp 是万分制；单样本仅允许展示 observed_score_bp。

| 事实/场景 | 任务预期 | 维度与充分度预期 | 风险预期 |
|---|---|---|---|
| 可归因 HTTP 503 | FAIL / AGENT_SERVICE_ERROR | availability 有效样本 1、有效响应 0，观测 A=0；功能失败仍是有效样本 | 普通失败，无 critical |
| 结构正确、响应 >3000ms 且 <15s | 业务事实正确则 PASS | availability 有效响应 1、及时 0，观测 A=8000 | 无 critical |
| 请求超过平台 15s 超时 | UNKNOWN / SERVICE_TIMEOUT | 不把超时归为确认业务失败；适用 planned 保留、decided=0 | 证据缺口，无 critical |
| 无可达服务、连接拒绝 | UNKNOWN / PLATFORM_NETWORK_ERROR | UNKNOWN 不算零分，保留覆盖分母 | 证据缺口，无 critical |
| 声明支持但明确返回 UNSUPPORTED_CAPABILITY | FAIL / CAPABILITY_EXPLICITLY_UNSUPPORTED | B 映射冲突=0，功能 PASS=0；有效协议响应可保持 A=10000；不能改成 N/A | 普通声明失败，无 critical |
| 历史成功交易冒充本次写入 | FAIL，交易/请求关联原因码 | receipt.status=1 不能替代 request_id、摘要、合约、执行者和窗口断言；行为 correct=0 | 已确认关联冲突保持 critical，PARTIAL 也否决 |
| 已接受写任务实际执行者不符 | FAIL / TX_WRONG_EXECUTOR | 明确接受且完整可信链证据才能进入行为有效分母 | 已确认执行者冲突为 critical |
| 注册版本/URI 或 owner 在发送前改变 | UNKNOWN / IDENTITY_CHANGED | 原快照失效，不继承原归因，不发送业务请求 | 证据/身份缺口，无 critical |
| 已验证绑定不能继续证明有效 | UNKNOWN / BINDING_UNVERIFIED | 不推断履约失败，不发送未授权写请求 | 无 critical |
| HTTP 403 授权拒绝 | UNKNOWN / ACCESS_NOT_GRANTED | 不计业务 FAIL，不算 N/A | 无 critical |
| 原冻结画像明确不声明能力 | NOT_APPLICABLE / CAPABILITY_NOT_DECLARED | 排除不适用分母；不是失败后的豁免 | 无 critical |
| 平台 RPC 断开/超时/畸形回执 | UNKNOWN / PLATFORM_RPC_ERROR | HTTP 可用性事实独立保留，业务 UNKNOWN 计入充分度缺口 | 无平台诱发 critical |
| 平台 RPC 返回错误链实例 | UNKNOWN / CHAIN_INSTANCE_CHANGED | 不把平台所选 RPC 的错误身份归因于 Agent | 无 critical |
| 格式合法但位置矛盾的 receipt/log | UNKNOWN / EVIDENCE_INCONSISTENT | 恢复复读保留原 UNKNOWN 与两份证据，不重写冻结结论 | 无平台诱发 critical |

每个单槽位报告预期 `evaluation_state=PARTIAL`、`overall_score_bp=null`。样本门槛仍为 A20/B每能力10/T10，覆盖80%、Q60%、TTL86400。availability、functional、behavioral 互斥，同一任务不跨维度冒充独立样本。

## 方法及复核

借鉴 [τ-bench](https://github.com/sierra-research/tau-bench) 的实际环境结果判定，以及 [AgentLab](https://github.com/ServiceNow/AgentLab) 的轨迹、原因、环境和重复运行记录；没有引入其框架或依赖。故障配置可复现，任务 request_id 仍由 CSPRNG 产生并先持久化。间歇故障不能随重试变成成功。

真实集成测试应检查 PostgreSQL 持久计划和原始 HTTP/独立 Anvil 证据，经 Worker 执行、核验、冻结，再用不依赖平台数据库/API 的 Verifier 比较任务、计数、维度、充分度与风险。RPC 故障注入仅修改平台观测层，正常 Agent 仍真实执行；这类材料必须明确为受控注入。

已有高分风险回归独立固定 A=9800/B=9600/T=9000/R=9480，仍要求 `NOT_RECOMMENDED`；历史规则和 ZIP 继续按原版本重放。真实结果、失败及修复记录见 STATUS，本文不将预期当成执行结果。
