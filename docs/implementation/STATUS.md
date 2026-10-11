# 真实进度与会话交接

更新时间：2026-10-12；环境：用户 Windows 正式项目工作目录。

| Task ID | Status | 实施结果 |
|---|---|---|
| M0-01 | DONE | 已克隆私有仓库、保留 main 历史、创建功能分支、安全安装启动基线并合并 README；36 项参考测试通过 |
| M0-02 | DONE | 四包 uv workspace、真实锁、Vue 构建、Foundry 编译与测试通过 |
| M0-03 | DONE | 共享 DTO、33 份生成契约、TS 类型、确定性哈希及校验测试通过 |
| M0-04 | DONE | 真实 PostgreSQL 迁移、只追加约束、幂等存储、租约/fencing 和并发测试通过 |
| M0-05 | DONE | 认证 API、网络出口、worker 租约、原生运行及 Linux Compose 实测通过；Windows Docker 引擎仍受 WSL 导入问题影响 |
| M0-06 | DONE | 本地完整检查和远端 foundation-quality / foundation-compose 均通过，无关键测试跳过 |
| M0-07 | PARTIAL_EXTERNAL_BLOCKED | ERC-8004 真实 commit/ABI/许可与规范字节已锁；8004scan OpenAPI HTTP 403，不阻塞本地 M1 |
| M1-01 | DONE | 三个自研合约、生成 ABI、14 项 Foundry 测试（含 256 次 fuzz）通过 |
| M1-02 | DONE | 三合约真实部署、双 seed、持久 A/D、9 项真实 Anvil 测试及原生服务重启后的 HTTP 幂等复查通过 |
| M1-03 | DONE | 真实快照、声明 review、owner/executor 双 EIP-712 签名与单次 nonce |
| M1-04 | DONE | 授权、冻结意图、HTTP 发送与租约/crash reconcile 恢复 |
| M1-05 | DONE | 独立 RPC/纯断言，真实 A PASS、D 成功回执但 SEMANTIC_MISMATCH；CI b04a04a 通过 |
| M1-06 | DONE | 报告冻结、确定性 ZIP、并发/恢复/缺失/篡改拒绝、原生 A/D 报告 smoke 及166项全量回归通过 |
| M1-07 | DONE | PostgreSQL publisher nonce/outbox、签名后广播恢复、真实 EvaluationAnchor 发布、独立安全 ZIP verifier |
| M1-08 | DONE | 原生 API/worker/Anvil A/D 纵向演示；A/D bundle、A anchor、离线/在线 verifier、篡改拒绝 |
| FOLLOWUP-01 | DONE | 三能力模板与独立只读查询；具体状态及测试见 2026-10-09 任务记录 |
| FOLLOWUP-02 | DONE | 四态归因、标准 reason_code、原始响应证据及异常归因；具体状态及测试见 2026-10-09 任务记录 |
| FOLLOWUP-03 | DONE | 冻结 Evidence Bundle 逐任务重判、四态计数比较、历史格式兼容及独立 RPC 复查；最终 Review 修复已通过定向回归 |
| FOLLOWUP-04 | DONE | 正式多槽位三维评分、固定类别与安全负例、ReportCore 1.2 及独立重算；阶段 Review/真实集成通过 |
| FOLLOWUP-05 | DONE | 既有任务4/5已由PR#5合并；复查修复RPC日志误风险、冻结恢复及正式Run状态，新规则5/报告1.4；完整507项Python/Web/Foundry/Schema与代码CI通过，最终PR见#6 |
| FOLLOWUP-06 | DONE | A/D 新故障模式、独立预期及真实单槽位评分/充分度/风险/复核通过；Review 修复 RPC envelope 与只读 ABI 边界，规则6/报告1.5；最终本地回归与 Foundation CI 通过 |
| FOLLOWUP-07 | DONE | Akashi真实免费HTTP/MCP只读正例、独立Base事件核验、随机局部查询/非法输入/重复/注册存在检查通过；Review修复后重验；最终本地回归与 Foundation CI 通过 |
| FOLLOWUP-08 | DONE | 正式HTTPS/MCP只读适配、安全DNS socket pin、限频/配额/付款停止与CAS审计完成；真实免费调用、301项定向验证、独立Review修复及985项完整Foundation CI通过 |
| FOLLOWUP-09 | DONE | 固定块公共身份/端点关联、最终真实重验与独立Review通过；完整1279项通过，最终head CI成功，PR#10合并为1897a74并核对main一致 |
| FOLLOWUP-10 | DONE | 正式公共只读Worker/证据/报告/独立Verifier、Review/修复、真实闭环及本地完整1409项/0skip验收通过；最终head CI和Git交付按本节门槛执行，实际结果以PR#11/Git历史为准 |
| FOLLOWUP-11 | ACCEPTED_LOCAL | 12场景×3真实对照/完整冻结/独立Review通过，ba1b148；最终CI/Release待完成 |
| FOLLOWUP-12 | ACCEPTED_LOCAL | 真实Vue产品/API联调、21unit/11browser/build、终审修复通过；最终回归待完成 |
| FOLLOWUP-13 | IN_PROGRESS | 部署/文档/打包/重复A/D演示已准备，最终全量/CI/合并/Release待完成 |
| LOCAL-PG-JUNCTION | DONE | Windows PostgreSQL 改用 D:\web3-runtime 目录联接；R: 已移除，初始化、重启、数据完整性及13项定向测试通过 |

## 2026-10-12 / 任务11阶段验收（任务12/13与最终发布仍进行中）

- Baseline：main=origin/main=`76b411af797e480b0b8c117a5d06b78ebcfccd24`，工作分支 `feat/tasks-11-13-delivery`；用户授权继续11→12→13与最终回归/PR/CI/合并/Release。此前历史停止范围已由本轮要求替代。
- Task11 implementation：独立Ground Truth配置，复用真实PostgreSQL/HTTP Agent/Anvil/Worker/既有核验与评分，12场景×3次。正式v2 capture36 passed/0skip（461.04s）、exit0、source_changed=[]；离线analyse和克隆路径analyse exit0；指标边界7测试通过。完整原件与82文件exact源码ZIP冻结于`docs/testing/experiments/task11/formal-20261012-three-repeats-v2`。没有修改评分、充分度或风险版本。
- Results：Proposed6PASS/15FAIL/12UNKNOWN/3N/A；各方法适用集已知错误Recall为Online0.2/Receipt0/Proposed1，common writes为0/0/1；ProposedP/R/F1均1，关键风险9/9；Bundle结果/原因36/36，风险33/33，3份旧N/A报告明确无风险字段。正常写共享管道实测执行2567.532±52.378ms、链核验347.637±47.471ms、报告2807.448±173.974ms。不能把这些开销当独立基线benchmark。
- Review/fixes：拒绝初始手写判定/计时；真实旧30次和首轮36次保留runtime且不计最终。修复UNKNOWN弃权与Recall分母、receipt只读范围、方法范围预声明、实际HTTP/RPC请求计量、旧N/A风险不可比较、源码hash与原件完整性。首轮36次capture后源文件变化，因此重新采集v2而不改旧数据。独立Review与manifest/源码ZIP/重算/脱敏核查见实验README和REVIEW。
- Limits：受控重复不估计生产普遍性或显著性；无独立错误只读业务fixture；间歇服务用failure_every=1稳定选错，不估计故障概率；RPC计数不含Agent子进程；历史风险字段保持原格式。
- Prerequisites included with Task11：为保持实际执行源码可追溯，同提交包含实验运行时已存在的最小产品读API/生成DTO、fixture独立ledger路径和相关API测试/ADR。Task12页面单独验收和提交。读API用UUID keyset分页、manifest member/hash限定证据，写接口token/grant不变。API定向最终8 passed/0skip（50.06s）；首轮错误端口变量6pass/1fail记录NOT_PASS保留。Ruff/Mypy70/74Schema通过。
- Gate：任务11阶段实验/定向/独立Review/修复/重测/冻结通过，可逻辑提交；任务12真实页面联调与最后Review、任务13部署/全量回归/required CI/PR/合并/Release尚未全部验收，不能声称正式发布。旧提前全量进程已停止，NOT_PASS记录保留；不复用历史1409项作为本轮最终结果。

## 2026-10-12 / 任务12阶段验收（最终全量与Release待完成）

- Task11 Git：阶段实现/冻结/独立Review提交 `ba1b148`；尚未push/PR/合并，不把阶段通过当最终发布。
- Frontend：真实Agent列表/注册/刷新、Owner/ERC-8004/来源/声明/历史快照、绑定/公共只读关联；三能力/固定公共免费只读套件授权启动，内存token+payload-bound idempotency、2秒轮询及报告作业失败终止；三维分/实际样本数/覆盖/充分度/关键风险、PARTIAL/null/UNKNOWN/N/A、同Agent可比范围限制；manifest内任务输入/响应/链证据、Bundle下载和实际anchor状态；独立CLI JSON本地导入、摘要归因及offline/live/失败信息分开。
- Review/fixes：清理切换Agent/报告后的旧anchor/证据/Verifier归因；报告失败与网络错误停止轮询；绑定只标历史核验非当前授权；补样本实际数量非仅bp。真实原件16KiB+hex撑宽页面，min-width0修复后实际页面width=1360并加browser回归。GET anchor先前无confirmed回执一律NOT_REQUESTED，改为单次原子outbox/receipt读取：QUEUED/SIGNED/BROADCAST/FAILED如实，不导出signed bytes；manifest内他报告成员拒绝、CAS篡改/丢失409回归。
- Tests：前端21 unit、build/vue-tsc和7 browser groups通过；browser自行启停Vite并固定Playwright版本。读API初次最终8 passed/0skip（50.06s）；最后13项report/API组合中12通过，pending测试两处测试变量/参数错误修正后单项1 passed/0skip（19.43s）。原失败记录保留，不降低断言；最终全量仍须重新完整执行。跨模块独立Review无剩余阻断。
- Real UI：真实API→独立Worker→HTTP A/D→Anvil→核验/报告/manifest证据→下载Bundle→实际独立CLI JSON导入通过；A PASS，D成功receipt但FAIL/TASK_ID_MISMATCH，均PARTIAL/null/UNANCHORED。A先前UI启动完成后HMR重置，最终加载原Run；D过期绑定HTTP409按既有双签名与新grant续期后重试成功，无绕过。二份原ZIP独立CLI exit0；1360px真实证据布局/摘要MATCH/无未捕获异常复核通过。公开原件/截图/CLI结果与摘要清单见`docs/testing/evidence/local-ui-2026-10-12`；私有token/context/密钥不公开。
- Source freeze：仅`application/reports.py`是在Task11 capture后变化的执行源码，改变安全的pending receipt投影，不改变原未anchor实验/核验/评分/统计；原82文件exact snapshot与所有正式数据保持不动，实验README明确差异与跨OS重放换行范围。
- Gate：任务12实现→定向→独立Review→修复→重测→真实UI联调→阶段验收通过，进入Task13；全量/required CI/最终main/Release仍待完成。

## 2026-10-12 / 任务13实现与Review（最终门槛待运行）

- Git：任务11提交ba1b148、任务12提交6e774d2，阶段实现/Review/针对性/真实联调已通过；本节准备任务13逻辑提交，最终全量/CI/合并/Release未完成。
- Implementation：共享CAS卷且API可追加binding证据；actual CODE_VERSION强制；各服务只挂载所需配置，A/D独立可写持久ledger。prepare_compose_runtime真实验证部署/seed/发布者与固定端点，只复制4个配置重写内部RPC，保留host原件与旧目录。package_delivery基于指定Git commit归档、逐文件SHA/bytes/notice/lock清单，拒绝私密/runtime路径与覆盖旧输出，不自动声称匿名/许可/验收。
- Directed：package与真实Anvil/Compose准备14 passed/0skip（12.72s）、Ruff/Mypy/Compose config/文档链接与fence通过。repeat原生隔离PG/Anvil/API/Worker/A-D/Web smoke退出0：runtime/auth/webproxy→A PASS/D FAIL/TASK_ID_MISMATCH→两份PARTIAL/null报告→A/D双锚定→独立offline/可信RPC复核→篡改拒绝。日志见TASKS11_13_ACCEPTANCE.md。只签本地合成测试链，不付款/主网写入。
- Review/fixes：Compose image无Git须显式source版本；API/Worker同CAS且API不可仅ro；fixture配置与ledger分离/各自卷；host/container RPC与secret挂载隔离；smoke原旧SEMANTIC_MISMATCH总原因更新为当前固定TASK_ID_MISMATCH同时保持request/hash具体断言；重复演示必须发布D的旧FAIL报告避免previous head阻塞。旧失败原件保留。文档去除不存在的demo/test/Verifier参数；Chromium安装进入实际check/CI。
- History：当前独立CLI重放9个原始历史Bundle+2个真实UI Bundle全部exit0，原件SHA前后不变；109相关Verifier/publication tests通过（38.34s）。Akashi历史4PASS/1UNKNOWN、PARTIAL/null/executorUNKNOWN/UNANCHORED与302原件hash不变；本輪不重复公网请求，未声称当前公网状态。正式36次实验重判/分析一致性已确认。
- Security/delivery：分阶段staged源码与ZIP成员匹配现有token/DB凭据/实际本地private keys无命中；截图token已mask。77 Python/168 Web依赖元数据及2notice已盘点，不赋第一方license。官方赛事名/规则/截止/匿名模板无原件为UNVERIFIED；软件Release可在技术/CI通过后披露限制发布，官方参赛提交须另核实；不虚构合规。
- Final gates：本机Linux Docker因既有WSL问题NOT_RUN，不破坏原环境；增强foundation-compose将完整build/deploy/seed/start/A-D/双anchor/Verifier。稳定实现后开始scripts/check.py全量（FAIL_ON_SKIP=1），随后required CI/PR/合并/clean main/exact archive/Release；未通过前不标FOLLOWUP13 DONE。

## 2026-10-12 / 最终Review修复与重验

- Final candidate `0e36331` 已push并创建Draft PR#12；增强foundation-compose在CI run38161591091的job114535463881已实际SUCCESS，日志包含COMPOSE_RUNTIME_PREPARED/LIVE_RUNTIME_PASS/真实A PASS-D TASK_ID_MISMATCH/报告/双anchor/offline-online/tamper通过。该旧candidate结果不能代替最新head required checks。
- 独立finalReview复现报告poll旧失败会停止新Run、report/cancel POST返回后读已清理Run，以及旧load成功/失败覆盖新历史选择。修复使用已有updateIfCurrent与捕获run/generation，VM真实源码回归证明五条旧路径失败/新路径通过；最终21unit/type/build与11组browser通过、exit0、无未捕获异常，日志runtime/task12-final-browser-races.log。源码已锁定；无新业务规则。
- 打包完整性实际发现git archive换行转换：旧candidate .dockerignore/tool.ps1输出与Git blob不同。改用一次ls-tree/cat-file batch读取raw blob生成固定日期/权限ZIP，10package tests通过（8.68s），含CRLF属性/重复byte/unsupported mode；新输出对旧candidate911/911逐文件exact Git bytes核对通过。文档同改，不放宽exact-byte断言。
- Clean reproduction：全新候选checkout `0e36331`无.env/private runtime，uv locked sync、pnpm frozen install/build、DB/operator/RPC/config unset离线Task11重算JSON/CSV/report/chart一致；152实验/8UI/302Akashi原件与82source snapshot hash全match，checkout干净。三公共Bundle独立复核维持原四态/状态。完整tracked/40ZIP7039members凭据字段扫描0真实命中，仅12明确测试字面量；root额外7950source/ZIP扫描唯一PRIVATE KEY marker是负例测试，无实际key bytes。
- 原本本地完整check在上述finalReview前启动，明确中断为INTERRUPTED_NOT_FINAL；仅杀已确认的该check进程树，未动demo/开发数据库。日志/结果保留`runtime/tasks11-13-full-check-final*`，不得计为通过。修复后稳定candidate需重新执行全量与最新headCI；最终Git/Release未完成。

## 2026-10-11 / 本轮任务10正式公共只读评价（本地阶段验收完成）

- Baseline：任务9最终文档head13343622b41c2aa1947963e8be41c2f525cb991b的CI38116332399 quality/Compose均SUCCESS，PR#10按授权squash合并为1897a7408550116e0294c8c4eff25b580eb5c482。已fetch/prune、安全同步main=origin/main、核对合并树等于最终PR树、工作树干净，仅清理任务9本地/远程分支；随后建立feat/public-readonly-evaluation，未并行开展不同阶段。
- Design/implementation：显式公共Task/Facts/Slot/Plan/Grant/Input、新rule7/ReportCore1.6分支，复用Worker/PG/CAS/Observation/评分/Bundle；公共executor=None，旧EIP-712受控规则1–6不变。固定5槽免费只读查询与独立Base历史证据；样本不足保持PARTIAL/overall=null。完整机制与兼容性见ADR0021；迁移不改历史，存在executor-null公共行时downgrade明确拒绝。
- Egress/evidence：固定Akashi HTTP/MCP及Base历史tx/receipt/必要block白名单，DNS全部公网验证后pin数字IP，socket前核对当前快照、授权/撤销/取消/deadline与租约。跨Worker advisory lock串行、至少1秒间隔、64请求配额；付款/未知副作用/协议故障停止共享出口，无自动重试。每intent/response写CAS并注册后才继续；恢复保留原件及真实尝试时间/响应状态，已发出但响应不完整为UNKNOWN/DISPATCH_UNCERTAIN、无声称latency、无补发。
- Review/fixes：独立Review修复OpenAPI付款字段存在性、身份原件不足越界、拒绝/服务故障误计业务结果、恢复原件丢失/latency以及publication.platform_instance_id篡改。CLI首次evaluate和report阶段失败材料保留runtime；前者修复任务9身份21条引用兼容（持久start ledger+20原件），后者修复TaskOutcomeCounts按别名序列化KeyError。均补回归；最终有针对性Review108 passed/0skip，无剩余可行动阻断。
- Directed/regression：公共平台/出口202 passed，公共PostgreSQL/Anvil11 passed，恢复定向1 passed（11.77s），核心459 passed，Bundle29 passed；全树Ruff、Mypy69源文件、71Schema/OpenAPI和TS生成检查通过，Web构建/2测试通过。首个有退出码的完整check发现迁移downgrade约束名被命名规则重复加前缀，实际PG复现1 failed；改用op.f固定已展开名称，空库真实roundtrip1 passed（2.60s），现有公共5行拒降级/数据保留/无schema漂移和最终恢复组合2 passed（89.36s），独立SQL/边界Review通过。原完整进程在确认失败后主动停止exit1，日志runtime/task10-full-check-final.log和-result.json，明确NOT_PASS。稳定代码完整重跑最终结果见下方Local final，日志runtime/task10-full-check-reviewed.log和-result.json；没有退出码的更早检查不计通过，也不复用任务9结果。
- Live：正式CLI `scripts/public_readonly_evaluation_smoke.py --allow-public-readonly --operator-dns-over-tls` 首次成功15:18后，仅恢复延迟从等待时间改为None；逆向该补丁hash严格匹配旧manifest。最终执行源码重新真实验收于runtime/task10-live-final-20261011-1540退出0，真实API→evaluate/verify/report Worker→冻结Bundle。66次网络响应（56 Base RPC、6 HTTP、4 MCP；64x200/1x202/1x400），实际独立Base canonical交易/回执/12确认和锁定Anchored事件核对；4 PASS、1 UNKNOWN、0 FAIL。ReportCore1.6.0、Run/report PARTIAL、overall_score_bp=null；executor UNKNOWN，未请求本地anchor，publication LOCAL_ANVIL/UNANCHORED。独立Bundle离线PASS、assessment/task_count MATCH；随机hash未查到不证明全球不存在。付款/签名/主网写入均0。
- Published evidence：最终run的脱敏acceptance、66响应审计、229CAS、66DNS、Bundle、source-manifest和progress/run-context保留于docs/testing/evidence/akashi-public-evaluation-2026-10-11；publication-manifest对302文件逐字节承诺，Git禁止证据换行转换。最终manifest所有执行平台/core/verifier源码与交付一致，仅run启动后迁移downgrade名称修复和PG历史保护测试两个文件不同；README明确说明，不重写真实源清单。旧成功/失败材料和前次公开副本保留runtime，隔离本地数据库保留，不提交凭据、token、private key或链状态。公开原件与ZIP、待提交变更静默匹配现有7项敏感值均0匹配。
- CI isolation failure/fix：代码提交0de08e4368965c234fcbe7f65872cca2a7e76e66已push并创建Draft PR#11，Foundation run38122561336 Compose SUCCESS、quality FAILURE：1406 passed/3 failed/0skip/2warnings（1343.72s）。唯一失败是公共revoke/disabled/cancel三个测试遗漏deployment fixture，本机已有runtime配置掩盖了依赖。测试显式复用真实identity_chain并标注chain，所有零调用/五观测/完整CAS断言保持；LOCAL_CHAIN_CONFIG故意指向不存在文件时3 passed（11.93s），不改生产代码或安全门槛。原失败日志runtime/task10-code-ci-complete.log与-result.json保留NOT_PASS；最终CI需对最新head重跑，不用本机旧配置的成功代替干净环境验收。
- Local final：完整check.py于2026-10-11T08:22:08Z实际退出0；Python1409 passed/0skip/2warnings（2189.57s），Web类型生成/build/2tests、Foundry14/0skip/256fuzz、Ruff、Mypy69、71Schema/OpenAPI/TS无漂移及三ABI全部通过。原件runtime/task10-full-check-reviewed.log和-result.json。本机运行开始的实现及测试树对应随后提交0de08e4，执行期间仅增加上述3个测试的显式fixture和文档；最终fixture在不存在本地配置时另测3 passed，生产源码完全相同。最终干净Linux/full CI必须再对最新head全量运行，不把旧head或本机现存配置当该CI成功。
- History/final audit：当前Verifier对四份实际历史A/D ZIP离线重放均PASS，旧assessment明确NOT_AVAILABLE_LEGACY_REPORT、anchor NOT_CHECKED，记录runtime/task10-historical-bundle-replay.json。最终302文件清单/303 Git blobs逐字节一致；源清单仅迁移与测试两处逻辑差异，domain.py与safe_http.py在Git内只规范CRLF为LF，README说明完整。全部358变更与314 ZIP成员静默匹配当前7项敏感值0命中；第三方真实调用没有付款/签名/主网写入，独立代码及证据Review无剩余阻断。
- Gate/Git/next：任务10实际实现→定向→独立Review→修复重测→真实闭环→本地完整阶段验收完成。实现0de08e4和fixture隔离修复c8f6dd4已push，Draft PR#11 base=main/head=feat/public-readonly-evaluation。最终验收文档提交后继续等待最新head所有Foundation checks成功，转Ready并按AGENTS条件合并，fetch同步main=origin/main、核对合并树，再仅清理本任务分支；CI run/最终head/合并SHA以PR#11和Git历史为准，旧失败run不计成功。本轮8→9→10实现与验收顺序完成，不开展11–13。外网默认关闭；公开少样本仍PARTIAL/overall=null、executor UNKNOWN、本地未anchor；离线复核不证明采集者诚实或实时主网状态，评分/充分度门槛不变。

## 2026-10-11 / 本轮任务9受限公开身份接入

- Baseline：已核对PR#9 MERGED，main=origin/main=079bb57abac954fd920b539060679575858cea2c，合并树与e5ece713逐文件一致，工作树干净；本任务分支feat/erc8004-readonly-identity，未开展任务10。
- Implemented：复用锁定ERC-8004 ABI、SafeHttpClient、CAS、AgentSnapshot、PostgreSQL和ingest Worker，固定Base8453/Registry/98097；同数字块ownerOf/tokenURI/code与canonical复查；严格元数据复合身份/声明，MCP精确端点、HTTP另核OpenAPI原件；public snapshot hash承诺core+PublicIdentityRead，旧格式无字段/哈希变化。注册/端点/执行者/业务分开，executor/business永远UNKNOWN，不产生binding或绕过写任务门槛。设计ADR0020，运行说明PUBLIC_READONLY_IDENTITY。
- Directed：核心、Reader、安全出口/适配、契约和历史PoC定向541 passed/0skip（16.33s），新增真实公开原件重算1 passed/0skip；真实PostgreSQL公共/受控身份及适配证据24 passed/0skip（63.21s），合计566；Web2/build、Foundry14/256fuzz、Ruff/Mypy59、CLI Mypy、61Schema/TS/ABI通过。首轮uv未在PATH/错误测试文件名导致NOT_RUN已纠正，没有记为通过；过程中并发编辑的lint输出也保留失败，稳定代码再检查通过。
- Review/fixes：独立实际复现并修复发送后落库前重复公共读取（持久发起ledger，恢复UNKNOWN无重发）、失败新读保留旧PASS（当前关联失效）、网络故障误归解析失败、ABI URI/畸形RPC额外字段编码凭据漏脱敏、缺注册原文仍PASS、OpenAPI GET输入和顶层/path付款漏检。所有问题补回归/重测，最后受控回归和独立复审无剩余可行动发现。
- Live：修复后最终run2退出0，10次免费身份只读全部200（无业务请求）；固定块52451849/hash0x6e8fc723ddaa8096f44749ab9a45a4bc1c117049866ae0f7f204c22d1bf18e6f，Owner与历史一致。20CAS、10DNS、ABI/raw SHA256、元数据/OpenAPI/hash、双端点关联及IPpin审计全PASS；注册/端点PASS，executor/businessUNKNOWN。35原件逐字节公开于docs/testing/evidence/akashi-identity-2026-10-11，manifest/6源文件hash无变化；after-review/final_acceptance=true。全本轮20真实身份请求，无支付/签名/主网写入；run1仅pre-review NOT_FINAL材料保留runtime，没有用其冒充最终通过。
- Regression failure/fix：d34a9a9对应Foundation CI run38112125274，quality/Compose均SUCCESS，Python1279 passed/0skip（1244.22s）。本机同head完整check.py退出1：1278 passed、1 failed（2142.15s），不能计为通过；唯一失败是既有报告重放测试的1秒租期安全LostLease，job保持LEASED，没有越过fencing。改为重放开始后等待一次真实数据库续租事件，正常租期、有限等待、SUCCEEDED及单报告断言均保留；没有修改生产lease/fence。修复定向1 passed（16.15s）及独立Review通过；runtime-only真实行锁突变退出1（28.43s）被续租事件断言检测，撤除突变后1 passed（16.54s），证明行锁验收没有放宽。两个上游弃用warnings保持可见。
- Final full acceptance：稳定00bcb43aa8023ed0a834626492e3394df37e9c7b本机完整check.py退出0，Python1279 passed/0skip/2warnings（2118.55s）；同head Foundation CI run38114309427的quality/Compose均SUCCESS，Python1279 passed/0skip/2warnings（1174.56s）。两者Ruff/Mypy59、61Schema/TS漂移、Web build/2 tests、Foundry14/256fuzz、三ABI全部通过。实际日志与结果分别runtime/task9-full-check-reviewed.log、task9-full-check-reviewed-result.json、task9-reviewed-ci.log和task9-reviewed-ci-summary.json。六实施源码与最终真实run2承诺保持不变，无需追加公网调用。四份历史真实A/D Bundle离线重放PASS，未将未执行的线上anchor核验记为通过。需求映射和独立Review无剩余阻断。
- Git/next：实现cd4238fa、收集修复d34a9a9、续租测试修复00bcb43已推，PR#10已创建。首轮完整check.py收集冲突exit2及第二轮本机exit1保留为NOT_PASS；改名后1279项收集退出0仅表示收集通过。当前实现→定向→Review→修复→重测→完整阶段验收完成；本节最终验收文档提交后仍核对最新head全部checks，再按AGENTS合并、同步main和仅清理本任务分支，最终SHA/CI以Git/PR历史为准。本阶段仅身份关联，任务10未开始；完成Git交付后下一项为10正式Worker、真实业务链核对、评分/Bundle/独立Verifier，不能把任务9描述为公开Agent完整评价闭环。

## 2026-10-11 / 本轮任务8正式只读适配

- Baseline：按用户续接指令读取原goal-objective任务8–10，main/origin/main均ededc90、工作树干净、目标remote与权限核实。分支feat/formal-readonly-adapter；严格按8→Review/修复/验收→9→10，不重复仓库大审查，未开始9/10。
- Implemented：复用SafeHttpClient增加显式公共只读模式；固定Akashi HTTPS/443/path/MCP白名单，全部DNS答案IPv4/IPv6公网校验、实际数字IP socket pin、原Host/TLS SNI/CERT_REQUIRED、禁复用/redirect/proxy/Cookie与认证；20s/1MiB/depth32、串行完成后1s间隔、64次尝试配额、零自动重试。HTTP402不读body，付款header/JSON/MCP text/所选find_proof付款声明均停止；未知MCP副作用/握手异常不可跳过工具门槛。
- Adapter/evidence：平台静态HTTP/MCP适配为verify_record类查询，现有Observation+EvidenceRecord/CAS；发送前持久意图、接收后审计与安全原body保存，失败写盘停止。原PoC纯业务断言移入core保持AST相同，旧脚本兼容导出。复用PostgreSQL注册/只追加，去重ID重映射；没有改TaskEnvelope/Grant/Schema/评分或正式controlled Worker，任务9/10才接身份/规划/评分/Verifier。设计ADR0019，运行说明THIRD_PARTY_READONLY。
- Directed/review：最终安全出口/适配/PG/旧PoC/业务断言等定向299 passed/0 skipped（7.39s），公开真实材料回归2 passed（1.12s），合计301；全树Ruff、Mypy55源文件和新增CLI各退出0。独立Review复现并修复MCP部分握手超时跳过工具检查、所选工具付款漏检、camelCase凭据漏脱敏、normalized敏感字段外泄；独立最新Review101 passed/0skip。额外Windows重跑发现sleep提前唤醒限频问题，改为单调期限循环+请求完成后间隔，并使用可控时钟测试排除宿主调度误报，Review通过。没有放宽断言或跳过失败。
- Live：系统DNS解析198.18.0.85被正确阻断（run1退出1）；显式1.1.1.1 DNS也被fake-IP截获。操作者固定8.8.8.8:853/dns.google的TLS认证DNS resolver获得新鲜A/AAAA，仍经全部公网校验+pin，不声称DNSSEC。run2一次ConnectError，退出1且无自动重试；run3完整退出0。最终代码run4再次退出0：共8次请求（HTTP200/200/200/400；MCP200/202/200/200），2HTTP正例与MCP归一一致，随机hash200/有限未发现，非法hash400；没有402、支付、签名或主网写入。成功原始acceptance/16CAS/8DNS完整脱敏公开于docs/testing/evidence/akashi-formal-2026-10-11；所有失败材料保留runtime。该结果仅协议/证据验收，不冒充新身份或业务链上独立核验/完整评价。
- Complete CI：稳定代码提交d8297bbf2c2b0a10dea6338700daf17a697f692f对应Foundation CI run38108211933完成success，quality/compose均SUCCESS。完整check.py实际Python985 passed/0 skipped/2 warnings（1245.72s）、Web2、Foundry14/256fuzz、Ruff/Mypy55、57Schema、TS生成与三ABI检查全部通过。日志runtime/task8-code-ci.log，未把安装缓存的“skip”文字当作测试跳过。
- Evidence/history audit：四份实际历史A/D ZIP由当前源码离线重放全部PASS（anchor NOT_CHECKED）；16CAS与commit/run4逐字节一致，7份非空响应SHA256有效，8DNS外层JSON仅CRLF/LF差异，32段DNS wire字节完全一致。整轮29次尝试（5+8+8+8），全部符合白名单；5次公网IP拒绝、1次连接失败、23响应（18x200/3x202/2x400），付款/402均零。审计文件runtime/task8-acceptance-audit.json，无新增实测流量。
- Gate/Git/next：任务8实现→定向验证→独立Review→修复→重验→完整CI阶段验收通过。PR#9已合并为079bb57abac954fd920b539060679575858cea2c，任务9开工前核对main=origin/main、合并树与最终PR head一致、工作树干净，本任务分支已删除。本机稳定代码d8297bb完整check.py亦退出0，Python985 passed/0skip/2warnings（2041.58s），其余完整检查全部通过；结果原件runtime/task8-full-check.log与task8-full-check-result.json，完成时间2026-10-11T03:58:04Z。任务8无未完成源码需恢复；已顺序进入9，9Review/验收/合并后才做10正式Worker/评分/Bundle/Verifier，不降低写入绑定、评分或充分度。

## 2026-10-11 / 本轮任务6–7最终验收

- Final local/CI：稳定提交 `5c8f2393ff628cb5bb1973bcd1b52836bc37c3df` 的本地完整检查结果为 Python 879 passed / 0 skipped / 2 warnings，Web 类型生成/构建及 2 个 Web 测试、Foundry 14（含 256 fuzz）、Ruff、Mypy、57 Schema、TS 生成和 ABI 检查全部通过；结果文件为 `runtime/task67-full-check-result.json`，exit code 0。Foundation CI run `38067747321` 在同一 head 完成 success，`foundation-quality` 与 `foundation-compose` 两个 required checks 均 SUCCESS。
- Final PR/Git：最终PR head `0177ce11a7d9d669f57f9c1921ff8852d66a7a81` 对应 Foundation CI run `38069590008` completed/success，quality与Compose均SUCCESS；CI实际Python 879 passed / 0 skipped / 2 warnings（1154.17s），其余完整检查通过。该head相对本地完整回归仅有验收文档更新；合并树与最终head逐文件相同。
- PR/范围：PR #7 base=`main`、head=`feat/controlled-agents-readonly-poc`，无冲突、无 required reviewer、无权限/敏感配置变更，先转Ready再按授权squash合并为 `ed782f24c075a9caf6e1a34c5ce6897f0b498d3d`。fetch/prune后本地main与origin/main一致、工作树干净，本任务本地及远程功能分支已删除；其他分支保留。任务6和任务7均达到验收。任务7仍仅为免费低频只读 PoC，不接正式 DB/评分，不开展任务8–10。
- Completion audit：逐项核对用户要求、实现/独立预期、全部实际测试日志与第三方原始证据；当前版本四份真实历史A/D ZIP离线重放全部PASS。76次实际请求逐一通过当前精确只读策略、body长度/SHA256及串行间隔审计；公开30份body与原run及Git字节一致。真实CID事件和注册owner/URI从保留RPC结果独立ABI解码复查通过。后续文档提交的SHA与CI以Git/PR历史为准。

## 2026-10-11 / 本轮任务7：免费第三方只读PoC

- Actual：官方Akashi文档/health/OpenAPI/llms/注册描述和MCP discovery真实可达；免费GET /proof及MCP find_proof实际业务可调用。固定官方源码21a1ebd的历史示例tx作为候选，先用独立mainnet.base.org核实Base8453、tx/receipt/status1、旧ETH官方合约、Anchored ABI/topic、hash/filename/payer/timestamp/paid及固定canonical块；可靠正例3次HTTP和1次MCP均PASS，HTTP/MCP归一化一致。块38158156，观测head52429346，确认14271191。
- Separate results：随机合法SHA256返回200/anchored:false，但legacy合约unsearched；有限搜索响应合理，全链不存在UNKNOWN。非法hash明确400为正确输入拒绝PASS，不扣业务分。三次HTTP672/203/203ms只说明这些观察稳定。ERC8004 Base registry与既有锁定上游b9e466c一致，ID98097在固定块独立code/ownerOf/tokenURI确认非零owner与官方注册URI，身份存在PASS；没有证明executor绑定或完整正式评价。
- Safety/evidence：SafeHttpClient.readonly_poc显式隔离静态HTTPS/path/MCP/RPC白名单；正式平台仍回环HTTP。无redirect/proxy/Cookie复用、20秒/1MiB、串行1秒间隔/总预算64且无自动重试；禁止anchor_hash、/anchor、任意eth_call、支付/签名/链写入。402先停且不读付款body；HTTP200内付款要求也停止。最终完整run33次（32x200/1x400），含调查及一次导入失败全轮76次（74x200/2x400），没有付费/402/主网写入；全部实际请求经策略审计、原始body SHA256复算通过。
- Review/fixes：补嵌套PAYMENT_REQUIRED/MCP工具错误停止、证据写盘失败终止、CLI根目录导入、Cookie自动重放、tools/annotations畸形边界；纯断言补MCP多表示冲突、日志语义位置/严格有序index、间接目标及非SHA CID保守UNKNOWN。最终跨模块Review发现40KiB深MCP文本JSON的RecursionError绕过协议错误处理，转ValueError后保持UNKNOWN并补回归。原始body禁换行转换，约191KB小型公开材料发布于docs/testing/evidence/akashi-2026-10-11，30份必要原始响应+hash/time/status/请求及summary；三份非业务发现原文明确省略，原SHA及本地完整材料保留，无认证/钱包/支付凭据。
- Tests/failures：新增纯业务断言94项；网络出口+既有HTTP100项；观察/发布真实材料重放10项；稳定合计204 passed/0 skipped（1.65s）。Ruff全树、Mypy53+两PoC脚本及57Schema通过，最新全量收集879项。初HTTP测试因巨大bytes参数ID导致Windows环境长度错误，修短ID后通过；首次完整CLI仅资料阶段后ModuleNotFoundError退出1，修根目录path后完整重跑退出0，未把失败当通过；额外脚本Mypy初报异构JSON字典推断18项错误，补两处dict[str,Any]边界注解后通过。独立模块自Review、最终跨模块Review及修复重验完成，无剩余范围阻断；最终完整check.py与同 head Foundation CI 均通过，详见本节最终验收记录。
- Adaptation：复用JSON/hash/RPC基础、未来Task/Evidence CAS及Verifier组织；需要最小静态HTTP/MCP映射、官方事件版本断言、可信Base固定区块、公开快照/授权及身份执行者绑定。不能把Demo getRecord/request_id/grant/controlled envelope直接套用。只交独立PoC与分析，不接正式DB/评分，不新增依赖或前端。详见AKASHI_READONLY_POC和ADR0018。
- Git/next：任务6阶段提交35bbef2；任务7阶段提交7a04523；证据字节保持提交5c8f239；验收文档提交0177ce1；PR #7的最终head required checks通过后已按AGENTS条件合并、同步main并清理已完成分支。下一步停止本轮，不开展8–10。Windows Docker/WSL限制仍由真实Linux Compose CI单列验收。

## 2026-10-10 / 本轮任务6：受控异常阶段验收

- Baseline/scope：main/origin/main核实为68ee882（PR#6）。既有正式多槽位已在main存在，因此不重建架构；冻结前采样单槽位、互斥purpose，少样本全部PARTIAL/overall=null。实现前独立预期见CONTROLLED_SCENARIOS，设计与兼容见ADR0017。
- Actual：正常A PASS/A10000；3.2秒响应PASS/A8000；稳定503 FAIL/AGENT_SERVICE_ERROR/A0；20秒响应UNKNOWN/SERVICE_TIMEOUT/有效分母0。已声明但unsupported为FAIL/CAPABILITY_EXPLICITLY_UNSUPPORTED，HTTP A10000、功能0而非N/A。正常行为PASS/10000；D历史交易FAIL/TASK_ID_MISMATCH及真实D执行当前任务FAIL/TX_WRONG_EXECUTOR均critical，PARTIAL仍NOT_RECOMMENDED。
- Identity：真实注册URI/description版本标记与revision变化为UNKNOWN/IDENTITY_CHANGED，新快照不继承binding；executor有代码导致UNKNOWN/BINDING_UNVERIFIED，撤权UNKNOWN/ACCESS_NOT_GRANTED。检查原始HTTP和派发事件确认没有实际业务派发；not_sent是数据库结算占位。版本用例验证注册画像变化，不声称部署新服务二进制。
- RPC：真实连接拒绝和不响应socket触发实际读取超时；错误链/非法receipt/畸形record_call是对真实RPC采集结果的受控注入，明确区别。均UNKNOWN、无平台诱发critical；HTTP可用性独立保留。冻结原UNKNOWN与健康复读两份证据，在线Verifier单列RESOLVED/PASS，不改历史。
- Review/fixes：修复rule5把非法status当PENDING_FINALITY及缺status当SCHEMA_ERROR、tx/receipt/block/head/chainId位置互斥漏检、只读固定块/ABI边界及恢复占位断言豁免。新capabilities@6/rule6/ReportCore1.5贯通共享类型、Worker、报告、Verifier及生成契约；规则1–5/报告1.0–1.4重放语义不变，在途@5冻结1.4。四个既有真实A/D ZIP离线重放PASS，旧assessment明确NOT_AVAILABLE_LEGACY_REPORT。
- Tests：稳定unit/reference547 passed（47.46s）；fixture配置及真实Anvil执行38 passed（21.86s）；controlled E2E16+既有RPC recovery3为19 passed（327.19s）；追加真实RPC timeout1 passed（44.99s）；RPC/query/Verifier定向194 passed（22.48s）。均0 skipped。Ruff、Mypy53、57Schema/TS及diff检查通过。既有websockets与Starlette弃用warning未隐藏；完整check.py与本轮CI尚未运行，不能以阶段结果替代。
- Failure history：初测Web3地址未checksum、额外metadata.version不被DTO允许、not_sent占位被误当派发，均修复测试真实性；在并行编辑期间加载旧代码产生NameError/旧trace，停止编辑后稳定重跑通过；新增合法rule6使旧“不支持6”测试失败，改为不支持7；Mypy临时变量类型冲突已修复。未修改评分权重、门槛或预期制造通过。
- Git/next：阶段6提交于feat/controlled-agents-readonly-poc，提交SHA以Git历史为准；完成阶段Review后才开始FOLLOWUP-07免费只读PoC。最后跨模块Review、完整回归、PR/CI；不开展8–10。

## 2026-10-10 / 最新 main 任务4/5复查修复

- Baseline：fetch核实main/origin/main为328a712，PR#5已合并任务4/5；最新main CI run37973933397的quality/Compose均SUCCESS。复用现有三维评分、充分度与风险机制，不重复实现、不开发任务6。
- Order/Review：先复查任务4，176项定向单元/reference通过且无阻断，再检查任务5及跨模块链路。发现格式合法但位置互斥的RPC日志被rule4误归critical、恢复读数拒绝冻结原UNKNOWN、正式完整报告仍显示Run PARTIAL；修复后重新验证。原main重跑check.py在发现问题后主动中止，明确NOT_PASS，不复用其结果。
- Implemented：新capabilities@5/rule5/ReportCore1.4在业务断言前核验全部日志schema、固定事件ABI、交易/区块/序号、removed与唯一有序logIndex。RPC互斥为UNKNOWN/EVIDENCE_INCONSISTENT，畸形为UNKNOWN/PLATFORM_RPC_ERROR；均不扣Agent分、不创建critical。preserve_rpc_unknown共享纯规则保持原测量UNKNOWN，冻结复读和在线恢复单列，原已判定任务遇坏证据仍拒冻。新完整正式报告设Run COMPLETED，充分度不足保持PARTIAL。
- Compatibility：policy-v1/three-dimensional-v1/evidence-assessment-v1、公式/权重/阈值均不变；历史@3→1.2、@4→1.3显式冻结/重放，不升级。原rule4对照16个场景、原1.3报告对照3个场景逐字段一致。Schema/OpenAPI/TS同源生成，无新依赖、DB migration、合约或前端功能。
- Tests：稳定单元/reference396 passed/0 skipped（32.14s）；新增44项日志/ABI/helper单元通过。真实PostgreSQL/HTTP/Anvil首测矛盾恢复、反向拒冻及在途@4组合3 passed/0 skipped（206.35s）；追加真实畸形日志恢复1 passed/0 skipped（90.23s）。Ruff、Mypy53、57Schema及TS生成通过。独立跨模块Review已确认无剩余本范围阻断。
- Full check retry：5a83358完整check.py在pytest收集阶段发现新增unit/integration同名模块冲突，退出2/NOT_PASS；集成文件改为test_rpc_evidence_recovery.py，测试内容/门槛不变。保存原失败日志，先验证全量收集再在稳定提交重跑。
- Full check interruptions：1b54cdf首轮完整检查因本地PostgreSQL进程消失/连接超时而停止，工具返回-1/NOT_PASS；恢复数据库后的工具会话也消失，日志停在前几项通过且无最终退出码，仍为NOT_PASS。两次原日志分别保留；通过既有local_postgres.py恢复原数据，不重建数据库、不修改业务代码或门槛，随后用独立后台进程保存完整日志与退出码重新验证。
- Local final：稳定代码提交 **1b54cdf23c2eb14c2a0e5fa0642a418d72c38ac3** 的完整 `uv run --env-file .env --all-packages python scripts/check.py` **退出0**（2026-10-10 21:56:47–22:26:18 CST）。只设置PYTHONUNBUFFERED和pytest详细输出，FAIL_ON_SKIP=1保持不变。完整Python **507 passed / 0 skipped / 2 warnings**（1714.92s），包含真实PostgreSQL/HTTP/Anvil、正式评分/充分度/风险、新旧版本及M1回归；Web typecheck/build与 **2 tests passed**；Foundry **14 passed / 0 failed / 0 skipped**，含256次fuzz；Ruff、Mypy53、57Schema、TS生成无漂移及三份ABI检查通过。结果文件明确记录同一head与exit_code=0；两条既有Starlette/httpx与websockets弃用警告未隐藏。
- CI：PR **#6** 的代码head **1b54cdf23c2eb14c2a0e5fa0642a418d72c38ac3**，Foundation CI run **38041353658** completed/success，foundation-quality与foundation-compose均SUCCESS。CI实际Python **507 passed / 0 skipped**（1006.06s）、Web2、Foundry14（256fuzz）、Schema/TS/ABI全通过；Linux Compose真实build、迁移/runtime smoke和独立worker通过。被新提交取消的旧run38041274211不计通过。最终验收文档提交后仍须核对PR最新head全部检查，不能拿旧head成功代替合并许可。
- Review/acceptance：任务4评分复查→任务5修复/测试/Review→跨模块需求审计均完成，无剩余本范围代码阻断。风险、充分度、数值和任务成功率独立；坏RPC先保持UNKNOWN，已确认风险不受高分/PARTIAL抵消；完整新报告Run为COMPLETED。四个实际历史A/D ZIP在当前版本离线重放PASS，计数/assessment比较明确NOT_AVAILABLE_LEGACY_REPORT，未升级旧报告。本轮任务4/5实现和完整验收通过。
- Git：fix/rpc-log-evidence-attribution基于328a712；代码提交5a83358及收集修复1b54cdf均已push，PR **#6** 的base为main、head为本任务分支。最终文档单独提交；最新head CI、合并SHA及分支清理结果以PR/Git历史为准。仅在全部检查成功、无冲突/required reviewer及base/head正确时按已有授权合并，再安全同步main并删除本任务分支。
- Limitations/Next：旧规则4报告保留原语义，纠正评价需新规则重新测量；工程分不是校准概率，离线复核不证明采集者诚实，纯写缺安全availability样本仍PARTIAL，仅覆盖现有受控协议/EVM ABI。Windows本机Docker/WSL限制由真实Linux Compose CI单列验收。本轮到任务5停止，不开发任务6、Agent扩展、第三方接入或前端。

## 2026-10-10 / 本轮任务 4：正式三维评价

- Implemented：formal-evaluation-v1 按互斥 purpose 冻结完整样本；A=0.8有效响应率+0.2及时率，B=各声明能力等权(0.2映射+0.8功能通过率)，T=已接受且可判定正向独立任务正确率。沿用 policy-v1 的20/10/10、覆盖80%、Q60%、TTL86400、写入30/40/30及只读35/65权重；任务成功率独立输出。缺样本、必要类别或声明覆盖继续PARTIAL/overall=null。
- Evidence/version：capabilities@3/rule3/three-dimensional-v1/ReportCore1.2；原始HTTP、首次HTTP、实际负例payloadhash、逐槽统计依据进入CAS与ZIP。Verifier逐任务重判并重算三维分数；旧1.0/1.1不升级，旧双null仍UNKNOWN。policy-v1内容hash固定，不允许同名改规则。
- Tests：单元/reference **292 passed**；真实 PostgreSQL/HTTP/Anvil正式评价与报告组合 **12 passed / 0 skipped**（766.20s）；Review修复真实回归 **3 passed / 0 skipped**（117.93s）。Ruff、mypy53files、54生成Schema通过。尚未执行本轮最终全量检查/CI，留待任务5完成后统一验收。
- Review fixes：首响应不被重试覆盖；同ID冻结材料冲突拒绝；真实来源类别缺失保持UNKNOWN；未确认/非canonical证据不能创建关键冲突；接受负例必须FAIL；ACK丢失保持UNKNOWN且不重发；连续过期槽位同步操作导致heartbeat饥饿，改工作线程并复用HTTP客户端；报告评分在最终fenced写入前组装。两项短租约真实测试验证执行/慢评分不会阻塞heartbeat。成功率及rule3增加模型不变量。
- Git：feat/formal-evaluation；阶段4提交de8fe94；未push，未创建PR。
- Limitations：纯写声明缺安全只读可用性来源则PARTIAL；只覆盖既有受控协议及EVM ABI；离线复算不证明采集者诚实。任务5、最终全量及CI仍未验收。
- Next：严格进入FOLLOWUP-05；本轮不开发任务6、Agent扩展、第三方接入或前端。

## 2026-10-10 / 本轮任务 5：充分度与关键风险

- Implemented：ReportCore1.3/evidence-assessment-v1记录每维度及每声明能力有效样本、适用计划/UNKNOWN或unresolved/N/A、声明映射/覆盖、必要类别、新鲜度及缺口；全部gate以精确Fraction判定。最大unresolved20%是原coverage80%的补数；保留20/10/10、Q60%、TTL86400及整秒计龄，不新增阈值。首次HTTP可判定时平台RPC故障不扣A。
- Risks：仅独立重判critical FAIL断言形成关键风险并携带slot/assertion/rule/reason/证据引用；普通履约FAIL与UNKNOWN缺口分列。风险独立于数值和充分度，高分或PARTIAL均保留confirmed critical并否决接入建议，不推断恶意。优先级与版本兼容见ADR0015。
- Verifier/compatibility：显式按1.0/1.1/1.2/1.3重建，历史字段/wire/hash不升级；1.3比较完整充分度及风险，旧报告assessment_comparison明确NOT_AVAILABLE。重新计算全部hash后篡改充分度、风险结论/引用/版本也会拒绝。
- Tests：稳定单元/reference **314 passed / 0 skipped**（53.03s）；正式正常写入和真实无关成功交易风险 **2 passed**（331.41s）；真实拒绝RPC导致全任务UNKNOWN但A10000/无风险/原UNKNOWN冻结 **1 passed**（212.56s）。高分9480且critical、PARTIAL且critical、缺样本/覆盖、20%UNKNOWN边界、显示6000bp但exact Q不足、1.2不升级、重hash篡改均通过。Ruff、mypy53files、57Schema/TS生成通过。
- Review fixes：新增充分度与原scoring_reference门槛一致性guard；N/A按维度与能力排除但未测声明不消失；超长/空原始声明不因报告解释文本拼接而崩溃，保持原上下文UNKNOWN；risk必须与重判critical断言引用一致。两轮跨模块Review继续检查最终稳定树。
- Git：阶段5提交6ffa5fe；最终完整scripts/check.py及远程PR/CI尚未通过，不声明最终验收通过。
- Limitations：工程指标不等于校准信任概率；关键风险沿用已接受写任务关联冲突，读取答案错误作普通功能失败；纯写无安全availability来源仍PARTIAL；离线复核不证明采集者诚实。
- Next：跨模块最终Review → 全量检查 → PR/CI；本轮到任务5验收后停止。

## 2026-10-10 / 任务 4–5 最终 Review 修复

- Review：补齐写任务返回chain_id/executor/record_hash与任务约束的核验，返回tx_hash与冻结RPC候选不一致为UNKNOWN/EVIDENCE_INCONSISTENT。只有可信HTTP、链身份、canonical/finality和成功回执确认后，错误返回字段才形成关键风险；回滚保持普通失败。畸形RPC日志容器或成员保持UNKNOWN，不能保留未经可信链证据支持的critical。
- Version：新正式计划使用capabilities@4/rule4/ReportCore1.3；既有@3在途任务显式冻结为1.2，历史1.0/1.1/1.2不升级。独立Verifier双向校验报告/模板/规则版本。
- Tests：最终稳定单元/reference **340 passed**（38.46s）；新正常正式写入与旧@3在途冻结/导出/离线复核真实PostgreSQL/Anvil **2 passed / 0 skipped**（329.21s）。三组核心回归 **106 passed**，Verifier **55 passed**；Ruff、mypy53files、57Schema/TS生成通过。两名独立Review代理复查无剩余阻断。
- CI：quality超时由15改为25分钟，新增真实正式评价的固定窗口约721秒，另需原有测试和工具安装/构建；未跳过测试、未放宽评分或验收门槛，Compose超时不变。
- Full check：第一次scripts/check.py在pytest阶段因发现写结果漏检主动停止，明确记为NOT_PASS；接下来必须在稳定提交重新执行全量检查，不复用中断结果。
- Git：feat/formal-evaluation基于fetch核实的最新origin/main=499ef56351d8672a105cea8a67ca194caff63a9e；最终修复待提交，push/PR/CI待完成。本轮仍停止在任务5。

## 2026-10-10 / 任务 4–5 最终验收

- Scope：任务4 → 阶段测试/Review修复 → 任务5 → 阶段测试/Review修复 → 跨模块Review → 完整验收均完成。三维得分、已判定任务成功率、充分度和关键风险独立输出；保持policy-v1原公式、权重与门槛。新报告1.3/规则4可从冻结原始证据重算；历史版本与@3在途任务保持原语义。没有新增依赖、DB migration、Agent扩展、第三方适配器或前端功能。
- Main files：core模型、record_verifier/reporting；platform evaluations/execution/verification/reports；独立verifier/bundle；同源生成Schema/OpenAPI/TS；测试与ADR0014/0015、CAPABILITY_TASKS。同步DB/签名/客户端初始化在线程中执行、客户端按run复用，报告计算在短fenced写入前完成，租约与fencing不放宽。
- Local full check：在稳定提交 **2379a039475984b7c9d1f7c1413a8a34b6d2f52c** 运行 `. ./scripts/tools.ps1; uv run --env-file .env --all-packages python scripts/check.py`，**退出0**。完整Python **447 passed / 0 skipped / 2 warnings**（2247.86s），包含真实PostgreSQL/Anvil/HTTP及M1恢复、冻结、发布、复核回归；Ruff、Mypy53源文件、57Schema、生成TS无漂移通过；Web typecheck/build和 **2 tests passed**；Foundry **14 passed / 0 failed / 0 skipped**，含256次fuzz；三份编译ABI检查通过。两条既有Starlette/httpx与websockets弃用警告未隐藏。
- CI：PR **#5**，base main、head feat/formal-evaluation；Foundation CI run **37967395116**、代码head **2379a039475984b7c9d1f7c1413a8a34b6d2f52c** completed/success；foundation-quality与foundation-compose均SUCCESS。CI实际Python **447 passed / 0 skipped**（869.28s）、Web2、Foundry14（256fuzz）、Schema/TS/ABI全部通过；Compose实际build/迁移/运行时smoke/独立worker通过。验收文档提交后仍须核对最新head的全部CI成功再合并，不复用旧head作为合并许可。
- Review fixes：首次HTTP不可被后续响应覆盖；来源/材料冲突拒绝；负例实际payload绑定、ACK丢失保持UNKNOWN且不重发；RPC/非canonical/未最终确认材料不能创建critical；同步操作阻塞heartbeat已修复；成功率与分母模型不变量；写返回字段漏检与畸形RPC日志误报；新旧规则和在途报告版本配对。阶段及最终定向回归均重新通过，独立跨模块Review无剩余阻断。
- Historical replay：最终稳定版本重新离线复核local-chain与local-chain-v2的A/D四个实际历史ZIP均PASS；assessment_comparison明确NOT_AVAILABLE_LEGACY_REPORT，未升级历史报告。最终340单元/reference、2真实新旧版本回归和完整447项通过的证据不替代彼此；首个中断全量结果仍NOT_PASS。
- Git：阶段提交de8fe94、6ffa5fe、最终修复2379a03均已推送预期origin；工作树在全量检查后干净。验收文档单独逻辑提交，最终head/合并SHA以Git历史和PR为准。仅在latest-head CI全通过、无冲突、无required reviewer、base/head正确时按已有授权合并，安全同步main并删除已完成分支。
- Acceptance：本轮任务4/5达到本地及代码CI验收要求，无已知实现阻塞。限制仍为当前受控协议/EVM ABI、纯写缺安全availability证据保持PARTIAL、工程指标不是校准概率、离线一致性不证明采集者诚实；Windows本地Docker WSL限制由真实Linux Compose CI单列验收。**停止，不开始任务6。**

## 2026-10-09 / 本轮任务 1：三能力模板

- Implemented：共享 Task/Worker/Verifier 支持 get_tx_status、verify_record、anchor_record；查询固定块、指定参数及独立 RPC 对照；只读无执行绑定或业务广播；授权目标合约可独立选择，冻结代码 hash。
- Files changed：core models/record_verifier/reporting、platform application 与 EVM collector/record、受控 fixture、共享 Schema/OpenAPI/生成 TS、CAPABILITY_TASKS 与 ADR 0011。
- Tests：单元/reference 127 passed；真实 capabilities/reports/verification/execution 组合 35 passed / 0 skipped（339.59s）；固定块后写入不改变历史查询补测 1 passed（16.87s）。Ruff、mypy 52 files、52 Schema 与 diff check 通过；历史 M1 A/D bundle 离线复核 PASS。
- Review fixes：只读 report settlement、read profile 的 behavior=None、RPC null/null 不误作不存在、非 canonical/错误定位/确认不足不扣 Agent、历史块查询边界。
- Git：分支 feat/capabilities-task-replay，任务 1 提交 6f741c9；尚未 push。本轮完整稳定树检查与 CI 待全部 1–3 完成后执行。
- Limitations：每 run 一个能力槽位；当前复用既有 EVM ABI，未加第三方协议适配器。保留 M1 PARTIAL，未开发完整三维评分、前端或 ERC-8004。
- Next task：任务 2 四态结果与失败归因。

## 2026-10-09 / 本轮任务 2：四态与原因

- Implemented：复用 Outcome/Reason，新增证据驱动服务失败、业务失败、证据不一致和规则版本原因；新模板/断言规则为 v2，旧 v1 序列化兼容；预评审排除能力可 NOT_APPLICABLE，已声明支持不得排除。
- Tests：172 单元/reference passed / 0 skipped；任务归因纯单元 45 passed；真实 PostgreSQL/Anvil 归因、能力、核验、报告、执行组合 54 passed / 0 skipped（818.07s）；Ruff、mypy 52 files、52 Schema 通过。保留两条 Starlette/websockets 弃用警告。
- Review fixes：授权/派发/endpoint 不一致不能将 HTTP 500 算 Agent FAIL；畸形 HTTP status 和声明数组不能崩溃；Agent 服务错误不被后续 RPC 故障遮盖；链上可证实回滚使用 TX_REVERTED；派生响应与冻结原始 HTTP 不一致为 UNKNOWN；损坏 RPC 证据降为 UNKNOWN。补全 NOT_APPLICABLE 不派发、不读任务 RPC且可冻结/导出；早期 RPC UNKNOWN 可以按原判定冻结，后续链恢复不会重写原任务结果；M1 专属 suite 不接受排除的 anchor 能力。
- Compatibility：旧 v1 reason 与默认 wire serialization 保留；新增状态、原因、原始 HTTP envelope 和 rule_version 进入已有 Evidence Bundle/CAS；Schema/OpenAPI/TS 由共享类型生成。
- Limitations：非法 JSON 被安全出口拒绝，因无法保留可靠脱敏原文，保持 UNKNOWN。报告发布仍需可信链上下文；全任务独立复核在下一项实现。
- Git：阶段 2 Review 后提交 854610d，JSON null 边界补测提交 1d88cc7；尚未 push。

## 2026-10-09 / 本轮任务 3：证据驱动逐任务复核

- Implemented：ReportCore v1.1 冻结逐任务 outcome/reason/rule version 和四态计数；`task-replay-v1` 索引绑定计划槽位、原始输入、冻结输入及 Agent HTTP CAS。独立 Verifier 从这些输入调用现有纯规则逐项重判，重算断言、任务结果和四态计数，并重建报告统计/评分字段；不访问平台数据库/API、不重调 Agent。操作者可用 `--task-rpc-url` 另查任务链状态，失败只报告为平台 RPC UNKNOWN，不覆盖离线重判。
- Compatibility：`@2` + ReportCore 1.0 + 旧单任务索引仅作为本轮前已冻结报告的兼容格式；继续重判并返回计算计数，但明确输出 `task_count_comparison=NOT_AVAILABLE_LEGACY_REPORT`。新报告必须 `@2` + ReportCore 1.1 + `task-replay-v1`，否则以规则版本错配拒绝。当前 report builder 只支持每 run 单槽位；Verifier 拒绝多槽位 bundle，避免在未重建全报告统计时误报 PASS。
- Tests：阶段 Verifier/四态/报告契约单元组合 **74 passed / 0 skipped**；真实 PostgreSQL/Anvil A/D 报告导出、离线逐项复核及独立任务 RPC 复查 **2 passed / 0 skipped**（3 个其他报告用例 deselected）；旧 `runtime/local-chain` 与 `local-chain-v2` 的 A/D 四个真实 ZIP 也均离线复核通过，A 为 PASS，D 为 FAIL/SEMANTIC_MISMATCH。最终稳定树完整检查及 CI 已通过，实测结果见下节。
- Review fixes：补齐模板、ReportCore schema 与索引格式双向配对，拒绝移除 v1.1 任务摘要或降级索引；拒绝当前模型不支持的多槽位报告；NOT_APPLICABLE 跳过非必要链 RPC；损坏的原始 HTTP CAS 不再导致报告冻结异常崩溃，缺少匹配内容时明确拒绝冻结。修复一次 Ruff 导入排序。
- Final review：真实 NA 导出后复核首先复现 **1 failed**（CAS 去重复用原输入 ID）；已修复同 ID 来源兼容，并增加冻结 RPC 重判/未恢复错误/时间顺序、v2 结算原因及在线链身份一致性校验。相关单元组合 **101 passed / 0 skipped**（10.22s）；真实归因报告导出复核 **4 passed / 0 skipped**（14 个其他用例 deselected，119.61s），覆盖 FAIL、UNKNOWN、NOT_APPLICABLE 及 RPC 恢复后的原 UNKNOWN 保留。全量检查早期在 pytest 阶段因该 Review 问题主动中断，不记通过；修复稳定提交后重新运行。
- Limitations：旧格式报告没有冻结任务计数，无法声称与原报告计数比较；无可信 RPC 时结果证明冻结证据与版本化规则内部一致，不单独证明原始采集者诚实或当前链状态。在线复查是可选的，RPC 来源只接受操作者配置。本轮未实现三维评分、前端、ERC-8004 或第三方协议适配器。
- Git：分支 `feat/capabilities-task-replay`；任务 3 提交 b724f04，最终 Review 修复提交 dc6d974；已 push 并建立 upstream，PR #4 的 base 为 main，CI 通过。合并与最终分支状态以 PR/Git 历史为准，遵守最新 head 检查通过后合并的仓库规则。
- Next task：FOLLOWUP-04/三维评分保持未开始；按用户要求本轮到任务 3 后停止，等待下一轮指令。

## 2026-10-09 / 本轮 1–3 最终验收

- Scope：三能力输入/输出/断言、四态与标准原因、证据驱动逐任务重判及计数比较全部完成；继续复用 M0/M1 架构，无新依赖、协议适配器或完整评分模块。主要修改为 core 模型/规则/reporting、platform 执行/采集/报告、fixture Agent、verifier/CLI，契约同步生成，设计见 ADR 0011–0013。
- Local command：在 dc6d974 干净稳定树运行 `. ./scripts/tools.ps1; uv run --env-file .env --all-packages python scripts/check.py`，**退出码 0**。Ruff 通过；Mypy 52 个源文件通过；54 份 Schema 与生成 TS 漂移检查通过；完整 Python **314 passed / 0 skipped / 2 warnings**（1198.25s）；Web build 通过、**2 tests passed**；Foundry **14 passed / 0 failed / 0 skipped**，含 256 次 fuzz；三份编译 ABI 检查通过。两条警告来自既有 Starlette/httpx 与 websockets 弃用提示，未为本轮升级依赖。
- CI：PR #4，head dc6d974bc1f3efc57e7434e6425c7e7776854159，Foundation CI run **37934736082** completed/success；`foundation-quality` 与 `foundation-compose` 均 SUCCESS。质量日志实际 Python **314 passed / 0 skipped**（187.34s）、Web **2 passed**、Foundry **14 passed / 0 skipped**；Compose 的 Docker build、runtime smoke 与 Worker once 均通过。PR 为 MERGEABLE/CLEAN，reviewDecision 为空；未修改保护或权限配置。
- Review：每项完成后定向回归及自审，最终交叉 Review 又修复 CAS 去重误拒 NA、冻结链观测未重判、冻结时间缺约束、v2 结算原因未绑定与错误链在线误确认。修复后组合单元 **101 passed**、真实归因导出复核 **4 passed**；最终完整回归通过。稳定修复后的四个历史 A/D ZIP 再次离线通过，旧报告计数比较明确标为 NOT_AVAILABLE_LEGACY_REPORT。
- Acceptance：本轮任务 1–3 满足验收，无已知阻塞。保留每 run 单槽位、既有 EVM ABI 和旧报告没有冻结 task counts 的明确限制；离线结果证明材料内部一致，链状态需操作者可信 RPC。FOLLOWUP-04、三维评分、前端、ERC-8004 与其他后续功能未开始，停止等待下一轮指令。

## 2026-10-02 / M0-01

- Implemented：Git/认证/目录审查；启动包 44 项 manifest 校验；安全 clone、fetch 和功能分支；规划 overlay；README 语义合并；保留 Ponytail 约束。
- Files changed：AGENTS、PLAN、README、docs、scripts、configs、core 评分参考、fixtures golden、reference tests、Git 模板。未复制启动包外层、ZIP、验证日志或安装器。
- Commands executed：git rev-parse/status/remote/branch/log、工具版本检查、gh auth status/login、git ls-remote、gh repo view、git clone、git fetch origin --prune、git switch -c、install_plan --dry-run / --on-conflict sidecar。
- Tests：启动包 SHA-256/size 校验 44/44；安装 dry-run 退出 0；py -3 scripts/check_bootstrap.py 退出 0、36/36 通过；git_doctor 退出 0 / REMOTE_MATCH；git diff --check 通过。
- Known limitations：安装的是规划和评分参考，不能据此声明 M0/M1 完成。Docker/Compose、Foundry/Anvil、PostgreSQL 尚未找到；uv 待安装。
- Blockers：先前 BLOCKED_EXTERNAL_AUTH 已解除；当前没有需要用户介入的阻塞。
- Branch：feat/foundation-m0-m1。
- Commit SHA：基线 e9430d186d7c63ddc8e2da2d70231ccb4873c8b1；启动基线提交 0903f76；36 项参考测试通过。
- Push status：NOT_PUSHED。
- Decisions：以用户明确分支名为准；API 使用 BACKLOG/spec 的 /api/v1；M0 卡片编号以 BACKLOG 为准。
- Path migration：6 处旧项目路径和 2 处父目录/启动包示例已迁移；无业务绝对路径；无故意保留的旧引用；仅修改两份 Markdown。
- Next task：M0-02：隔离安装并锁定工具链、建立真实 workspace。

## 2026-10-02 / M0-02

- Implemented：四个可安装 Python 包及依赖方向；uv.lock、pnpm-lock.yaml 实际解析；Vue 平台连接页；Foundry 工作区及协议版本；项目级工具安装脚本和 doctor 命令。
- Files changed：根 pyproject/.python-version/uv.lock；四包 pyproject；CLI；apps/web；contracts；scripts/tools.ps1；configs/toolchain.json；workspace tests；ADR 0002。评分参考只将歧义变量重命名，公式不变。
- Commands executed：隔离 venv 安装 uv 0.9.3；官方 Foundry 1.8.4 下载并验证 SHA-256；uv lock；uv sync --locked --all-packages；独立空环境再次 sync；四包 import；pytest；ruff；mypy；pnpm install --frozen-lockfile/build/test；forge build/test。
- Tests：空环境锁定安装与四包 import 通过；pytest 38 passed；ruff 通过；mypy 4 source files 通过；Vue typecheck/build 通过、2 tests passed；Solc 0.8.30 build 通过、Foundry 1 passed。
- Known limitations：当前合约测试只证明工作区可运行，不是 M1 合约验收。API/DB/worker/复核器尚未实现；Docker/Compose 尚未安装，容器镜像锁和运行验证归 M0-05；PostgreSQL 官方便携包下载中。
- Blockers：无用户阻塞；Docker 条件待 M0-05 处理。
- Branch：feat/foundation-m0-m1。
- Commit SHA：仓库基线 0903f76；路径迁移 e72b039；本任务待提交，下一任务记录实值。
- Push status：NOT_PUSHED；将在基础检查通过后推当前功能分支。
- Next task：M0-03 共享领域契约、Schema 和生成类型。

## 2026-10-02 / M0-03

- Implemented：身份/快照/声明/双签绑定/grant/run/slot/observation/assertion/task-link/report/receipt；严格地址、uint256 字符串、UTC 毫秒时间、整数基点；四态及原因码；静态协议注册表和 ports；JCS 与 Ethereum Keccak 公用函数；API 输入契约；由 DTO 生成 JSON Schema/OpenAPI components/TS。
- Files changed：core/models、evidence.py、ports.py、registry.py；schemas/generated；scripts/generate_schemas.py；web generated types；domain 示例；tests/unit/test_contracts.py。
- Commands executed：pytest -q；ruff check；mypy；generate_schemas / --check；pnpm generate:types；pnpm build。
- Tests：79 passed；ruff 通过；mypy 8 source files 通过；33 份 Schema 验证和重新生成无漂移；TS 类型检查及 Vue build 通过。初次新增测试导入了不存在的 evaluate，已修正为实际 evaluate_from_stats，完整重跑通过。
- Known limitations：OpenAPI 此时只有类型，没有声称路由已实现；M1 task DTO 只执行 anchor_record；其他能力的完整任务适配属于 M2。哈希一致性不代表链上真实性。
- Blockers：无。PostgreSQL 17.11 便携二进制已成功运行 --version；数据库迁移和队列尚待 M0-04。
- Branch：feat/foundation-m0-m1。
- Commit SHA：M0-02 a0a0ed1；当前任务提交待生成。
- Push status：a0a0ed1 已成功推送 origin/feat/foundation-m0-m1；未推 main。
- Next task：M0-04：真实 PostgreSQL 模型、迁移、租约与 fencing 验收。

## 2026-10-02 / M0-04

- Implemented：SQLAlchemy 关系表与 JSONB 文档；Alembic 单一冻结迁移；FK/唯一/check 约束；append-only 触发器与 run plan 不可变；原子保存 plan/slot/job；SKIP LOCKED、租约、单调 token、heartbeat、重试上限、带 fencing 的事务写回。
- Files changed：platform/infrastructure/db、migrations、alembic.ini、CLI migrate、local_postgres.py、tools.ps1、真实 DB 测试、共享测试工厂和 py.typed 标记。参考测试仅格式整理，评分参考只显式收窄已判定值的类型。
- Commands executed：initdb；pg_ctl start；alembic upgrade head/current/check；空测试库 downgrade base → upgrade head；reputation migrate；pytest；ruff；mypy；check_bootstrap。
- Tests：87 passed（包括 8 个真实 PostgreSQL 集成测试）；mypy 19 source files 通过；ruff 通过；reference 36/36 通过；Alembic head=6aa7efd8cbc4，无模型漂移。
- Known limitations：队列层恢复已验证；跨 HTTP/链的业务恢复仍需 M1。开发数据库管理员可关闭触发器，这属于信任边界。Compose 尚未验证，M0 不能整体标完成。
- Windows fix：原生 initdb 在中文绝对路径下出现 UTF8 错误；脚本动态选择空闲盘符映射至同一 runtime 目录（当前 R:），未复制/移动项目。重试初始化成功。数据库仅 loopback:55432，UTC 会话；随机凭证只在被忽略文件。
- Failures resolved：新增测试导入路径修复为 pytest pythonpath；已有参考测试格式问题已整理；mypy 改用包名检查并添加 py.typed，修复 Optional Fraction 收窄，不改变规则。
- Branch：feat/foundation-m0-m1。
- Commit SHA：M0-03 f2ba3ac；当前任务待提交。
- Push status：远端已到 a0a0ed1；后续提交待推送。
- Blockers：无用户阻塞。WSL 2.7.3 可用，正在下载签名官方 Docker Desktop，准备 M0-05 per-user 安装和 Compose 验证。
- Next task：M0-05 安全网络、认证 API/worker 与本地编排。

## 2026-10-02 / M0-05 实现与原生验收

- Implemented：随机本地凭证、恒定时间 bearer 认证、结构化错误与 request ID；真实 DB readiness/候选注册/查询；共享输出 DTO 和真实路由 OpenAPI/TS；精确受控出口、无代理/跳转、大小/深度/压缩限制；独立 worker 的心跳、失租取消、有限重试；隔离 Compose 网络和 digest 固定镜像。
- Files changed：api、worker、network、init_local、Dockerfile/compose/env.example、schema generator/生成契约、worker/API/network tests、LOCAL_RUNTIME runbook、工具链记录。
- Commands executed：pytest -q；ruff check；mypy 四包；generate_schemas / --check；pnpm generate:types/build/test；真实 uvicorn HTTP live/ready；docker compose config --quiet；buildx imagetools inspect 四个基础镜像。
- Tests：107 passed；ruff 通过；mypy 25 files 通过；35 份契约无漂移；Vue build/typecheck、2 tests 通过；真实 HTTP health 通过；Compose 配置解析通过。Starlette TestClient 提示 httpx 将弃用，当前测试通过，无隐藏跳过。
- Known limitations：M0 worker 只有经过集成测试的调度器，M1 业务 handlers 尚未接入；本地 Docker 引擎尚未启动，不能宣称容器验收通过。公网 HTTP 禁用。
- Blocker：Docker Desktop per-user 安装成功，WSL import-in-place 报 Wsl/ERROR_PATH_NOT_FOUND；VHD 文件存在且原有发行版可运行。未修改/注销用户发行版；继续原生验证与 Linux CI，不以此阻断独立开发。
- Branch：feat/foundation-m0-m1；M0-04 commit 5f67ac8，已推送；本任务待提交。
- Next task：M0-06 CI，完成容器构建/启动验证；M0 总体仍待验收。

## 2026-10-02 / M0-06

- Implemented：foundation-quality 与 foundation-compose 两个固定 CI check；actions 固定真实 commit，contents:read，不注入生产凭证；完整 check.py、真实 HTTP/RPC smoke、禁止跳过测试的 CI gate。
- Files changed：.github/workflows/ci.yml、scripts/check.py、scripts/smoke_runtime.py、tests/conftest.py。
- Commands executed：uv run --all-packages python scripts/check.py（退出 0）。
- Tests：107 Python passed / 0 skipped；ruff、mypy 25 files、35 schema、生成 TS 无漂移；Vue build 和 2 tests；Foundry 1 passed / 0 skipped。
- Known limitations：远端 Actions/Compose 尚待执行；本机 WSL 引擎问题独立记录，未将 mock 视为容器验收。
- Branch：feat/foundation-m0-m1；M0-05 commit 6ceb06a；当前任务待提交/推送。
- Next task：检查真实 CI，修复失败；M0-07 固定可取得的上游资料。

## 2026-10-02 / M0-07

- Implemented：读取官方 master 当前 commit b9e466c250744a7e06b13dff9d3c2844ed64f825；保存原始 Identity ABI、含 CC0 声明的 README 和官方 EIP 页面；真实字节数/SHA-256/来源登记；外部接入仍 disabled。
- Files changed：configs/upstream-lock.json、third_party/erc8004、tests/unit/test_upstream.py。
- Commands executed：gh api repo/commits/tree；官方 raw/EIP/OpenAPI HTTP GET；pytest 上游字节/接口/禁用状态校验；ruff。
- Tests：1 passed；ruff 通过。远端 ecaf110 的 foundation-quality 已通过，Compose smoke 正在运行。
- Known limitations / Blockers：8004scan OpenAPI HTTP 403 → BLOCKED_DOWNLOAD；没有生成假 hash/文件。没有公网 RPC 部署核验，usable=false。上游无独立 LICENSE 文件，实际许可声明在已保留 README。
- Branch：feat/foundation-m0-m1；M0-06 ecaf110 已成功推送；当前任务待提交。
- Next task：收尾 M0 CI 运行验证，然后 M1-01 三个真实演示合约。

## M0 运行回归与修复

- Windows 原生 `python scripts/smoke_runtime.py` 退出 0：API DB readiness、Vue 代理、未认证 POST=401、真实 Anvil chainId=31337 全通过。
- CI ecaf110 / f2df4ca 的 quality 均通过；Compose 构建/迁移/API 内部健康通过，但宿主入口失败，未隐藏失败。
- 定位：只连接 internal bridge 时未生成 published ports。新增仅 API/web/Anvil 的 ingress bridge，仍绑定 127.0.0.1；数据库/worker/fixture 保持内部，ADR 0003 说明信任边界。
- 同时修复非 ASCII bearer token 导致 compare_digest 异常的边界；3 项真实 API 集成测试通过。
- 上游原始文件设置 -text/-diff，防止 Windows checkout 改换行后破坏 SHA-256；源文件空白属于原文，未为 lint 修改原始字节。
- 当前修改容器验证待重跑；此前提交 f2df4ca 已推送。

## M0 验收完成

- GitHub Actions run 37017699537（commit ecb8ba5）：foundation-quality=success，foundation-compose=success；容器真实构建、迁移、宿主 API/web proxy/认证/Anvil smoke、独立 worker CLI 均通过。
- Windows 原生平台健康链路已通过；Windows Docker Desktop 的 WSL import 错误仍是已知环境限制，未声称本机 Docker 成功。可使用原生本地开发链完成 M1。
- 最后契约回归：AgentView 来源与数据库/SnapshotCore 共用 controlled/public_registry/replay，真实 API 测试覆盖受控来源；45 项 API+契约测试与前端 build 通过。
- M0-07 外部 OpenAPI 403 不阻塞 M1，所有公网接入继续禁用。
- Next task：M1-01：自研 Registry、RecordRegistry、EvaluationAnchor 及真实 Foundry 正反测试；不扩大 M2。

## 2026-10-02 / M1-01

- Implemented：owner/revision/instance 身份合约；executor+request 去重业务记录；明确 admin/evaluator 权限、前向 hash/序号、历史报告幂等发布；编译生成 ABI 和 CI 漂移校验；删除无业务引用的 ProtocolVersion 探针。
- Files changed：contracts/src/test/abi、generate_abis.py、check.py、ADR 0004。
- Commands executed：forge fmt/build/test -vv；针对构造失败测试执行 -vvvv 检查路径；generate_abis / --check；ruff。
- Tests：14 Foundry passed、0 failed/0 skipped；记录不可覆写 fuzz 256 runs；真实编译 ABI 校验通过。构造 revert 会结束整个测试，已拆独立用例以确保后续零字段/超长 URI 路径实际执行。
- Known limitations：尚未部署/seed；不能据此声称 A/D 或 M1 闭环已通过。测试中的 gas 是执行该测试的实测，不是生产调用基准。
- Full regression：scripts/check.py 退出 0；109 Python passed、mypy/ruff/35 Schema/TS 无漂移、Vue 2 passed/build、Foundry 14 passed、编译 ABI 无漂移。
- Branch：feat/foundation-m0-m1；M0 最终提交 f7981d2、M1-01 提交 48429f8 均已推送预期 origin；工作树干净。
- Next task：M1-02 本地部署、幂等 seed 与持久任务 Agent。

## 2026-10-02 / M1-02

- Implemented：受限本地部署与签名 setup outbox；六个独立随机角色；幂等 seed、真实 D 无关成功交易；受控 HTTP v1 服务；独立 SQLite 意图/nonce/signed bytes 账本、恢复和重放；共享公共部署/协议 DTO 与生成契约。
- Files changed：application/local_deploy/local_seed、CLI deploy-local/seed、fixture_agents/service、core/runtime DTO、生成 schemas/TS、smoke_agents.py、9 项链集成测试、ADR 0005 和运行说明。
- Commands executed：真实 reputation deploy-local、seed 两次；独立 uvicorn A:9101/D:9102；smoke_agents；停止并重启两个服务后 smoke_agents --recheck；pytest -q；ruff/mypy；Schema check；Vue build。
- Tests：118 Python passed（新增 9 项真实 Anvil：角色分离/重复 seed/HTTP 幂等/磁盘重开/签名后退出/广播后退出/nonce 并发/D 反例/真实 reset）；mypy 30 files、ruff、39 Schema、Vue typecheck/build 通过。保留 TestClient/websockets 弃用警告，无隐藏 skip。
- Live evidence：runtime/local-chain/protocol-smoke.json 保存真实 request/hash/tx/event；A 匹配、D receipt=1 但 request/hash 不匹配。服务重启后的原请求返回相同 txHash，A 仅 1 条相应事件，D 对当前任务 0 条事件。
- Known limitations：当前是 synthetic snapshot 的协议 smoke；不能称完整平台绑定/worker/报告/复核已完成。M1 fixture Compose 编排归纵向集成收尾，基础 Compose 已验证。私钥/账本/证据均在忽略 runtime，未提交。
- Branch：feat/foundation-m0-m1；实现提交 b8684a0 已推送；上一个 CI 29e4425 为 success，新代码 CI run 37021958255 已启动，结果待核实。
- Blockers：无当前实现阻塞；本机 Docker WSL 问题、8004scan 403 继续单列。
- Next task：M1-03 真实注册快照、人工映射确认与 owner/executor 双 EIP-712 签名绑定。

## 2026-10-02 / M1-03

- Implemented：固定真实区块的 demo reader；异步 ingest 快照；人工声明版本确认；随机单次 nonce 与 owner/executor 双 EIP-712 验证；当前身份核对/旧快照拒绝/合约账户 UNKNOWN；脱敏后 CAS 证据；API 与独立 worker 静态接入。
- Files changed：core binding/DTO、identity service/demo reader/evidence store、API/worker、生成 Schema/OpenAPI/TS、smoke_identity、ADR 0006 与运行说明。
- Commands executed：真实 PostgreSQL + Anvil pytest；ruff/mypy；Schema generate/check + TS generate；Vue build/test；forge test/ABI check；重启原生 API、独立 worker 进程运行 smoke_identity。
- Tests：135 Python passed（新增 16 身份链/数据库集成用例及 1 脱敏存储测试）、14 Foundry passed/0 skipped、2 Vue passed、40 Schema 验证、mypy 37 files、ruff、Vue typecheck/build 与 ABI 检查退出 0。首轮发现全零签名抛 BadSignature，已修复且回归通过。保留两项上游弃用警告。
- Live evidence：runtime/local-chain/identity-smoke.json 保存 A/D 真实 snapshot、review、binding 和 job 引用；两者 VERIFIED。签名发生在操作者脚本，API/worker 不读取 owner/executor 私钥。D 身份通过不表示 D 业务正确，后续需独立业务断言。
- Recovery/security：同 nonce 并发只有一个成功；提交快照后退出重领保留同一 snapshot_id；竞争 refresh 返回 SNAPSHOT_CONFLICT；已刷新旧版本不能新签；错误 Agent/endpoint/nonce/domain/role/signer/expired challenge 拒绝；敏感元数据拒绝且不保存。
- Compatibility：无需 DB migration；DTO 新增可选结果引用和挑战类型；JSON Schema/OpenAPI/TS 同源生成。未开启公网注册抓取。
- CI：前一提交 2119c0e 的 run 37022077859 已核实 success；本次 eea511a 的 run 37024611634 已启动，结果待核实。
- Known limitations：health readiness 当前仅检查 DB/migration；链配置/实例在身份操作时核验。M1 评价执行、报告、发布、独立复核及完整 Compose E2E 尚未完成。Windows Docker WSL 和外部 OpenAPI 403 仍单列。
- Branch：feat/foundation-m0-m1；M1-03 实现提交 eea511a 已推送预期 origin；本验收状态单独更新。
- Next task：M1-04 授权边界、预持久化任务计划、执行/重启 reconciliation；不降低评分门槛。

## 2026-10-02 / M1-04

- Implemented：最小受控 grant 与撤权；payload-bound Idempotency-Key；当前 snapshot/review/EOA binding 及授权窗口检查；一次 functional slot 的 CSPRNG 请求/合成数据/expected facts/初始 dispatch/job 原子保存；计划及发送前链见证；真实 HTTP 执行、固定路径查询、可信 RPC 记录恢复；仅明确未接受时原 id/payload 有限重投。
- Recovery/security：append-only attempts/observations/dispatch events；每次请求前授权与 lease fencing；跨 run 间隔、每 Agent active run 1、全局 evaluate 有效租约 2；取消未发送任务、已发送继续核对；撤权后禁止 Agent HTTP，仅可信 RPC 恢复；平台 RPC 失败保留 UNKNOWN，未实现健康窗口证明前不扣 Agent 超时分。
- Files changed：evaluation/execution service、RPC record reconciliation、API/worker/jobs、共享 DTO 及生成契约、smoke_execution、11 个新增用例、ADR 0007/运行说明。
- Commands executed：pytest 全量（FAIL_ON_SKIP=1）；ruff/mypy；44 Schema generate/check 与 TS generate；Vue build/test；Foundry/ABI check；重启原生 API/worker/A，执行真实 smoke_execution（包含重新绑定）。
- Tests：146 Python passed/0 skipped、14 Foundry passed、2 Vue passed、mypy 41 files、ruff、44 Schema、前端 build 与 ABI 校验通过。完整 pytest 282.45s。关键用例启动独立 worker，在真实 HTTP 返回后 os._exit(86)，新 worker 只 GET 原 request，链上仅一条记录；旧 lease 写回拒绝。另覆盖发送前退出、并发同 key、配额、取消/撤权、RPC 拒绝连接等。
- Live evidence：runtime/local-chain/execution-smoke.json 保存 A/D 的实际 run/grant/plan/observations，含各自候选 txHash；输出 IDENTITY_SMOKE_PASS 与 DISPATCH_SMOKE_PASS。候选尚未独立验证，因此两个 run 均不声称业务通过。
- Compatibility：无 DB migration；CaseSlot 新增可选 synthetic_input（有值则校验摘要），RunPlan 新增 planning_evidence_refs，EvaluationRun 增加 cancel_requested；Schema/OpenAPI/TS 已生成。全量 pytest 使用端口 9101，已在 runbook 明确停止/恢复 demo A。
- CI：M1-03 最新 ef5fede 的 run 37024686970 已核实 success；eea511a 的旧 run 因后续提交取消，并非失败。本次新代码 CI 待推送核实。
- Known limitations：独立业务断言/评分/报告/发布/复核和完整 M1 Compose E2E 尚未完成；当前 run 处于 VERIFYING，未有业务断言的 settled slot 仍记 unknown。Windows Docker WSL、外部 OpenAPI 403 继续单列。
- Branch：feat/foundation-m0-m1；M1-04 实现 8729af9 已推送预期 origin；CI run 37027935606 已启动、结果待核实。本验收状态单独更新。
- Next task：M1-05：保存可信 RPC 的 tx/receipt/block/log，并独立验证 request/hash/executor/target/instance/deadline/finality；必须得到 A PASS 与 D 无关成功交易 FAIL。

## 2026-10-03 / M1-05

- Implemented：受信 RPC 原始结果采集、共享回放输入、纯任务关联断言、追加式 TaskLink/断言和 verify worker 作业；目标字节码摘要及紧邻发送前链头校验；GET verification API；独立进程 smoke 脚本。
- Files changed：core/models/verification、record_verifier、adapters/evm/collector、application/verification、API/worker/execution/planner、48 份生成 Schema/TS、test_verification、smoke_verification、ADR 0008/运行说明。
- Commands executed：pytest -q -x（FAIL_ON_SKIP=1）；pytest -q -x tests/integration/test_verification.py；ruff/mypy；generate_schemas/generate:types；前端 build/test；forge test/ABI check；独立原生 API/worker/A/D 的 smoke_verification。
- Tests：定向首轮 6 passed / 1 failed，修正测试对正常 Agent 重复请求返回真实 revert 的错误预期后，预写成功交易另行独立采集并验证窗口。全量首轮 152 passed / 1 setup error（Agent 启动超过 30s）；只把进程启动等待调为 90s，业务窗口保持 60s，重跑 153 passed/0 skipped（414.60s）。补充独立回放校验平台实例 domain salt 后，相关 7 项测试再通过（156.72s），含真实 RPC 拒绝连接、另一 Anvil、不存在交易、错误执行者/目标的真实成功交易。ruff/mypy 45 files、48 Schema、前端 build/2 tests、Foundry 14 tests/ABI 校验通过。
- CI：已核实上次提交 3019352 的 run 37028009864 为 success；8729af9 的旧 run 37027935606 被后续提交取消。本次 391d2c9 已推送，新 CI 结果待核实。
- Live evidence：原生 API/worker 已加载新实现，A/D 已恢复；smoke_verification 退出 0，IDENTITY_SMOKE_PASS、DISPATCH_SMOKE_PASS、VERIFICATION_SMOKE_PASS。runtime/local-chain/verification-smoke.json 保存实际 run 和断言；A PASS，D receipt.success PASS 但 request/hash 不符，最终 FAIL/SEMANTIC_MISMATCH。未从 fixture 标签生成结论。
- Compatibility：无 DB migration；旧计划缺 target_code_hash 时 UNKNOWN，不追填旧计划；新增 4 个共享核验模型及平台实例 domain salt 校验。新增断言与 TaskLink 继续 append-only/fencing。
- Known limitations：M1-06/07/08 报告、存证、独立 bundle verifier、完整 E2E 尚未完成。未降低 policy 门槛。Windows Docker WSL 与外部 OpenAPI 403 仍单列；本次未声称本机容器通过。
- Branch：feat/foundation-m0-m1；PR 授权规则 794c681、M1-05 实现 391d2c9 均已推送预期 origin；本验收状态另行提交。整项 M0+M1 尚未完成，尚未创建最终 PR。
- Next task：M1-06：从槽位/观测/独立断言派生统计，冻结 PARTIAL/overall=null 报告及无循环承诺的证据包。

## 2026-10-03 / M1-06

- Implemented：纯规则重新执行任务断言并派生互斥目的统计；复用原 policy-v1/scoring_reference，保持20/10/10与80%/60%门槛，mapping不因人工确认默认正确；PARTIAL/overall=null，D保留关键冲突建议。report worker 在冻结前再查链上证据与实际 Anchor head；短事务 fencing/advisory lock、同run幂等、前一报告未发布时拒绝竞争previous；CAS/manifest/ReportCore无循环承诺、稳定ZIP导出、真实源码版本。
- Files changed：core/reporting 与4个共享报告类型、application/reports、API/worker/verify入队、52份生成Schema/TS、smoke_reports、报告集成/manifest边界测试、ADR0009及运行文档。没有DB migration。
- Commands executed：ruff/mypy；Schema generate/check、TS generate；pytest报告定向及全量（FAIL_ON_SKIP=1）；前端build/test；forge test/ABI check；原生新版API/worker的smoke_reports。
- Tests：5项真实PG+Anvil报告集成通过（121.72s）；全量166 passed/0 skipped（591.52s）；mypy48 files、ruff、52 Schema、Vue2 tests/build、Foundry14 tests及ABI检查通过。覆盖A/D部分报告、完整文件承诺、固定JSON顺序与ZIP字节、真实密钥不出包、双作业仅一份revision且均成功、报告提交后作业ACK前中断恢复、旧lease拒绝、CAS修改/丢失拒绝。manifest另有8项循环和非可移植路径拒绝测试。
- Live evidence：smoke_reports退出0，runtime/local-chain/report-a.zip（131066 bytes）及report-d.zip（131661 bytes），各132成员；report-smoke.json记录真实report_id/hash。A为PARTIAL/INSUFFICIENT_EVIDENCE，D为PARTIAL/NOT_RECOMMENDED，两者overall=null、回执NOT_REQUESTED。源码存在未提交实现时正确标记-dirty，没有声称来自干净release。
- Runtime：原生API/worker已加载报告实现；全量测试期间A/D停止，完成后恢复。报告smoke复用已核验任务，不重新执行Agent写入。已冻结的本地A/D报告应在M1-07继续发布；不要新建竞争previous的未发布报告。
- Known limitations：发布outbox、真实锚定和独立ZIP verifier尚未实现；导出成功不等于独立复核通过。无Git部署需配置实际CODE_VERSION，完整Compose/E2E收尾归M1-08。本机Docker WSL与外部OpenAPI403仍单列。
- CI/Git：上一阶段b04a04a的run37033866824核实success；391d2c9旧run被后续提交取消。本次实现3f052d3已推送feat/foundation-m0-m1至预期origin，暂存diff/实际密钥/大小检查通过，新CI待核实。本验收状态另行提交；M1整体仍未完成。
- Next task：M1-07：持久签名/nonce后广播、unknown broadcast reconcile、独立安全ZIP与规则复算、可信配置下真实Anchor核验、篡改/换链测试。

## 2026-10-03 / LOCAL-PG-JUNCTION

- Implemented：按用户要求创建 `D:\web3-runtime` NTFS 目录联接，指向原中文项目的 runtime；local_postgres.py 自动创建/复用并验证同一目录，拒绝同名冲突和非 ASCII 入口。删除动态 subst 逻辑及未使用的 BIN 常量；原中文路径、文件、数据库凭证保持不变。
- Migration：切换前记录数据库 cluster system_identifier、26 张 public 表的行数和逐行内容 SHA-256；通过 pg_dump -Fc 保存 `runtime/backups/before-runtime-junction.dump`（135228 bytes，Git 忽略），pg_restore --list 验证可读。正常停库后通过目录联接重启；核对 R: 仍指向原 runtime 后移除该映射及 postgres-drive.json。移除 R: 后再次 stop/start/status 均退出 0，实际 postgres.exe/data_directory 均为 D:/web3-runtime 路径，未重新生成盘符。
- Commands/tests：用目录联接的 initdb 初始化唯一临时 cluster 成功并仅清理该临时目录；真实 psycopg SQL 连接/SELECT 1 通过；两次重启后的 cluster 标识及26张表全部行内容摘要均与切换前一致。`FAIL_ON_SKIP=1 .venv/Scripts/python.exe -m pytest -q tests/unit/test_local_postgres.py tests/integration/test_database.py tests/integration/test_api.py` 退出 0，13 passed/0 skipped（54.80s）。ruff check、ruff format --check 和 git diff --check 均退出 0。原有 Starlette/httpx、websockets 弃用提示仍存在。
- Files changed：scripts/local_postgres.py、tests/unit/test_local_postgres.py、README、LOCAL_RUNTIME、ADR0002、PLAN、STATUS。临时检查脚本和对比摘要保存在本次聊天 work 目录；备份仅在忽略的 runtime，未暂存凭证或数据。
- Git：从干净 2bcc6d6 创建本地短分支 `fix/postgres-runtime-junction`；本节与实现一起本地提交，实际 SHA 见 `git log -1`；NOT_PUSHED。用户此次授权为本地修复，未执行远程发布。
- Limitations/next task：目录联接在数据库运行期间保留；同盘另一个项目占用同名入口时会明确拒绝。此次仅验收本地 PostgreSQL 入口及相关 DB/API 测试，未重新运行全量链/前端/Compose 验收。下一业务任务仍为 M1-07，不变更原里程碑结果。

## 2026-10-03 / M1-07 + M1-08

- Implemented：`AnchorService` 通过 `anchor_jobs`/`signer_nonces` 持久化 nonce、signed transaction 和状态；广播异常按既有哈希 reconcile，回执追加到 `anchor_receipts`；新增报告/评价 anchor API 和 worker handler。`packages/verifier` 提供独立 `reputation-verify` CLI，安全读取 ZIP、核对全部 manifest/CAS、重放 `RecordVerificationInput`、重算断言/统计/评分，并在操作者 RPC 下核对链实例、交易、合约记录和确认深度。
- Tests：verifier path-traversal 单测通过；ruff、mypy、52 schema drift check 通过；冻结 `runtime/local-chain-v2` 上真实 PostgreSQL + Anvil + A/D 流程完成 identity、dispatch、verification、reports；`M1_ACCEPTANCE_PASS`：A/D 两个 bundle，A 真实 EvaluationAnchor CONFIRMED，离线 anchor `NOT_CHECKED`，可信 RPC online `CONFIRMED`，policy/blob tamper 拒绝。
- Live evidence：`runtime/local-chain-v2/report-a.zip`、`report-d.zip`、`report-smoke.json` 为忽略的本地运行产物；A/D 均 PARTIAL、overall=null，A 已发布。旧 `runtime/local-chain` 报告保留，未覆盖；新鲜链实例因旧 Anvil 已不可恢复而使用隔离 `local-chain-v2`，不把旧 bundle 描述为干净发行复现。
- Security：signed transaction、publisher secret、数据库凭据未进入 Git 或 bundle；verifier 不信任包内 RPC；无 RPC 不宣称链上成功；ZIP 拒绝路径穿越、重复/符号链接/高压缩比成员及未承诺文件。
- Limitations：本轮继续保留 Windows Docker WSL import 和 8004scan HTTP 403 单列；本地 M1 使用 Anvil，不代表公网最终性。M2 三能力完整评分未展开。
- Git：当前工作分支为 `feat/m1-07-m1-08`，包含之前保留的本地 PostgreSQL junction 提交；M1-07/M1-08 实现提交 `6c340b5`，状态提交、push、PR 和 required CI 仍待完成。
- Next task：M2（用户未授权扩展，本轮停止）。

## 2026-10-06 / WINDOWS-LOCAL-RUNTIME-SETUP

- Implemented：从私有 GitHub 仓库克隆 `main`；本机 Python、Node、pnpm、Foundry、PostgreSQL 与 solc 工具均安装在 Git 忽略的项目目录，不写系统 PATH、Python 注册表或全局包目录。
- Windows compatibility：本机 Hyper-V 排除 8534–9156 中的多个端口段，默认 8545/9101/9102 无法绑定。新增严格校验的 `LOCAL_RPC_URL`、`FIXTURE_PORT_A`、`FIXTURE_PORT_D` 覆盖；本机 `.env` 使用 18545/19101/19102，默认值和 Compose 内部端口不变。seed、注册元数据、受控 HTTP、测试和 smoke 共用相同配置；`smoke_agents.py` 同时尊重 `LOCAL_RUNTIME_DIR`。
- Runtime：PostgreSQL 17.11 运行于 127.0.0.1:55432；Anvil 运行于 127.0.0.1:18545，并每秒持久化到忽略的 `runtime/local-chain-v2/anvil-state.json`；API、worker、Vue、fixture A/D 已后台启动，PID 与日志位于 `runtime`。API/前端分别为 127.0.0.1:8000/5173。
- Tests：`uv run --env-file .env --all-packages python scripts/check.py` 退出 0；172 Python passed/0 failed、Ruff、mypy 52 files、52 Schema、生成 TS 无漂移、Vue build + 2 tests、Foundry 14 tests（含 256 fuzz）、3 ABI 全通过。仅保留既有 Starlette/httpx、websockets 弃用提示及受限 `.pytest_cache` 警告。
- Live acceptance：`LIVE_RUNTIME_PASS` 与 `PROTOCOL_SMOKE_PASS --recheck` 通过；此前同轮完成 `M1_ACCEPTANCE_PASS`，覆盖 A/D 真实调用、A PASS、D 成功回执但 SEMANTIC_MISMATCH、PARTIAL bundle、A anchor、离线/在线 verifier 和篡改拒绝。旧链运行产物保留在忽略的 runtime，未删除或伪装为当前链。
- Git：分支 `fix/windows-local-runtime-ports` 已推送；实现提交 `0855e03`、清理提交 `13db4fd`；PR #3：`https://github.com/Ryanjxy123/web3-agent-reputation/pull/3`。required checks 已触发，最终结果以 PR 页面为准。
- Next task：业务里程碑仍为 M2；本地环境任务完成，不扩大到公网或主网。
