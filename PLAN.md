# 从零构造执行计划（ExecPlan）

当前授权范围（2026-10-12）：基于已核实最新 main `60dec2c`，只依次修复 EXP-1 实验完整性与 OPS-1 公共刷新配额恢复。每项实际复现、最小实现、定向测试、独立 Review/自主修复及提交，之后整体回归、PR、required quality/Compose CI、正常合并和 main 同步；不修改冻结原件/历史 Release，不调用付费接口或主网写入。当前分支 `fix/exp1-ops1`，实际进度和待验收结果见 STATUS 及本轮验收记录。

EXP-1 阶段提交 93fdb88、OPS-1 阶段 bb0c0e6 已验收，12 项新增真实 PG 集成及独立 Review 两项锁/审计中断修复通过；跨模块 Review、43 历史 Bundle/234 独立单元通过。稳定 bb0c0e6 完整 check.py exit0：1701 Python/0skip、Web/Vite/浏览器、Foundry/ABI/Schema/TS全部通过，源码摘要无变化；104 新增测试。PR #16 最新 head 的 quality/Compose 与 main 合并终态以该 PR 为准，仅双 CI 全成功后正常合并并同步/清理本任务分支。本轮两项实现/本地验收完成；交付门禁后停止，下一任务为另行授权的比赛最终验收。

本轮授权范围（2026-10-12）：基于最新 main，依次完成 SEC-1 整合/历史数据隔离/独立 Review，再完成 SEC-3 独立 Verifier 身份完整性修复/独立 Review，随后执行完整回归、PR、required CI、合并及 main 同步。复用 22245d9，不改写不可变证据，不进行外部攻击或生产凭据操作；不展开 EXP-1/OPS-1。

本轮进度：SEC-1已通过PR #14、最新head完整quality/Compose CI并正常合并为2a59220，本地main已同步/核对干净。SEC-3在fix/sec3-verifier-identity先用单测及真实A/D Anchor复现AUD-EVAL-001，再复用公共1.6一致性校验修复受控1.0–1.5；独立跨模块Review/218项定向、17项真实PG/Anvil集成和43份历史Bundle/哈希完整性已通过。阶段提交d9f7d09的最终本地scripts/check.py完整通过：1597Python/0skip、Ruff/Mypy70/Schema74/TS drift、Web typecheck/build/21unit/5Vite集成/11browser groups、Foundry14/256fuzz/ABI3，exit0、源码/测试哈希无变化。身份/任务已有签名与规则约束保留，输出明确三种复核可信边界，见ADR0025/STATUS。本验收记录仅改文档；按授权推任务分支/创建PR，最新head两项CI全部成功后正常合并/同步main/只清理本任务分支，最终身份与CI以当前SEC-3 PR及runtime/sec3/final-delivery.json权威终态为准，不扩大范围。

历史 SEC-2 授权与验收记录：

本轮授权范围（2026-10-12）：仅修复用户指定的 SEC-2 Vite WebSocket 与 HTTP 资源访问控制不一致。在 `fix/vite-ws-access` 基于核实的 main `82dcb85` 精确升级 Vite 至首个修复版本 7.3.2，使用本地合成文件验证访问边界、异常输入、正常开发/HMR/API 代理及构建，完成独立 Review 与 Git 门禁。开发和当前 Compose 交付运行均在范围内，设计见 ADR0023，实际结果见 STATUS；不开展其他安全审计。上一轮 SEC-1 提交保留在 `fix/url-credentials`，本任务不混入其源码变更。以下任务11–13授权与结果为历史记录。

SEC-2 Git 流程已获明确授权：实现 `5a0510b` 推送任务分支并创建 PR #13，等待 foundation-quality / foundation-compose 等当前 head required checks 全通过后按仓库规则合并；随后同步 main、核对一致性和干净工作区并记录最终状态。仅提交本轮变更，不直接推 main、不绕过检查；最终身份及 CI 结果以 STATUS 和 PR #13 记录为准。

SEC-2 实现验收已通过：`5a0510b` 的 CI run `38210482851` 中 quality/Compose 均 SUCCESS，完整 1448 Python/21 Web unit/5 新增集成/11 browser groups/Foundry 14、类型检查、构建及真实 Compose A-D/报告/锚定/独立 Verifier 通过，独立审查无剩余问题。最终验收记录作为仅 PLAN/STATUS 的文档提交进入同一 PR，并等待该最新 head 的 required checks 全绿才合并；合并及 main 同步身份以 PR #13 终态和 `runtime/sec2/final-delivery.json` 为准。本轮在 SEC-2 Git 门禁完成后停止，不开展其他安全专项。

历史授权范围（2026-10-12 任务11–13）：基于已核实 main 76b411a，在 feat/tasks-11-13-delivery 按任务 11→Review/修复/验收/提交→12→Review/修复/验收/提交→13→综合回归/PR/required CI/合并/Release 连续推进。任务 11 正式 v2 实验已冻结，任务 12 产品与终审修复已验收，任务 13 部署/文档/打包/复现已验证；最终技术门槛结果见 STATUS/验收记录，最终 Git/Release 身份以 PR #12 与实际发布记录为准。历史测试或初始 unsupported 实验不计本轮最终通过。最新 checkpoint 见 docs/implementation/STATUS.md。

历史授权范围（2026-10-11）：续接main `ededc90`，依次任务8→Review/修复/验收→任务9→Review/修复/验收→任务10；优先完整交付8，资源不足则先提交与交接当前阶段。第三方只允许免费只读，无付款/签名/主网写入。任务8设计ADR0019，实际进度以STATUS为准；不展开11–13。

阶段进度：任务1–10实现与本地阶段验收完成。任务8 PR#9合并并核对main一致，本机与CI完整检查通过；任务9稳定00bcb43本机与Foundation CI完整1279项/0skip通过，最终文档head1334362的CI38116332399 quality/Compose均成功，PR#10合并为1897a74。任务10在feat/public-readonly-evaluation完成公共模型/Worker/证据/报告/独立Verifier，定向与独立Review修复、真实Akashi HTTP/MCP+Base66响应通过；4PASS/1UNKNOWN、ReportCore1.6/PARTIAL/overall=null、executor UNKNOWN、离线Bundle PASS/MATCH、本地publication UNANCHORED。本机完整check.py退出0：1409Python/0skip、Web2、Foundry14/256fuzz、Ruff/Mypy69/71Schema/TS/ABI全通过；干净CI发现3个测试遗漏deployment fixture，已补显式真实fixture，在不存在配置路径下3passed，未改生产逻辑或断言。实现0de08e4/修复c8f6dd4已推送、Draft PR#11；最终文档head全部CI成功才按AGENTS合并/同步main/清理本任务分支，真实CI与合并SHA以PR/Git历史为准。旧失败/无退出码日志不计通过，评分/充分度/身份绑定与历史规则不变；本轮到10停止，不展开11–13，详情见STATUS/ADR0021。

版本：foundation-v1.1，2026-10-03。状态：M0 基础验收完成（原生 Windows + Linux Compose CI）；M0-07 公网 OpenAPI 403 单列；M1-01 至 M1-08 已完成，M0+M1 最终验收通过。

## 2026-10-12 / SEC-1 原始本地修复（历史记录）

已按审计记录完成 URL userinfo 的公共证据脱敏与注册元数据拒绝；相关 CAS、Agent Snapshot、公开快照 API 回归及代码审查通过。身份认证、证据哈希、历史只追加机制和 ERC-8004/Bundle 流程未改；历史 CAS 不改写，真实历史秘密需单独隔离或撤下。该修复完成后停止本轮，不扩展到其他审计问题。

## 1. 最终要交付的系统
对同类凭证业务 Agent 固定身份与声明快照，执行合规测试，将返回结果与独立链上观测关联，生成三维证据评价，并以报告摘要存证和独立复核支撑审计。
主线不是目录/排行榜，也不是让大模型主观打分。

**最小可运行验收**：正常 Agent 真正写入 → 无关成功交易不能冒充本次结果 → 报告可导出 → 摘要真实上链 → 独立复核 → 修改证据被发现。

## 2. 材料与边界
基础需求来自用户提供的《项目实施规划 PRD V1.0》和《项目介绍与展示方案 V1.0》。保留三能力、三维度、四态结论、八类样本、M0–M4 与 policy-v1 初始公式。
本版本细化目录、任务租约、哈希输入、Git/Windows、协议复用及验收，变化见 `docs/references/SOURCE_ALIGNMENT.md`。
共享聊天链接只获得标题，未取得正文；GitHub 公开访问返回 404，不能确定私有性、默认分支或现有代码。Codex 必须在本地重新审查，不把此计划当已读过仓库。

## 3. 固定技术与工作方式
使用模块化单体。API 与 worker 是同一 Python 服务包的不同入口；复用 core，独立 verifier。
`apps/web` 使用 Vue 3/TS/Vite；`services/platform` 使用 FastAPI、Pydantic v2、SQLAlchemy 2/Alembic、httpx、web3.py；PostgreSQL 做任务队列；Foundry/Anvil 做本地链；Docker Compose 统一运行。
版本由 M0 实际解依赖并锁定，不假设“最新一定兼容”。无 Redis、Celery、Kafka、K8s、全网索引的基础依赖。
基础环境默认不用 Supabase/Vercel、付费模型和云账户，防止给核心开发引入额外账号/网络依赖。

## 4. 执行顺序与硬门槛
| 阶段 | 做什么 | 不通过时不能做什么 | 验收产物 |
|---|---|---|---|
| M0 | 审仓库/Git；工作空间；共享类型；迁移；安全 demo 网络；CI；版本锁 | 不堆页面或接公网 Agent | 环境审查、锁文件、Schema、最小健康检查、reference tests |
| M1 | 三个本地合约；双 Agent；最小绑定；任务调用与核验；部分报告；存证；独立复核 | 不做完整总分，不扩协议，不接主网 | 正常/无关交易/篡改三条真实验收记录 |
| M2 | 三能力用例、三维度、四态/原因码、充分度、完整 EOA 绑定、八类受控对象 | 不把缺证据样本硬排总榜 | policy-v1 算例、受控完整评价、消融数据 |
| M3 | 六个产品界面、权限、恢复、安全出口、历史/当前有效性、导入准备 | 安全出口未验收不得开启公网 URI 抓取 | 可人工操作端到端流程、安全回归 |
| M4 | ERC-8004 + 8004scan 公开注册接入、实验/恢复/匿名交付 | 未授权公开 Agent 不强行做写入评价 | 真实公开快照或明确受阻记录；完整回归与复現包 |

首轮执行 M0 + M1。M1 可通过 CLI + 极简页面验收，但不得缺真实 API/worker、链执行或复核器。
公网线不阻塞本地闭环；M4 的 live 集成失败需要单列阻塞，不能伪装整个 M4 已完成。

## 5. 本次已交付、尚未交付
已交付：执行与接口规格、任务卡、策略配置、评分参考模块、对应离线测试、Git模板、只读诊断和非覆盖安装器。
尚未交付：运行中的平台/API/worker、数据库迁移、已部署合约、真实报告包、前端、上游 ABI/提交锁、远程提交。
`docs/implementation/STATUS.md` 为真实进度来源；不得仅因存在规划文件勾选功能完成。

## 6. Codex 每个任务的执行循环
读取 task_id 的依赖 → 检查当前实现 → 先写/确认验收用例 → 实现最小路径 → 跑目标测试和相关回归 → 检查变更与 secrets → 逻辑提交 → 更新状态。
所有变更路径、异常语义和测试在 `docs/implementation/BACKLOG.md`。
任务遇到缺依赖/认证：写清命令、错误类别、缺少什么，继续独立任务，不修改门槛。

## 7. 进度（只根据真实运行更新）
- [x] M0 仓库与契约基线通过；Windows 原生实测、Linux Compose CI 实测，本机 Docker WSL 问题单列。
- [x] M1 本地真实纵向闭环通过。
- [ ] M2 三维规则与八类样本通过。
- [ ] M3 产品与安全恢复通过。
- [ ] M4 公网接入与最终验收通过。

## 8. 发现、决策与交接
发现记录：私有仓库已认证并克隆，原 main 仅含 README，历史已保留。详见 ENVIRONMENT/STATUS；公网接口/部署/依赖仍需实测复核。
关键决策记录：`docs/adr/0001-foundation.md`。
会话交接：每轮把已完成 task_id、未解决风险、测试路径、Git状态、下一条命令写入 STATUS，不依赖聊天记忆。
当前下一任务：M2（本次不展开）。M1-07 完成持久签名/nonce outbox、广播恢复、真实 EvaluationAnchor 发布和独立安全 ZIP verifier；M1-08 完成 A/D 真实 bundle、A 链上发布、离线/在线独立验证及篡改拒绝。

2026-10-03 本地环境修复：PostgreSQL 中文路径兼容入口改为项目所在盘根目录的 `web3-runtime` 目录联接；本机已移除 R:，保持原目录与数据。验证和本地 Git 状态见 STATUS 的 LOCAL-PG-JUNCTION；下一业务任务仍为 M1-07。

2026-10-06 本地环境复验：私有仓库已重新克隆并以项目内 Python 3.12.4、Node 22.17.0、pnpm 10.12.4、Foundry 1.8.4、solc 0.8.30 和 PostgreSQL 17.11 完成全量检查。针对 Windows/Hyper-V 排除默认 8545/9101/9102 的情况增加进程级端口覆盖，本机使用 18545/19101/19102；完整结果见 STATUS 的 WINDOWS-LOCAL-RUNTIME-SETUP。M0/M1 结论不变，下一业务任务仍为 M2。

## 2026-10-09 本轮范围

仅按顺序完成后续任务 1（三能力）、2（四态归因）、3（证据驱动逐任务复核）。三项均已实现并完成阶段 Review；最终 Review 的 CAS 去重、冻结链观测/时间、结算原因及在线链身份问题已修复并通过定向回归。dc6d974 稳定树完整检查退出 0（Python 314、Web 2、Foundry 14 项通过，均无 skip），PR #4 的 quality/compose CI 均通过；详细结果见 STATUS。当前每次报告仍只有一个任务槽位；独立复核对 v1.1 报告重新执行固定规则并比较任务结果/四态计数，对历史 v1.0 报告重新判定但明确不声称原报告计数比较。完整三维评分、前端、ERC-8004 和其他 M2/M3/M4 内容本轮不展开；本轮验收通过后停止，等待下一轮指令。

## 9. 完整完成定义
陌生队友克隆仓库后，可按 README 创建本地配置，运行迁移/合约部署/受控样本/demo/test/verify；不需要负责人电脑里的未提交文件。
报告里的每一个核心判断能追到任务、原始脱敏证据、断言和固定规则。失败/未知也能演示。
不得用静态假数据声称系统已测；外网数据、受控实验、历史回放有醒目标识。

## 2026-10-10 本轮范围与阶段结果

仅完成后续任务4（三维评价）和5（充分度/关键风险）；任务4阶段实现、测试、Review修复已通过：292单元/reference、12真实正式评价/报告、3真实Review回归，均无skip；规则与版本见ADR0014/STATUS。
任务4提交de8fe94。任务5已实现充分度解释/精确gate/证据引用风险/ReportCore1.3，阶段Review及314单元reference、3真实正常/风险/RPC测试通过；复用policy-v1门槛。
接着执行跨模块Review、全量Python/Web/Foundry/Schema/PostgreSQL/Anvil、提交/PR/CI。
本轮最终验收已完成；不把阶段通过当全量通过，不开始任务8–10。

最终Review已修复写任务返回字段漏检及畸形RPC误报：新正式计划使用@4/rule4/ReportCore1.3，旧@3在途任务明确保持1.2；340单元/reference、2真实新旧版本回归通过，跨模块Review无剩余阻断。此前全量检查在发现问题后主动中断，不能记为通过，稳定提交后重新执行。quality CI增加到25分钟以容纳约721秒固定正式任务窗口和其余完整检查，测试与评分门槛不变。详细记录见STATUS，任务4/5最终全量/PR/CI已完成。

任务4/5最终验收：稳定代码2379a03完整check.py退出0，Python447/0skip（2247.86s）、Web2、Foundry14（256fuzz）、Ruff/Mypy53/57Schema/TS/ABI全通过。PR#5的代码CI run37967395116在同head下quality/Compose均SUCCESS，CI Python447/0skip（869.28s）；四个历史A/D ZIP最终重放PASS且不升级。最终设计和Review修复见STATUS/ADR0014/0015。验收文档提交后需继续检查最新head CI再按授权合并及同步main；本轮任务4/5实现验收完成，停止任务6。

## 2026-10-11 任务6–7最终状态

任务6受控故障场景与任务7 Akashi 免费只读 PoC 已完成实现、Review/修复、定向回归、完整本地检查及 GitHub Foundation CI。最终PR head `0177ce11a7d9d669f57f9c1921ff8852d66a7a81` 对应 run `38069590008` 的 `foundation-quality`、`foundation-compose` 均成功。PR #7按仓库规则合并为 `ed782f24c075a9caf6e1a34c5ce6897f0b498d3d`；本地main与origin/main一致、工作树干净，本任务本地/远程功能分支均已删除。后续文档提交的SHA与CI以Git/PR历史为准；本轮停止，不开展任务8–10。


2026-10-10 最新main复查：328a712已合并PR#5的任务4/5。本轮任务4评分复查通过，再在任务5/跨模块Review复现并修复RPC日志误风险、UNKNOWN冻结恢复及正式Run状态。新规则5/@5/ReportCore1.4保留旧规则4/1.3原语义；评分和充分度参数不变，设计见ADR0016。稳定单元/reference396项、真实PostgreSQL/Anvil定向4项通过；稳定代码1b54cdf完整check.py退出0：Python507/0skip（1714.92s）、Web2、Foundry14/256fuzz、Ruff/Mypy53/57Schema/TS/ABI均通过。代码CI run38041353658的quality/Compose均SUCCESS（Python507/0skip）；四个实际历史ZIP重放通过。首次同名收集失败、本地数据库/工具进程中断均保留NOT_PASS记录，恢复后完整重跑，未降低门槛。PR#6最终文档提交后核对最新head检查再按授权合并、同步main和清理本任务分支，结果以PR/Git历史为准。完整需求审计及跨模块Review无剩余阻断，详细证据和限制见STATUS；本轮任务4/5验收完成，停止，不进入任务6。


2026-10-12 任务11阶段验收：12独立场景×3次真实v2采集36passed/0skip（461.04s），7指标测试与独立Review通过；源码/原件/分析/图表完整冻结。适用集Recall为Online0.2/Receipt0/Proposed1；UNKNOWN/N/A和局限保持，评分规则不改。实际运行时已有的最小读API/DTO和fixture ledger作为源码追溯前提同批提交，Task12页面另验收。当前继续12最后Review/真实UI、13部署/完整回归/PR/required CI/合并/Release；未完成门槛不记正式交付，详见STATUS。

2026-10-12 任务12阶段验收：真实Vue/API/Worker/A-D/Anvil/报告/证据下载/独立CLI导入闭环通过，21unit/build/7browser及读API/report定向通过。最后Review修复pending anchor误标与长hex溢出，历史冻结不改。Task11提交ba1b148；继续Task13与稳定代码完整回归/required CI/PR/合并/Release，不提前宣称完成。

2026-10-12 任务13实现/Review与定向14项、原生真实重复A/D/双anchor/Verifier通过，历史9+UI2 Bundle/109测试回归通过。CODE_VERSION/CAS/fixture卷/RPC/打包/文档已修复；正式赛事/匿名/第一方许可未知如实披露，不新增阻塞。进入稳定代码最终scripts/check.py/required quality+完整Compose CI/PR/合并/clean main/Release；最终验收未通过不标DONE。

2026-10-12 最终交接：任务 11 正式实验、任务 12 真实产品及任务 13 部署/交付软件已完成实施、独立 Review、修复和复现。已测试实现基线为 `aa539c9d9162e6bc54e641d4f0713608433e4dad`；全量 1448 Python/0 skipped、完整 gate 1765.39s 与 required CI run38164569622 均通过。旧中断全量不计通过。最终文档 head CI、合并/main 同步、针对发布 commit 的包/manifest 及 Release 由 PR #12/Git/Release 外部记录标识；不修改冻结实验与评分。官方赛事、匿名和许可要求仍按 COMPETITION_DELIVERY 核实。
