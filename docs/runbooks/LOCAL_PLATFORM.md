# 本机平台启动与实际验收

日期：2026-10-18。工作目录：`D:/xjtu_project/block_chain_new/block_chain_new_new`。

Vue 网站、FastAPI、独立 worker 与 PostgreSQL 已实现。本轮收口的真实PG快照为38候选、35份报告、7个不同完整评分对象、0活动任务；最新结果以[STATUS.md](../../STATUS.md)为准。已适配专项可复用保留证据；没有预置 profile 的规范身份也可自动发现注册资料、协议接口及适用的Mech历史履约任务，按实际覆盖生成报告。历史采集与离线核验用法见 [MODEL_EVIDENCE_LOOP.md](MODEL_EVIDENCE_LOOP.md)。

## 日常启动

本机依赖、前端构建和数据库连接文件已准备好，运营 profile 为可选配置。普通用户不用填写 RPC、模型密钥或数据库信息，在项目根目录运行：

```powershell
.\scripts\start_local_platform.ps1
```

该命令启动并核实本项目 PostgreSQL，启动本机 API，检查数据库健康后运行前台 worker。默认 **public-off**：已有目录与报告可浏览；新提交的规范身份返回 `NEEDS_INFO`，明确说明未启用公开采集，不请求外部服务、不产生新分数。

本次已获授权的免费公共只读评价使用：

```powershell
.\scripts\start_local_platform.ps1 -EnablePublicReadOnly -Proxy 'http://127.0.0.1:7897'
```

打开 [http://127.0.0.1:7754/](http://127.0.0.1:7754/)。网站与 API 同源，直接使用已有 `apps/web/dist`，无需额外运行 Vite。页面提供浏览和接入两个入口；提交后直接排队，只有活跃任务自动读取进度，成功后打开报告。

`-Once` 仅供单任务或启动验收：worker 至多处理一个待处理任务，队列为空时立即退出，启动器随后停止它创建的 API。日常使用保持启动器运行，不加 `-Once`。退出启动器会停止其创建的 API；PostgreSQL 保留运行，可单独停止：

```powershell
.\scripts\stop_local_postgres.ps1
```

只管理数据库时使用 `.\scripts\start_local_postgres.ps1` 与上述停止脚本；数据与现有凭证保留。

## 本机实例与运营配置

| 项目 | 当前实际配置 |
| --- | --- |
| PostgreSQL | 17.11，`127.0.0.1:55438`，库/角色均为 `reputation` |
| 数据目录 | `runtime/platform-postgres`，与旧项目分离 |
| PostgreSQL 工具 | `D:/web3-runtime/tools/postgresql-17.11/pgsql/bin` |
| 当前API与生产静态网页 | `127.0.0.1:7754`，与启动脚本默认一致 |
| API/worker 连接配置 | `runtime/platform-config/database-url.txt`，可由运营者环境变量覆盖，不进入公开接口 |
| 运营 profile（可选） | `runtime/platform-config/profiles.json`，引用已有专项身份、政策与保留证据目录；缺省时仍可运行通用接入 |
| 启动日志 / 任务原件 | `runtime/platform-logs` / `runtime/worker-jobs` |

API 首次尝试绑定 8015 时，Windows 返回 `Errno 13`。随后一次原生 `socket.bind(127.0.0.1, 0)` 诊断由系统分配到可用的 7754，API 已在该端口真实启动；没有修改防火墙。当前API、启动脚本与开发代理均为7754。当前服务已在运行时直接访问网页，无需重复启动。Vite 的 5175 仅保留为开发配置，尚未完成该端口的真实启动验收。

profile 属于可选运营配置，本机已保留首个历史增仓特例和两个预测历史实例。匹配这些配置时，worker 新采 10 点可用性，再复用保留的历史交易、状态与上下文独立核验，生成新版本；复评不调用模型、不触发资产操作。

开启公共只读后，没有预置 profile 的规范身份走通用路径：核对目录身份、使用操作者可信 RPC 在固定区块读取注册信息，再从登记文档发现服务和协议资料。已适配的 MCP 发现接口可安排独立可用性采样；取得工具列表或 Schema 只说明已发现声明，不代表业务完成或交易履约通过。缺少业务、独立判据或交易证据时，报告分别列出缺项，不计算完整综合分。若目录与链上两类来源均没有取得有效身份依据，则以 `NEEDS_INFO` 结束并保留采集记录；无法识别的输入返回 `UNSUPPORTED`。

适用的Gnosis Mech可自动复用或只读采集公开历史，冻结七个不同履约B槽，重验请求/交付交易、历史执行控制、任务标识及CID/CAR文件。原件不足保留缺项；按需新评价可只补同七槽缺项，不重读已成功项、不换槽、不创建新业务任务或自动重试。来源清单和原件只追加，规则见 [ADR-0011](../adr/0011-shared-task-delivery-evidence.md)与[ADR-0012](../adr/0012-resume-frozen-task-evidence.md)。通用业务正确性F尚未接入，B通过不代替F；下述自动预测另用独立政策，已可形成其限定范围的三维分。

预测历史的 worker 已完成两个真实对象的正式闭环：2198 综合89.72，2235 综合98.71，分别使用同一代码与各自原件。运营 profile 使用 `policy_id=prediction-history-v1`、`history_run`、`plan_run`，可另给 `identity_run` 身份补充和 `translation_run` 已保存中文材料；这些都是本机保留目录，普通用户不填写。实际命令、真实任务和报告号见 [PREDICTION_REUSE](PREDICTION_REUSE.md)。该轮完成时主库为33候选、3个不同完整评分对象、4份报告；此处是历史验收记录，当前统计见 STATUS。

该路径先核对自动选出的方案、固定十四个不同市场的7+7分组、真实交付事件中的内容摘要及原始文件/CAR。历史cohort不足或已固定交付缺原件时，以 `NEEDS_INFO` 结束且不发新采样；资料具备后才新采十次公开历史文件访问，再离线生成本次报告。复评不会重新收集历史、发起新预测或调用翻译模型。

作业 `COMPLETE` 表示该轮处理和报告发布结束，报告是否取得完整分数以报告自身 `scores.status` 为准。新采样或独立核验不足时可发布 `PARTIAL` 报告，作业消息明确说明没有完整三维分及综合分；不把流程结束冒充完整评分。每轮仍由数据库租约与fencing token约束续租和发布，历史版本保留。

## 当前无需profile的预测自动接入与本轮收口

当前更新：预测V2已实际增加2267完整29.8，总计8个不同完整对象；2135/2150在UTC14:17按ADR0017启动共用直接原题批次。新自动接入仍只接受已核Fixed Native/Omen/IPFS；根File或Directory均按CID验证，完整原题只作精确且唯一的定位，最终独立核结算与提前交付。V2要求14个不同Question；旧V1与原报告保留。输出修订3按实际Schema和链上任务关联，报告显示真实错误返回，不额外要求内部prompt回显原题。API端口7754，当前worker进程记录 `runtime/v2-workers-20261018T141657Z/processes.json`。下文7对象及35报告为此前收口的历史记录，当前以STATUS及最新批次为准。

普通用户只提交完整canonical或注册页面，平台核实登记、工具声明和协议后自动执行；不填profile、不选方案、不二次确认。支持保留的prediction-history-v1与显式V2；14个不同已结算问题互斥7F/7B及10次A，不降门槛或按结果换槽。当前仅已核Fixed Price Native与Omen/IPFS，订阅2469未适配，不承诺任意登记对象完整出分。

预测证据扩展按ADR-0016/0017执行；已发布结果及当前批次以STATUS开头为准。 既有prediction-history-v1的三维、30/40/30、固定历史计划与原件继续保留；取得足够可核证据才发布新分数。

| 对象 | 最新报告 | A / F / B | 综合分 |
| --- | --- | --- | ---: |
| 2340 | `c7eb4285-bd1a-456d-9a1e-34606e067b15` | 98.51 / 79.33 / 100 | 91.28 |
| 2182 | `1e7732c5-3a24-4582-9ca0-b0f4deedd1dd` | 98.33 / 77.64 / 100 | 90.56 |
| 2360 | `63b17e17-3260-48f8-b258-67bdd68abf94` | 98.33 / 72.79 / 100 | 88.62 |
| 4110（service3786） | `6b4a1a7b-278b-48f0-88e8-980edc86129f` | 89.69 / 53.89 / 100 | 78.46 |

4110旧PARTIAL仅缺登记日期：目录GET为TransportError，并非字段解析漏掉。仅补1次确切GET及3次必要RPC，在旧profile/固定N核唯一mint与有序ServiceAgentLinked，登记块47694994、UTC2026-08-12T23:45:35+00:00。共用helper依[ADR-0015](../adr/0015-registration-date-supplement.md)绑定旧history manifest/bundle，补录源 `runtime/prediction-registration-supplement-20261018T130654Z-671d83aa/`；原14任务与10A未重采，旧PARTIAL保留。新报告 `runtime/evaluation-report-20261018T130748Z-45152bd3/amendment-result.json` 真实PG发布exit0。两项补录负控产物显示拒绝，但原执行exit未回收；仅后续只读产物检查exit0，不冒称原命令exit0。

长验证租约验收 `runtime/publication-lease-check-20261018T124836Z-c445e119/result.json` exit0：真实PG验证107.05秒（含65秒本地延迟，用于验证续约），第66秒竞争者claim为None、fence未变，旧token拒绝。此前重复A采样中断记录保留，不声称恰好一次；这次恢复0新A/网络/模型。后续登记补录才使4110由PARTIAL变为完整78.46。

2340原83.01由ADR-0014 revision2更正为91.28，旧报告及revision1复算保留，原14任务/10A/翻译零重采。逐功能展示2340（`runtime/evaluation-report-20261018T123417Z-556b41e4/`）、2182（`runtime/evaluation-report-20261018T130123Z-25aa1c20/`）、2360（`runtime/evaluation-report-20261018T130228Z-14e08e63/`）均4工具/14真实关联、分数不变，刷新脚本exit0。2340展示验收先因双origin exit1未入库，修正后exit0；三个0资格说明同源同分与错误correction SHA拒绝exit0。前端最终受影响pnpm build exit0，明确计划槽位不等于实际测得，无core/API Schema改变；视觉仍BLOCKED。

七对象批次的2135/2150/2267各0合格，2359仅6个，保留缺项而不降14门槛；4134共用null CID解析已修，但实际inline JSON129/174字节无Omen context，不为其新建类或重跑，说明报告 `e34a935a-13de-4608-a4ee-dcd51889ab2c` 位于 `runtime/generic-report-format-gap-20261018T125256Z-f7e7d0b1/`。

后续四对象批次 `runtime/prediction-auto-batch-20261018T125324Z-96bd00cd/qualification-summary.json` 已结束0full：1722的38条为36输入404+2无market_id；2266的14条全404；2673的29条为22输入404+6不支持工具+1无market_id；2699的2条为1ReadTimeout+1不支持工具。driver exit2/PowerShell exit1，2699超时是平台读取不确定，不是逻辑bug。初筛和正式有限资格都保留原件，不能据此猜市场、改cutoff或为股票/inline开新类。见[有限扩量调查](../../reference/PREDICTION_EXPANSION_DISCOVERY_20261018.md)。

预测证据扩展按ADR-0016/0017执行；已发布结果及当前批次以STATUS开头为准。 先确认可测覆盖再写生产代码，订阅、付费Agent与资产操作仍不在本轮授权内。

本轮最终只读收口 `runtime/prediction-batch-close-20261018T131251Z-ef4125f5/result.json` 实际exit0：38候选/35报告/7完整/0active；4110报告API200、补录附件200且原件字节SHA一致，网页与当前新JS200，新外网/模型0。浏览器视觉仍BLOCKED。API7754与重启后最新代码的一个worker保持运行，两个额外批量worker已停，旧三worker已替换为一；这次收口不新增采样或任务。

## 历史通用接入验证

首次基线验收通过真实 API 提交三个没有预置 profile 的身份：Base #45074、BSC #49467、Gnosis #2340。三者均完成链上注册核验并保存报告，实际结果见 [通用接入验证原件](../../runtime/generic-platform-check-20261018T093143Z-c316e720/result.json)。当时三份报告的可用性、功能、交易样本均为 **0**，`scores.status=NOT_EVALUATED`；原报告保留，后续2340履约报告另列下文。

随后仅对新增MCP描述文件远端发现格式做了一次受影响的Clicks复评：作业 `c891dc87-f630-48d9-aa1e-33e0cc08996e` 正式发布报告 `5b7a2b70-4fe5-47cc-8396-dee2bf5bcdf7`。真实发现4个工具；发现接口10次新访问为9PASS/1UNKNOWN，p95为10,734ms，可用性80。功能和交易无任务样本，报告PARTIAL、无综合分。见[结果与必要失败控制](../../runtime/generic-descriptor-check-20261018T093900Z-0e4c7f79/result.json)及[详细报告](../../runtime/generic-evaluation-20261018T093902Z-e866bab9/report.html)。复用原件完成错误身份与伪造判分拒绝、私有附件404、网页和当前JS200，未再次发起Agent采样；辅助脚本先前的computed字段读取错误及exit1也保留在结果中。

共用Mech履约规则已离线重验两个旧对象的原七个行为槽：2198覆盖2种工具、2235覆盖3种，合计4种；两者B均为100、无综合分，本次不发布新报告。原件重派生及错误身份/伪造行为判分拒绝退出 **0**，新增公开请求 **0**，见[两对象履约核验](../../runtime/mech-task-check-20261018T105653Z-850f26e7/result.json)。

无预置profile的Gnosis #2340经真实API任务 `b08ad952-11e2-4069-acbf-eeba41358666` 自动采集并发布 `50066371-ef1a-4210-91be-3ec833fe9381`：原七槽6 PASS，1个文件ConnectError，B无分、PARTIAL。新评价 `9b83f0d5-e783-4724-9eae-2e901cd6e4dc` 只补同七槽缺项，新增4次公开读取；入库复核因多注册proof、父来源引用集合不一致而FAILED。修正后复用同份原件完成离线复核、真实PostgreSQL导入和API GET200，两份计划附件与原文件一致，命令退出 **0**，恢复阶段新增公开请求 **0**。

正式新报告为 `72bbfff4-27bb-4f7b-afd1-8302bf03ee60`：**B七PASS、100分；A/F无分，综合分为空，PARTIAL**。见[补证与恢复结果](../../runtime/mech-task-platform-check-20261018T111813Z-cfc50af6/result.json)及[详细报告](../../runtime/generic-evaluation-20261018T111817Z-0415f9eb/report.html)。旧报告、FAILED作业、源清单和原七槽均保留，未重复已成功六项。该履约轮完成时为34候选、3个不同完整评分对象、10份报告；B报告本身不增加完整对象数量。其后自动预测已增至7个，当前统计见本文开头。

本轮复用已有核心、网络及前端构建验证，没有重跑旧测试或构建。API保持本机7754运行，浏览器视觉与DOM交互验收仍为 **BLOCKED**，无远程配置或推送。其后用户已批准 `PREDICTION_AUTO_ATTACH` 优先复用既有预测判据，本轮结果与下一优先级问题见上一节。

## 安装、构建与历史首次导入

本轮 uv 锁定/依赖安装、前端独立 pnpm 锁定安装与首次构建均已真实退出 0。Python 使用项目 `.venv`，前端实际使用 Node 22.17.0、pnpm 11.25.0；精确依赖见 [前端说明](../../apps/web/README.md)。新机器安装入口为：

```powershell
uv sync --locked
```

然后在 `apps/web` 运行 `pnpm install --frozen-lockfile`、`pnpm run build`。当前本机日常启动可复用已有安装和构建。

运营者在取得真实证据后初始化并导入；以下是当前本机已存在的输入，不是 clone 自动附带的演示数据：

```powershell
.venv/Scripts/python.exe scripts/import_local_report.py `
  runtime/evaluation-report-20261018T053613Z-fe5237bc `
  --initialize --candidates runtime/admission-report-20261017T182038Z-f504c54e
```

首次历史导入包含 **5 个候选**，首份报告 ID 为 `251eb31d-973d-4cb1-ba4a-4a735d652ec7`，综合分 **96.67**；三维为 88.89 / 100 / 100，限于报告列明的历史增仓范围。本机已有记录，不需在每次启动时重复导入。

后续离线补记将 Custos、Olas、delu 和 Clicks 的六项事实/缺项整理为新准入快照，没有产生声誉分：

```powershell
.venv/Scripts/python.exe scripts/build_expansion_admission.py configs/candidate-reviews-20261018.json
.venv/Scripts/python.exe scripts/import_local_report.py --candidates runtime/admission-report-20261018T063130Z-e7ee947b
```

两条实际命令均退出 **0**，前者复用 31 条观测、无外网调用，后者导入 4 个新对象。当次主库核对为 **9 个候选 / 1 个完整评分对象 / 同一对象 2 份报告**；原件目录中另存 database-import-receipt.json。这是历史快照，网站能直接查看这些对象的未决资料与下一步。该日期配置已作为快照输入冻结，后续变化另建版本，不改写已引用原件。

`runtime` 中的公共采集原件、数据库和私有 profile 均被忽略，不入 Git。新 clone 没有这些采集证据，不能凭空生成上述 seed 报告。专项历史评分应按采集运行手册取得真实原件、生成报告，再由运营者导入并配置对应 profile；通用接入不要求预置 profile，普通网站用户只提交注册资料。

## 历史首次平台验证

实际页面/API 读请求保存于 `runtime/local-platform-check-20261018T055831Z-95665164`。`checks.json` 记录以下 5 个真实 HTTP 入口均为 **200**：

- `/`：生产构建网页。
- `/api/health`：API 与 PostgreSQL 就绪。
- `/api/agents`：5 个候选的真实目录。
- `/api/agents/brain-defi`：对象详情与历史报告。
- `/api/reports/251eb31d-973d-4cb1-ba4a-4a735d652ec7`：已导入的详细报告。

响应原件已保留，中文按 UTF-8 正确读取。HTTP 读取成功与浏览器 DOM 交互验收分开记录。

独立库 `reputation_verification` 的集成用例首次仅因 `pg_hba.conf` 未允许该库连接而失败。专门增加限定到该库、角色 `reputation`、`127.0.0.1/32` 的 SCRAM 规则并 reload 后，只重跑该受影响用例：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_local_platform.py -v
```

1 个用例 PASS，退出 **0**，使用私有 `REPUTATION_TEST_DATABASE_URL_FILE` 指向独立验收库。实际覆盖 3 个并发领取者仅一个获得任务、租约过期后旧 fencing token 无法续租或提交、报告 UPDATE/DELETE 追加写保护，以及正常和错误 API、证据摘要与下载归属。没有使用 SQLite 或内存数据库替代 PostgreSQL；已有有效结果直接复用。

后续静态复核发现同一内部 key 可被另一完整注册身份覆盖，已用原子 upsert 条件拒绝冲突，保留短线索首次补齐和规范等价写法。仅新增并执行这一关键回归：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_local_platform.py -k test_registration_identity_cannot_be_rebound -v
```

真实独立 PG 用例 PASS、退出 **0**：补齐身份、等价写法、候选冲突拒绝及事务后内容不变。等价输入的测试样例修正后只重跑该新用例，最终 1.010s；此前集成用例未重跑，主库真实报告未修改。

共享 API DTO、Schema 与 TS 从 core 类型生成。`.venv/Scripts/python.exe scripts/export_api_contracts.py` 已退出 **0**，导出实际 FastAPI 路由的 `services/platform/generated/openapi.json`，共享字段统一由类型维护。

前端首次 `pnpm run build`（`vue-tsc` + Vite）PASS、退出 0；随后真实集成审查发现示例按钮误选旧短注册线索、身份标签不准确，修正必要 Vue 源并改善结论说明后，仅重新构建受影响前端一次，同样 PASS、退出 0。开发代理 8015→7754 的配置调整未触发重建。

后续只读审查进一步修复三个实际使用问题：未评分对象的旧短注册线索不再自动填入表单，任务原因以服务返回的明确 `message` 展示，已评分报告的 `runtime` 原件链接接入现有受控证据附件下载 API。候选没有报告上下文的本机路径仍为文本，HTTPS 来源链接保留；原件入口只在折叠技术区中出现。因这些 Vue 源实际变化，再仅执行受影响的 `pnpm run build` 一次，类型检查与构建 PASS、退出 **0**，生成 `dist/assets/index-DA0fC7Eh.js`，CSS 未变化。没有启动服务或重跑其他测试。

上述重建均对应真实源代码问题修复，没有为提交重复测试。浏览器视觉仍 **BLOCKED**，未重复 Chrome 崩溃尝试，未声称已完成浏览器交互 DOM 验收。

## 历史首个专项提交与验收

主库真实 POST `/api/evaluations` 返回 **202**，任务为 `88a22786-55ec-462e-a7e7-d440f215587c`，原始 QUEUED 响应保存于上述检查目录的 `submitted-job.json`。任务从 2026-10-18 **13:58:35+08:00** 提交至 **14:03:45+08:00** 完成，自动经历 QUEUED、RUNNING 与采集/核验/保存报告，最终为 **COMPLETE**。

本次新报告 ID 为 `568a411d-2548-48ed-8df7-1dd7840a903f`，原件位于 `runtime/evaluation-report-20261018T060340Z-4c27cea3`，实际结果如下：

| 维度 | 本次得分 | 实际样本 |
| --- | ---: | --- |
| 服务可用性 | 93.09 | 10 PASS，成功响应 p95 4109 毫秒 |
| 功能声明一致性 | 100.00 | 7 PASS |
| 交易行为可靠性 | 100.00 | 7 PASS |
| 综合分 | **97.93** | 状态 `COMPLETE` |

这是同一个 Agent 的第二次报告：重新执行本次可用性采样，复用保留的历史任务证据并重新独立核验，产生新的时间与报告版本。新可用性耗时使分数发生实际变化；历史业务样本没有因复评重新触发主网操作。第二份报告不增加真实对象数量，首份 96.67 分报告继续保留。

**静态资源、报告时序与实际启动器验收：PASS。** `runtime/complete_local_acceptance.py` 已改用带时区的日期时间解析，复用已完成结果执行后退出 **0**；没有重复采样。`worker-and-assets-checks.json` 确认新报告生成晚于提交（`generated_after_submission=true`），对象历史报告数为 2；实际静态资源结果为：

| 资源 | HTTP | 类型 |
| --- | --- | --- |
| `/assets/index-UpdWLm_I.js` | 200 | `application/javascript` |
| `/assets/index-Bi-5aUVn.css` | 200 | `text/css; charset=utf-8` |

该次 HTTP 验收对应当时构建的版本；后续三处前端使用问题修复产生的新 JS 本轮仅完成构建验证，结果见上一节。

停止此前自己启动的手动 API 后，实际执行 `.\scripts\start_local_platform.ps1 -Once`，退出 **0**：复用 PostgreSQL、通过 API 7754 的数据库健康检查，再领取 DegenAI 的规范注册输入任务 `94fa5a31-0a6e-4e44-a126-0d4a7d52927d`，终态 **NEEDS_INFO / DONE**，未产生报告，公共请求数为 0。

随后通过仓库读取与 socket 检查确认启动器自己的 API 已停止，原有两份报告仍保留，该核对也退出 **0**。原件 `worker-and-assets-checks.json`、`launcher-check.json` 均位于 `runtime/local-platform-check-20261018T055831Z-95665164`。早期时间字符串比较错误只属于验收汇总，实际测量与报告没有失败。

该历史轮次有 1 个真实对象完成窄范围三维评分，后续已增加预测实例及通用缺项报告，当前统计以 [STATUS.md](../../STATUS.md) 为准；至少 10 个真实公共 Agent 获得完整评分的目标仍未完成。网站/API/worker/PG 已实现，真实提交到报告保存、历史版本保留、缺项任务和启动器生命周期均有实际验收记录。浏览器视觉仍为 **BLOCKED**，未声称完成 DOM 交互或桌面/手机视觉验收。


2026-10-18 预测实例完成时的历史启动记录：通过常规 `./scripts/start_local_platform.ps1 -EnablePublicReadOnly` 保持网站和worker运行。第一次因启动脚本仍对所有profile强制要求增仓专用context_run/rpc_runs而exit1；将必需字段按已支持policy区分后，仅重试该失败启动，健康检查通过，当时RUNNING于127.0.0.1:7754，并非已退出0。未重新采集或评分，PostgreSQL仍为本项目原实例。
