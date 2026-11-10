# 0035：CoW 标准订单、UID 与公开服务来源重放

状态：DRAFT，2026-10-29。新增独立 `retained-cow-swap-campaign-v1` adapter；旧报告、旧 origin、共享 v3 单分与 30/40/30 不变。该版本尚未接入 shared_report、profile 或 chainview，不能声称已发布或已完成 30 任务。

冻结前操作支持：只读采集器与来源重放共用纯函数`derive_cow_argument`。原`stage-value`/`quote-minimum`保持相同结果；新增闭集`object-overlay`/`json-overlay`/`keccak-utf8`仅替换原对象已有字段、深度最多8，不解释代码或URL、不签名、不读时钟。保护任务先保留fresh quote/build，再对完整validate参数隔离一个非法字段；appCode文本与对应appData哈希同步，避免额外哈希错误混杂。操作软件以不可执行文本快照及SHA进入新草案和来源清单，`execute_path`只供root本地运行前核当前源码，不在报表中执行。ROOT独占的采集、授权、签名、原UID提交与对账接口不构成已运行实验；未知写结果只对账原hash/UID，禁止换任务或重发。旧Topaz报告及ADR0032/0036不变。

协议模块只处理标准 EIP-712 Order、domain、精确 appData UTF-8 哈希、56-byte UID 和 canonical Trade/Transfer 编码。服务 tool、remote、orderbook host、appCode、partnerFee 和来源映射置于冻结计划及认证声明原件；不得把一个服务的品牌、费率或收款地址作为所有服务的规则。当前执行核验范围为 Base、ERC20、exact-input sell、FOK、本人显式 receiver；hooks、partial-fill 和未核 legacy 非零签入费的净额规则保持 UNKNOWN。

身份复用 ADR0034：官方 MCP 具体 name/version/remote 是公开服务身份；未证 ERC8004 时链注册为 UNKNOWN，不进入 A/F/B。实际 native MCP 请求/响应逐阶段精确绑定；quote/build/validate/submit 仍共享同一经济 task_key。完整公开报价与 unsigned build、官方已成交订单 API 原件可保留；私有签单、原始私有 submit 请求、密钥不进入公开 source，signature 不复制到 facts 或正文。只有手工 ACK 不足以使 submit 工具 PASS。

行为按 `(chain_id, order_uid)` 去重。一个 settlement tx 中多个不同 UID 可属于不同任务；每个 UID 必须重新计算 digest/owner/validTo，匹配官方 order/trades、真实 Settlement emitter、canonical tx/receipt/header、期限、64 块距离、本人收款及 allowance 清零。若同钱包同 tx 存在其它 UID，须补其公开订单以核本人收款和 UID 密码绑定，并按全部本人 Trade 汇总净事件，与公开前快照到回执块余额变化核对；不得把一份全 tx 净增重复作为各 UID 的输出。事件不能归属或余额窗口含其它变化为 UNKNOWN，保护退出不补正常 B。

本 assessment 的原 pilot 显式为 retained-retrospective，引用原冻结经济意图、unsigned build SHA 与公开 snapshot/RPC；不把新 case 宣称为 pilot 前已冻结。新任务只有计划冻结后才可发送。DRAFT 没有冻结时钟，builder 必须拒绝且不创建报告目录。A/F required_decisive 沿用 v3 覆盖含义，不增加“所有声明/正常槽位均可判才出分”门槛；正常 B 保留双向各四目标。

代码作为 artifact 内按真实 SHA 分目录保存的只读文本 provenance，不动态 import 或执行快照。公共来源白名单只收明确选择的原件与 body pair；旧原件和失败不覆盖。新增版本不迁移或改写已发布报告；后续适配范围或冻结规则改变须另立 ADR。

必要回归：真实 pilot 的 unsigned Order/UID 与公开 canonical 资产链离线重放；改 owner/amount/domain/appData/deadline/Trade emitter/UID 拒绝；缺 receipt/header/allowance 保持 UNKNOWN；同 UID 不得跨任务复用、同 tx 不同 UID 可区别；DRAFT builder 拒绝、私有输入排除。受控差分不算真实新任务或新成交。
