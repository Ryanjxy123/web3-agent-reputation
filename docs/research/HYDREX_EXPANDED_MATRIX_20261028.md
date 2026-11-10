> 2026-10-28T09:34:29.422970+00:00：根代理在任何新服务请求/付款前冻结此矩阵；执行参数见 runtime/hydrex-expanded-20261028/plan.json，SHA dd76d2ce8ea675ccec28c202265fe48ba1cb0c30ade6356e43197cc942c21aaf。下文草案过程保留为设计依据；冻结定义不随实际结果改变。旧v1回放保留，新来源适配单独版本化。当前官方标价0.01USDC；此前真实请求还含0.01USDC显式额外服务转账，32份按相同实收口径毛费用参考0.64USDC，仍须核实际请求及账本。

# Hydrex 扩量矩阵草案（2026-10-28）

状态：`DRAFT_NOT_FROZEN`。这是待核对、待冻结的业务采样计划，不是已执行记录、评分报告或可直接运行的交易配置。配套文件为 `runtime/hydrex-expanded-20261028/plan-draft.json`。冻结前不据此发起网络请求、支付、签名或资产操作；本草案不要求用户重复批准既有授权。

## 目标与事实基线

以当前 MangoSwap 的 **34 个总任务、8 次真实兑换**作为扩量参照。MangoSwap 的另两次链上履约为创建订单后撤销退款，不能称为另外两次兑换；153 是该对象实际适用的判据数，不是 Hydrex 必须复制的判据数。

Hydrex 已有 H01/H02 两个任务：两次 ZEROX、0.10 USDC→WETH 报价和完整独立模拟，其中 H02 有一次真实兑换。保留原任务 ID、请求、收款人、来源、报告及字节，不重新发起旧任务。此次增加 32 个新任务，形成至少 34 个总任务，计划以 H02 加 H03–H09 达到 8 次真实兑换。实际数量、判据与结果必须来自原件，不预填通过、成交或分数。

官方 `get_quote` 声明为 Base 上查询 ZEROX、OPENOCEAN、OKX、KYBERSWAP，交付输入金额、预期输出、最低到账、路由地址、calldata 和 value。参数 amount 使用最小单位字符串，slippage 默认 50bps，taker 可选；source 在 required 中，却又描述为可省略以查询全部。该矛盾以及未说明的 taker 默认值需核实，不能自行补成声明。

## 执行约束与顺序

新任务链号为 8453，payer 与预定收款人均为现有 SMA `0x73d642847cb9a3acef116ea207a74b9956c34a09`。H17 故意省略 taker，仅核真实默认语义，不臆造请求中的收款人，也不执行收款归属不明的方案。旧 H01/H02 的既有收款人保持原样。

**优先 H03，再尽早 H12。** H03 输入 `400000000000000` raw WETH（0.0004 WETH），正常报价、模拟并真实换成 USDC，以复用已有资产。确认 H03 实际结局及可用 USDC 后，尽早完成 H12 的 1 USDC 报价/模拟，避免后续服务费消耗令本地余额前置条件不足。H12 不动用 1 USDC 本金执行兑换。其余真实兑换使用 `100000` raw USDC 或 `40000000000000` raw WETH，滑点 50bps。

新任务的 UUID 由本地 CSPRNG 生成并保存在 JSON 中，冻结后不得重新生成或复用为另一个请求。服务请求标识、ACP jobId、付款/执行交易及状态分别持久化；未知发送状态先按原标识 reconcile，不盲重发。费用、资金就绪、授权、交易与原始返回逐项追加，禁止发币、铸造身份/报告、创建新身份、提升权限或接受服务返回的任意 RPC。

按官方当前标价，32 个新请求的名义服务费为 `320000` raw USDC（0.32 USDC），这是规划算术，不是已消费金额或固定花费承诺；实际以被接受的费用和真实账本为准。任何本金转入、服务费、建单、授权及网络费均不算被评 Agent 的兑换成交。

## 34 个任务

所有有效 amount 均为整数 raw 字符串。H28 的 `"0.1"` 是故意非法的参数字符串，明确不是资金金额；所有边界任务都不执行资产兑换。

| ID | 层 | 方向与关键参数 | 预定阶段 |
| --- | --- | --- | --- |
| H01 | retained | 原 task `bbc04887-2cac-4e48-b87b-05b63170b188` | 复用报价与模拟 |
| H02 | retained | 原 task `e47c3902-f99e-4bb2-a441-33d34c5d595c` | 复用报价、模拟和真实兑换 |
| H03 | normal | ZEROX，WETH→USDC，`400000000000000` | 报价、模拟、实兑；最高优先 |
| H04 | normal | OPENOCEAN，USDC→WETH，`100000` | 报价、模拟、实兑 |
| H05 | normal | OPENOCEAN，WETH→USDC，`40000000000000` | 报价、模拟、实兑 |
| H06 | normal | OKX，USDC→WETH，`100000` | 报价、模拟、实兑 |
| H07 | normal | OKX，WETH→USDC，`40000000000000` | 报价、模拟、实兑 |
| H08 | normal | KYBERSWAP，USDC→WETH，`100000` | 报价、模拟、实兑 |
| H09 | normal | KYBERSWAP，WETH→USDC，`40000000000000` | 报价、模拟、实兑 |
| H10 | normal | ZEROX，USDC→WETH，`10001` | 小额类报价、模拟 |
| H11 | normal | ZEROX，USDC→WETH，`123456` | 非整金额/6位精度报价、模拟 |
| H12 | normal | ZEROX，USDC→WETH，`1000000` | 较大小额报价、模拟；H03 后尽早 |
| H13 | normal | ZEROX，WETH→USDC，`1000000000000` | 小额类报价、模拟 |
| H14 | normal | ZEROX，WETH→USDC，`12345678901234` | 非整金额/18位精度报价、模拟 |
| H15 | normal | ZEROX，WETH→USDC，`100000000000000` | 较大小额报价、模拟 |
| H16 | default | ZEROX，USDC→WETH，`100000`，省略 slippage | 核默认50bps，报价、模拟 |
| H17 | default | ZEROX，USDC→WETH，`100000`，省略 taker | 核实际默认；归属不明不执行 |
| H18 | default | ZEROX，USDC→WETH，`100000`，slippage=0 | 报价、模拟，不实兑 |
| H19 | default | ZEROX，USDC→WETH，`100000`，slippage=1 | 报价、模拟，不实兑 |
| H20 | default | ZEROX，USDC→WETH，`100000`，slippage=100 | 报价、模拟，不实兑 |
| H21 | source | ZEROX，USDC→WETH，`123456` | 五联比较报价、固定块模拟 |
| H22 | source | OPENOCEAN，其余同 H21 | 五联比较报价、固定块模拟 |
| H23 | source | OKX，其余同 H21 | 五联比较报价、固定块模拟 |
| H24 | source | KYBERSWAP，其余同 H21 | 五联比较报价、固定块模拟 |
| H25 | source | 省略 source，其余同 H21 | 核自动候选与净输出，不实兑 |
| H26 | boundary | amount=`"0"` | 拒绝/安全规范化原件 |
| H27 | boundary | amount=`"-1"` | 拒绝/安全规范化原件 |
| H28 | boundary | amount=`"0.1"`，故意非法 raw 格式 | 拒绝/安全规范化原件 |
| H29 | boundary | 省略 amount | 拒绝/安全规范化原件 |
| H30 | boundary | fromTokenAddress=`"0x1234"` | 拒绝/安全规范化原件 |
| H31 | boundary | source=`"UNSUPPORTED_SOURCE"` | 拒绝/安全规范化原件 |
| H32 | boundary | slippage=-1 | 拒绝/安全规范化原件 |
| H33 | boundary | slippage=10000 | 拒绝/安全规范化原件 |
| H34 | boundary | taker=零地址 | 拒绝/安全规范化原件 |

H26–H34 未列字段均使用 ZEROX、USDC→WETH、amount=`"100000"`、slippage=50 及新任务收款人，只有所列字段发生变化。缺失字段在 JSON 请求中真正省略，不写成 null 或空字符串。

## 案例、声明组与三维映射

所有任务属于同一个通用即时 ERC20 兑换路由能力，不把四个 source 拆成四项能力。沿用 v3 的案例→声明组→能力聚合与 30/40/30，不修改评分公式、旧报告或旧原件。新场景、预期与来源映射在采样前冻结，不能按已看到的结果改权重。新增路由声明组及通用拒单/默认参数来源适配需负责人完成相应 ADR/适配核对后再冻结；本草案没有实现这些改动。

| 层 | A | F 声明组及案例 | B |
| --- | --- | --- | --- |
| normal | 按 USDC→WETH、WETH→USDC 各一个完整响应案例 | `intent-binding`：方向、地址、raw金额、收款、滑点与交付字段；`execution-effect`：同方向固定块完整效果；`routing-selection`：按四个 source 各一个过滤遵从案例 | 8个 source×方向正常案例，各至少1个可判真实履约；H02 为 ZEROX 正向既有目标 |
| default | 一个参数/默认业务响应案例，不增加能力权重 | `intent-binding`：省略滑点、省略taker、显式滑点参数分别核；`execution-effect`：实际可绑定方案的完整模拟 | 不适用，不填100 |
| source | 一个五联比较业务响应案例 | `routing-selection`：四source遵从复用原source案例；新增一个 all-source 净输出选择案例；意图/效果原件并入相应方向案例，不重复计同任务/同维/同判据 | 不适用，不填100 |
| boundary | 记录响应、时延和原因，不混入正常报价 A 分母；官方未声明错误输入SLA | `intent-binding`：amount、地址/收款、滑点三个验证案例；`routing-selection`：非法source验证案例。同类边界只增加该案例观测，不增加声明组权重 | 不适用；安全拒绝不冒充成交 |

JSON 中 `cases` 固定案例 ID、声明组、判据和预定任务；`metric_definitions` 规定客观预期，任务的 `case_expectations` 引用这些定义。旧任务只引用原 ID/source，`retained_case_assignments` 描述新报告如何回放既有原件，不提供手工 PASS 或替换旧结果。

每案例对有效可判证据计算 `100P/(P+V)`；UNKNOWN、未采、无效和不适用独立记录，不补0或100。F 先组内案例等权，再声明组等权；A/B 按预定案例等权，能力层继续等权。综合为 `0.30A+0.40F+0.30B`，按现有规则保留两位小数。B 的预定正常案例及可判门槛保持，不因保护退出或样本不足临时放宽。

## 判定与证据约束

A 采用官方正常任务5分钟SLA：要求及费用均就绪后至真实完整交付，ACP链事件和规范块绑定计时。操作者等待付款、轮询或延迟核验不计 Agent 故障。完整业务拒绝不等于 HTTP 500；错误输入未承诺的SLA不由平台臆造。

F 核原请求、原交付、实际calldata与资产效果。至少检查六个必需交付字段、amountIn与calldata一致、ERC20 value=0、精确输入、输出资产、可归属收款人、最低到账、授权及余授权、费用和最早有效期限。source 应结合实际内部路由及可核部署归属核验，不能只信返回的标签。未知协议或来源缺口为未适配/UNKNOWN，真实认证交付违反已明确约束才记FAIL。

H10/H13 等小额或极低滑点请求可能遇到合法流动性、市场保护或上游拒绝。没有明确服务承诺或可归责证据时保留 UNKNOWN/保护退出及原因；不能将没有方案自动扣分，也不能将保护退出当成正常效果通过。H17 没有声明默认收款人；观测事实可以记录，缺语义不能强行判对错。边界任务只在客观证明符合已冻结安全约束时判通过，安全规范化必须显式、可核且不扩大资产权限；含糊响应不填PASS。

H21–H25 使用相同方向、amount、taker及50bps，保存每份报价的真实有效窗口，寻找共同有效固定块并对全部可用候选进行完整效果模拟，比较扣除已披露协议/推荐费用的净输出。明确不可用候选保留拒绝原件，不能静默删除；候选范围不明、窗口不重叠、无法绑定费用或缺独立模拟时，最优价保持UNKNOWN。只证明已核四源候选集合内的选择，不称全市场最优；不事后增加任意价格容差来得到通过。

B 必须绑定链实例、任务/ACP交付、买方执行者、原方案、目标与事件发出地址、最早截止、交易回执、输入净减少、指定收款人输出净增加、最低到账、费用、余授权0及预定确认要求。预定执行任务未实际兑换时保留该槽位；合法保护退出不替代正常履约。一笔实际兑换只能归属一个真实任务，不用服务费、建单、模拟、授权或资产归集补B。

如果某路没有有效方案或无法安全核验，保留真实拒绝/失败/UNKNOWN并停止依赖的资产执行。H02–H09未完成8次兑换时，不删除原失败、不默换ZEROX、不降低门槛；先记录缺口，再为有价值的新正常案例追加冻结计划，总任务可超过34。最终说明实际完成数及范围，不能预称已达样本量。

## 冻结与验收清单

冻结前核对共享类型/适配器对拒单、缺省参数和多场景的支持，确认8个正常B目标及资金/费用前置条件；记录本草案原字节、冻结时间和哈希。H03→H12为资金相关前缀，H21–H25另作共同窗口比较组，不为凑时窗重播既有金融任务。

采样后保存所有正常、拒绝、失败和未知原件，追加新报告，复算34个任务和真实兑换数；不要求判据数等于153。运行必要的受影响正常/失败/未适配重放及真实PostgreSQL导入验证，记录真实命令、退出码和限制。草案阶段仅做本地结构/一致性核对，不把此核对写成工程、集成、外部服务或链上通过。

## 原件与规则

- `runtime/candidate-review-20261028-acp/hydrex-detail.response.bin`：官方接口、5分钟SLA、标价和字段说明。
- `runtime/unsigned-swap-public-20261028/hydrex-source-v2.json`：既有两任务及其真实原件引用。
- `runtime/hydrex-routing-shared-20261028-v6/report.json`：现有2任务/7判据报告。
- `runtime/mangoswap-single-score-20261027-v1/report.json`：34任务、8兑换、2撤销退款及153判据基线。
- `data/public-reports-transaction-v3.tar.gz`：已发布两个对象及其必要原件。
- `docs/adr/0029-single-score-and-report-scope.md`、`docs/adr/0030-unsigned-swap-source-replay.md`、`packages/core/src/reputation_core/point_scoring.py`：沿用的单分与来源重放边界。

当前原件适配器强制有效submitted/quote及显式taker/slippage，尚不能直接支持本草案全部拒单、默认参数和source判据；草案不把缺适配算成服务失败。负责人负责代码/ADR/状态更新及实际冻结；本文件仅为待冻结矩阵。
