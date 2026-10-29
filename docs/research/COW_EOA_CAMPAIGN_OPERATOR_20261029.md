# CoW EOA 冻结任务操作接口（2026-10-29，ROOT 专用）

交付为可审代码和未冻结数据。本轮没有运行操作脚本的任何 phase，没有 HTTP/RPC、密钥读取、签名、广播或提交。工程检查不计业务样本，不产生评分结论。整体 10 个交易 Agent、各至少 30 个真实任务的目标继续。

新文件：`runtime/nox-iclone-preflight-20261023/cow_eoa_campaign_operator_20261029.py`、`client/sign-cow-eoa-campaign.private.mjs`。旧 `ophis_eoa_pilot_20261029.py`、`sign-ophis-eoa-pilot.private.mjs` 和 `cow_order_facts.py` 均逐项核对 pilot 冻结 source SHA，相同原字节保留。

草案 `runtime/ophis-cow-campaign-draft-20261029/plan-draft-v2.json`，SHA `016ee56775698340925906748455607c22aba57ebc975f840ef5e6cb54af663e`，`status=DRAFT`、`frozen_at=null`，引用旧草案 SHA `517c0bd04e41cab4fb3e9099f093e4764500fc25de35fa4031dd3b59aaabd989`。原草案不改。全部 30 个 UUID、expected 与 cases 保持；C01 retained-retrospective 由旧 pilot 导入，操作器拒绝重采。C24–C30 改为每项 fresh quote/build 后完整 validate，再隔离已声明的一个非法字段；appCode 文本与其哈希是一致的同一变更。其余正向任务字典逐项相同。

操作器的链、owner、两种已有 Base ERC20 是授权允许范围；实际方向、总输入、slippage、有效期、appData 费率/来源策略、协议部署、MCP tool 和参数来自冻结 plan。不存在按 Agent 名、域名或登记 ID 的评分分支。签入 gross sell 和独立最低买入值限制资产范围，未添加用户未声明的费用 cap；signed feeAmount=0 不表示没有平台、solver 或网络费用。代码仅准备和核对，不手填 PASS。

ROOT 冻结时另存 `plan.json`，设置 FROZEN/真实冻结时间并重新计算 SHA；不要把草案 SHA 当冻结 SHA。运行前核 `operator_policy.source_refs` 的不可执行 `.txt` 快照与当前执行源码相同。报表 exporter 只加入快照路径，不执行 `execute_path`。`operator_policy` 的 300/180/90 秒 TTL 是 ROOT 操作新鲜度保护，不用于服务 SLA 或评分阈值。已发布 Topaz ADR0032/0036 没有改字节。

环境接口（以下仅是给 ROOT 的命令说明，本轮未执行）：

```powershell
$env:REPUTATION_COW_PLAN='runtime/ophis-cow-campaign-draft-20261029/plan.json'
$env:REPUTATION_COW_PLAN_SHA='<root新冻结文件的SHA256>'
$env:REPUTATION_COW_TASK_ID='C02'
$env:REPUTATION_RPC_USE_PUBLIC_BASE='1'
$env:REPUTATION_DOH_RESOLVER_IPV4='1.0.0.1'
# ROOT 执行签名器时才显式设置已有 wallet.private.json 路径；不发布该值。
```

每次仅选择一个 task。任务目录固定为 `plan.parent/tasks/<frozen task_key>`，同经济任务的多个 HTTP 阶段不增加任务数。C09–C30 的 22 个非实兑任务共计划 52 个只读 MCP 请求，尚未采集；余额、surplus 的准确性没有独立匹配块/基准时仍为 UNKNOWN。

| phase | 行为及边界 |
| --- | --- |
| `collect` | 按冻结模板顺序发公开只读 MCP。每阶段发送前保存 CSPRNG UUID 与 exact JSON；已发阶段只读原件，不重发。4xx/5xx/工具错误/传输缺源保留，依赖阶段停止。429 保存全 campaign 停止记录，不切节点/域名规避。SafeHttpClient、proxy7897、pinDNS、25 秒、2 MiB。 |
| `prepare` | 无网络；重读原 quote/build/validate 并复用 `inspect_cow_order`。校验总输入、原 quote 推导 minimum、owner/receiver、全部十二字段/domain/type、精确 appData 文本/哈希/冻结策略、TTL 请求窗和 UID。写公开 TASK_INTENT/PREPARED_ORDER。 |
| `inspect` | 无网络；显示选择范围及已有 prepared facts，不执行未采阶段。 |
| `prepare-approve` | ROOT 只读当前可信 Base RPC/完整账户订单页；核 EOA 无 code、两个官方 runtime hash、relayer/domain getter、两 token 余额和授权、confirmed=pending nonce、真实 ETH、原 UID 新鲜度。只准备 input token 对精确 vaultRelayer 的 gross approve，原 allowance 必须 0，另 token allowance 0。模拟/估算 gas，并计入 L1/operator 上界。 |
| Node `approve` | 独立核冻结源、原三阶段请求/响应、经济和密码绑定及 exact type2；持久签名围栏后才进入本地已有 EOA key 接口，只签、不发。 |
| `send-approve` | 重新核原 payload/hash、来源/TTL、fresh nonce/funding/allowance；持久一次 SEND 意图后只广播原 raw transaction 一次。 |
| `proof-approve` | 只查原 hash；pending、reverted 分开，核 canonical inclusion/chain/executor/token/calldata/nonce/零 native value、精确授权及 principal 不变。 |
| `order-readiness` | ROOT 只读同块 code/getters/balances/精确授权/nonce/TTL，写公开就绪快照。 |
| Node `order` | 独立重算 EIP712 digest、原 56-byte UID、精确订单/appData/最低值和就绪范围；先持久 SIGN 围栏，再签一次，只签、不提交。 |
| `submit` | 再核真实资金/精确授权/TTL；保存公开 SUBMIT_PRESTATE 与私有一次提交意图，按冻结 native tool 映射提交原签名/原 order/原 UID 一次。私有 request/签名不入公开来源；ACK 只表示 accepted，不表示成交或 submit 判据通过。 |
| `state` / `proof` | 只按原 UID 读取官方 order/trades，pending/expired/fulfilled 分开。proof 核 canonical settlement tx/receipt、同 UID 的 Trade、owner净 ERC20 事件与独立前后余额、filledAmount、EOA code、64块距离及 allowance0。solver 的 tx.from 不冒充订单 owner；同钱包同 tx 多 UID 暂停并留待独立归因。再查不增加 task。 |
| `prepare-revoke`、Node `revoke`、`send-revoke`、`proof-revoke` | 原 input token 对原 relayer 精确 0 清理。ALREADY_ZERO 时不签/不发；非零残留必须在原 gross 范围，不扩大权限。 |

正常实际任务 ROOT 顺序：`collect → prepare → inspect → prepare-approve → Node approve → send-approve → proof-approve → order-readiness → Node order → submit → state/proof`。所有写 phase 是显式单步，脚本不会串联自动签/发/补发。任何不明写结果先对账原 UID/hash；不能换 UUID、重签、重发、重报订单以掩盖未知。确认不足只追加只读观测。撤销授权不计交易样本。

公开材料：每阶段 observation/body、公开 TASK_INTENT、PREPARED_ORDER、SUBMIT_PRESTATE、完整 public RPC observations 和 `states/<uuid>/source-item-execution.json`。source 格式直接复用现 CoW adapter 的 `task_key/http_observations/task_intent/prepared_order/execution{order_observation,trades_observations,rpc_observations,prestate{snapshot,rpc_observations}}`。PREPARED_ORDER 的 `plan_sha256` 按既有 adapter 语义指 task intent 原件 SHA；`campaign_plan_sha256` 另存冻结 campaign SHA。未知缺项不填 txHash/执行者/成交。

私有排除：secret、SIGNED/SIGNING/SEND、签名 submit request、raw transaction，及任何 `.private` 路径不能导出。签名器只在 ROOT 显式运行且全部来源/范围/新鲜度核验与排他 fence 完成后读取 ROOT 指定的已有 secret。本轮未读取任何此类文件。

验收：Python3.12 AST 五文件、`node --check` exit0；一个真实公开 pilot 原件/七种单字段隔离/哈希/未知规则/新字段/深度负控的定向离线测试，最终 1 test / 0.007 s / exit0。测试调整为可移植 fixture 后只复核同一项，不重跑旧 suite。原冻结 pilot 三 source SHA 一致。所有 HTTP/RPC/签名/send/submit/资金阶段、真实集成与新评分均 NOT_RUN。
