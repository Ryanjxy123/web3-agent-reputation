# ADR 0021：正式公共只读评价与独立原件复核

状态：已实现并完成定向/真实验收，完整回归待确认；日期：2026-10-11。前置：任务8/9已验收合并。

Akashi 的免费 `find_proof` 查询返回历史存证信息，没有本次平台 request_id
对应的写入，也没有受控执行者双 EIP-712 签名。现有 TaskEnvelope/ExpectedFacts
要求的 executor、RecordAnchor 事件和 binding 不适用于这种业务；不得填入 Owner、
历史 submitter 或占位地址来制造执行归因。

采用独立 PublicReadonlyTask/Facts/Slot/Plan/Grant/VerificationInput，显式
`public-readonly-v1` / `public-readonly@1` / rule7 / ReportCore1.6。仍只使用原
evaluate→verify→report Worker、租约/fencing、PostgreSQL表、CAS、Observation、
断言、评分和Bundle外层。旧受控入口、规则1–6及报告1.0–1.5的语义和默认序列化保持。
TaskLink新增受限 `readonly-query`：verify_record、空executor、不宣称候选或执行交易；
旧execution/rejection先强制非空executor。数据库仅以显式CHECK允许此公共分支为空，
保留旧唯一约束、只追加和外键；迁移不得改写历史行。

授权由独立公共grant明确同快照、固定HTTP `/proof` GET或MCP `/mcp` POST、免费
verify_record、任务配额、并发1、至少1秒间隔、到期/撤销及操作者许可。外网默认关闭。
每次实际HTTP请求都在socket前重新核对授权、当前快照及租约；付款或未知工具副作用
停止后续Agent调用。已发送但响应未保存的崩溃恢复结算UNKNOWN，不重新查询补样本。
Base业务RPC使用同SafeHttpClient的显式业务范围，只增加固定历史tx/receipt及必要区块，
不从元数据或Bundle接受RPC地址、动态代码、交易、签名或写入请求。

公共验证输入保存注册原件、协议请求/响应、完整平台Observation和独立Base RPC的
EvidencePacket。每包重算CAS字节承诺；成功原响应还需保留UTF8原文、SHA256和长度，
重解析后与JSON一致。注册chain/genesis/fixedblock/code/ownerOf/tokenURI及metadata/
OpenAPI重新导出快照和端点关联；不可仅信任已有PASS字段。业务复用normalize_proof/
verify_proof核对canonical receipt、12确认、查询echo及锁定合约事件。确认的业务冲突
为FAIL并保留关键风险，RPC不确定或有限hash搜索未查到为UNKNOWN。

小计划为5槽：HTTP历史正例、一次独立availability重复、未知随机hash、固定非法输入，
以及MCP历史正例。槽位只进入一个purpose的分母，握手/身份/RPC不计业务样本。
原CASE_CLASSES、policy-v1权重和20/10/10门槛不变；缺少类别或样本则PARTIAL、overall=null。
注册、端点、执行者控制和业务判断分别呈现，执行者始终UNKNOWN。

报告冻结与独立Verifier比较实际CAS原件、计划、Observation、原断言和冻结断言，
重新计算统计、充分度、风险及评分；包括外层hash重算后的语义篡改回归。业务证据的Base
与本地报告publication链分开，如需anchor只允许本地Anvil，未请求的不声称上链通过。
离线复核证明承诺和确定性判断一致，不证明采集者诚实或历史HTTP/测量的真实性。
正式阶段验收必须包含实际第三方Worker调用及独立Base核对，MockTransport测试只证明
内部流程和异常处理；不把Mock或旧PoC材料描述为新的真实闭环。
