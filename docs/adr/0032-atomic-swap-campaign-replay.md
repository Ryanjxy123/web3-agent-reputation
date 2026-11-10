# ADR-0032：原子CALL序列的前瞻证据报告

状态：本轮新适配范围；发布首份报告前固定本文件。沿用ADR-0029的transaction-agent-evidence-v3、shared-task-assessment-v3和30/40/30，不修改评分、共享Schema、旧报告或旧unsigned来源分派。

## 问题与决定

公开交易服务可能返回由买方执行的完整多CALL序列，而不是单个Router调用。一次经济任务可以连续请求quote/build，并复用同一任务的A/F/B原件。把两次HTTP算成两个样本、把成功模拟或服务费当成交、或仅验证SWEEP阈值而忽略Router旧余额都会产生虚假的覆盖或履约结论。

新增隔离来源`atomic-swap-evidence-v1`、adapter `retained-atomic-swap-campaign-v1`和origin `atomic-swap-report-origin-v1`。仅实现已核Universal Router Slipstream方言的ERC20七CALL原子协议；不按Agent名称、域名、登记ID、当前样本数或预期分数分支。HTTP字段、calls入口和可选quote字段以冻结JSON-pointer配置接入，评分语义仍是通用业务与协议约束。未知合法形状是未适配，不因此扣Agent分；已适配ABI中明确违反独立参数或授权清理的交付保留FAIL。

注册证明重用真实ERC-8004 ownerOf/tokenURI原件校验与冻结服务声明；registry owner与买方执行钱包是不同角色。tokenURI须绑定确切registered_service，HTTP业务地址须属于该有来源的HTTPS origin；同名服务或钱包标签不能拼接身份。

FROZEN计划必须先于本次HTTP观测，保存每task UUIDv4、精确分阶段请求、独立规范化资产/数量/收款/滑点/目标、声明分组、case成员、criterion与required_decisive。quote/build同task仅计1。未采task仍在冻结分母；不以补齐全部声明作为所选范围出分门槛。禁止在采样后变更case分组或删去失败槽位。首版只接独立不可改计划；追加新任务应另建、冻结新版来源和报告，不覆盖已发布输入。

## 三维与证据

- A核正常业务各HTTP阶段完整成功。观测仅说明传输、正文及业务交付；无公开SLA时耗时仅展示，不用默认1秒/10秒阈值扣分。缺响应/客户端未完成与明确HTTP业务失败分开。预定无效输入的4xx不加入正常A案例。
- F核原始quote与build各阶段的资产、数量、链、最低值、冻结滑点及完整CALL。独立意图不能由前端给分替代。缺省值按有来源规范及真实字段/内部TTL核对；缺证明保留UNKNOWN。安全拒绝须输入确实违反有来源schema或明确业务约束、取得完整400/422错误且无可执行方案；404、500、上游错误或未适配不是安全通过。
- F净效果在固定块执行精确16CALL：用户input/output及Router output余额3读→原7CALL→同3余额读→3授权读。禁止state/block override。执行者、链、部署运行代码承诺、CLFactory/clone实现和池资产/tickSpacing必须有同块可信RPC。SWEEP只检查Router余额，故独立净效果扣除旧Router输出余额，不借旧余额补minimum。缺部署/池来源、回滚未定因、旧余额污染均不伪造PASS或统一扣分。
- B仅给预先安排的正常实兑目标。持久化发送意图须绑定原build响应SHA、16CALL计划SHA、模拟计划SHA、固定块/hash、执行者/链/nonce及完整tx input；交易、canonical receipt、事件发出地址、输入/输出净Transfer、前后余额、精确spender三类授权0及至少64块确认距离同时成立才通过。手续费、模拟、保护退出均不能补B；单兑换交易hash不得跨task复用。回滚未定因不自动标重大违约。

协议部署承诺来自操作者审查官方验证源码/构造参数后的前瞻固定配置，不接受Agent元数据提供RPC或把返回Router地址自升为可信。只读记录URL仍由既有操作者白名单校验。没有自动声称完成编译/bytecode同源认证；缺少必要原件应保留UNKNOWN。

含PREPARATION状态或router、Permit2、CL factory、CL implementation、executor任一空运行代码承诺的绑定不能进入FROZEN报告。池地址除可信固定块getPool、token0/token1/tickSpacing和ERC1167运行代码外，还须匹配该已核实现的CREATE2公式；静态预测不代替真实RPC查询。准备文件保存为独立原件，负责人另存审查完成的绑定并以path/SHA前瞻引用。

## 兼容、迁移与不变性

旧unsigned-v1/v2、SharedAssessment、profile和chain view模块保持不动；负责人后续以新origin显式接分派，不回填旧结果。新来源在新runtime目录构建report/manifest/origin，原件和已发布产物只追加。软件provenance复制为artifact内不可执行的文本快照并hash，manifest不直接依赖仍会变化的live services/*.py；快照不会被动态导入或作为远程代码执行。ADR-0032首发后保持原字节，后续政策/协议变化使用新ADR及版本。

输入篡改、错误身份/冻结时序、实际HTTP与请求不符、错误tx/actor/call序列/hash属于来源完整性拒绝；真实不符与缺原件/平台未适配分别判。正常样本和受控工程负控分别统计，单项离线单元验收不冒充公共实兑、链集成或PostgreSQL验收。

首份Atomic报告发布前补充错误解析：优先使用冻结错误pointer；缺失时只接受明确typed error envelope（kind=error、data=null、summary字符串）或标准JSON-RPC error.message。普通成功响应中的summary不能被当错误。400/422还须独立证明冻结输入非法，并使原因对应非法字段或其原值；仅一个amount字段非法时允许正数/uint160等通用Amount措辞。不匹配的400保留UNKNOWN；不改冻结请求/mapping，不重发真实样本。amount正数约束核实际请求值，不能误用正常意图的占位规范化数量。费用、路径与部署规则保持。

公开类型依据为冻结OpenAPI原件 `runtime/candidate-expansion-goal-20261028-direct/phase1/topaz-openapi.response.bin`（SHA256 `a97122624efe4f4d75d4f23a8395cc48667b63942cbc393d80c238d16296b863`）的 `/components/schemas/ErrorResponse`，quote 400明确引用该类型；kind枚举error、summary为human-readable error message。实际data=null条件比该公开schema更窄。该来源只解释通用输入形状，不引入域名/Agent身份判断。

首发前补充输入校验负例归因：独立证明非法的原请求，若冻结route承诺400/422的ErrorResponse，而绑定origin实际返回完整同类型（kind=error、summary字符串、data=null）HTTP5xx，则F safe-rejection为FAIL，事实仅是输入校验错误契约不符，不认定资金违约或内部根因。冻结OpenAPI必须对该route明确引用此错误类型；无关上游HTML、网络中断、403或未适配形状仍UNKNOWN。真实A38的0xzz原件支持该负例，不修改阈值、原A33/A34 UNKNOWN或任何冻结请求；正文的重试措辞不会触发动作。

## 显式接入、导出与追加计划

新atomic origin在通用shared来源核验入口优先分派，Repository沿原有manifest/来源核验边界导入；资料页从有hash的计划、身份与服务范围产生，不按对象名称分支。链视图解码完整16CALL，展示同一交易中的查询、精确授权、Router执行与清理；只有真实receipt的净资产转移可称兑换。纯quote/build的task outcome保持not_executed，避免误标已成交。

公开source导出只读取明确计划、HTTP映射和任务执行目录中的公开source-item，按原观测时间选择最新取证版本，不按分数选样。签名、SIGN/SEND、auth、原始广播文件和链接路径禁止进入来源；缺失阶段省略，重放保留UNKNOWN。source草稿及ledger不是已发布报告。后续软件provenance仍只写artifact内不可执行文本快照。

追加冻结版本以previous_plan的path/SHA形成只追加链：原task字典不可变，旧case成员只追加，规则与required_decisive保持。每task使用首次引入版本的frozen_at；不能拿新冻结时钟否定合法旧原件，也不能将补采响应贴到旧UUID。平台传输中断的旧任务/UNKNOWN仍保留，补采使用新UUID和明示原因；调度active目标与评分槽位分开。Shared核心任务槽位数不变，展示层及导出ledger另列已采任务，防止未采计划增加真实任务计数。v2/v3均保留原分组及30/40/30；没有降低门槛。

point-scoring的A/F required_decisive是覆盖目标，少于目标不会自行硬阻断A/F或总分；正常B案例才有可判数量门禁。A37/A38是不同输入表示的覆盖扩展及真实错误处理负例，不能描述成“补采才能解锁F总分”；旧UNKNOWN、原覆盖记录及所有阈值保持。

## 定向接入验收

一次定向验收覆盖真实七CALL格式及受控源下完整报告重放、2HTTP=1task、未采槽位、A不臆造SLA、真实不符/未适配/缺B分类、旧Router余额污染、三授权与64块确认、来源篡改/重复tx拒绝，以及artifact内软件快照。工程夹具明确为受控单元数据，不作为新公开业务样本；本阶段不新发网络或资金操作，不重跑旧suite。
