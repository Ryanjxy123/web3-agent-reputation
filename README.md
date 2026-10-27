# 基于多源证据的 Web3 Agent 声誉评价平台

面向公开注册的 Web3 Agent，关联注册资料、自然语言功能声明、接口、合约和历史交易，生成有证据可追溯的中文评价报告。

固定评价维度为**服务可用性、功能声明一致性、交易行为可靠性**，综合权重为30% / 40% / 30%。资料不足时显示缺项，不补成0分或满分。历史查询政策B仅核可观察服务交付，页面保留这项实际范围说明，不冒充资产交易可靠性。用户提交受支持的注册标识后，平台自动匹配评价方案。

这是对原项目的重新实现。当前采用Vue 3 + TypeScript前端、FastAPI API、独立worker和PostgreSQL；不需要运行原项目的微服务、合约或Docker Compose。

2026-10-23主线改为**与区块链深度结合**。平台区分资产执行、链上查询和研究交付；新增10个真实Olas/Omen交易者的历史证据，其中8个已由同一规则核齐注册→Safe授权/签名→合约调用→资产及条件头寸到账，2个保留缺源。它们目前是链上证据快照，尚无完整声誉分；不能把只抓到的成功交易换算成100分。另保留Brain真实包装/兑换/增仓报告、九个Mech研究报告和两家仓位查询报告，合计12个不同身份的完整历史范围分。[当前规则与边界](docs/adr/0021-chain-execution-evidence.md)。

2026-10-27新增MangoSwap #26345的完整ERC20兑换能力范围分：**A95.67 / F100 / B100 / 综合98.70**。功能计划14项中12项可判、2项UNKNOWN保留；行为维度为7笔Base真实兑换。提供方构造方案，买方钱包依据用户授权签名，平台独立核验资产、授权和交易结果。用户批准后先冻结v2补采政策，再采集剩余4项，两个旧PARTIAL版本保留。见[实验、费用与易懂样本解读](docs/runbooks/MANGOSWAP_EVALUATION_20261027.md)；本机可直接[打开报告](http://127.0.0.1:7754/?agent=mangoswap-26345)。

该结果是旧政策下有限兑换范围的阶段性评价，历史原件和分数保留。新版已按[共享任务设计](docs/adr/0025-shared-task-declaration-scoring.md)及[范围出分修订](docs/adr/0026-scoped-shared-assessment.md)实现：同一任务分别支持三维，综合结果明确只代表已测范围，未测声明独立展示；不强制测完所有声明才出综合分。现有13个不同身份的范围结果不能直接解释为13个Agent全部声明已评价完整。

最新MangoSwap回顾性共享报告复用31个业务任务，形成131项判据观察；A **90.20–100.00**、F **50.48–69.94**、B **100.00**，已测范围综合 **77.25–87.98**。范围表达未决证据的可能结果，不是长期成功率置信区间。ETH/WETH输入输出标识不一致进入F；七笔真实兑换的正确到账保留。限价、定时/周期、官网V4、原生ETH及条件免gas等缺口见[声明矩阵](docs/research/MANGOSWAP_DECLARATION_MATRIX_20261027.md)。

评价实现见[实现指南](docs/runbooks/AGENT_EVALUATION_CONTRIBUTOR_GUIDE.md)：包含共享类型、声明/案例配置、同任务证据、来源适配器与实际命令。当前来源适配器支持已冻结Uniswap V3兑换报告的离线转换；其它协议须接入静态来源重放器，不能直接提交手写分数。2026-10-27已按用户要求关闭PR21并取消多人并发协作方案，当前继续MangoSwap补测。

## 环境准备

已经完成下文依赖与PostgreSQL配置的机器，可单独导入新版共享报告及其1198个公开依赖（约0.60MB）：

```powershell
uv run --env-file .env --no-sync python scripts/public_reports.py import data/public-reports-shared-v1.tar.gz --initialize
```

此包包含所需旧报告原件，无需钱包、RPC或LLM，不要求先重新执行实验。SHA256：`09657600785f729fa4dfb35ddb1e4c8c578d131045e340a9b17d3e03e873108c`。本机报告ID由导入器生成，包中源UUID仅作来源；重导相同报告不会重复创建。网站打开方式与个人RPC/LLM配置见下文，个人凭据不随代码提供。

| 工具 | 本项目使用的版本 |
| --- | --- |
| Python | 3.12，当前验证3.12.4 |
| uv | 0.9.3 |
| Node.js | 22.17.0（前端要求至少22.12） |
| pnpm | 11.25.0，见apps/web/package.json |
| PostgreSQL | 当前验证17.11，需一个自己的数据库与可建表账号 |

以下命令在**本仓库根目录**执行。示例使用PowerShell；其他系统可用同样的uv/pnpm/Python入口，数据库安装方式自行选择。

```powershell
uv sync --locked
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web run build
Copy-Item .env.example .env
```

编辑本机`.env`，填入自己的PostgreSQL连接信息。数据库需事先创建，账号需要创建本项目表和触发器的权限。

```dotenv
REPUTATION_DATABASE_URL=postgresql://YOUR_DB_USER:YOUR_DB_PASSWORD@127.0.0.1:5432/YOUR_DATABASE
REPUTATION_LLM_KEY_FILE=runtime/secrets/deepseek-api-key.txt
REPUTATION_ZAN_KEY_FILE=secrets/zan-base-rpc.txt
```

`.env`不会被应用自动读取；下列命令通过**uv的`--env-file .env`显式加载**。也可以直接设置操作系统环境变量。不要把真实密码或密钥写进README、源码或公开配置。

## 启动与打开网站

首次使用先建表：

```powershell
uv run --env-file .env --no-sync python scripts/import_local_report.py --initialize
```

再导入随项目提供的10个真实完整评分及公开证据；此步骤离线核验，不请求RPC或LLM：

```powershell
uv run --env-file .env --no-sync python scripts/public_reports.py import data/public-reports-v1.tar.gz
```

数据包约16.5MB，恢复公开原件到原runtime相对目录，由已有核验器重建分数后入库；不会覆盖不同内容的本地文件，也不包含个人账号或数据库。首次导入会离线核验约1.5万份依赖，本机Windows验证约12分钟，期间无需RPC或LLM账号。

接着导入新增的Brain #49467和Hallmark #338475两份完整仓位评价；已导入旧包的队友只需执行这一条：

```powershell
uv run --env-file .env --no-sync python scripts/public_reports.py import data/public-reports-position-v2.tar.gz --initialize
```

补充包约1.6MB，包含两份原始报告和612个公开文件，沿用离线来源核验与事务导入，无需RPC、LLM或重新测评。两个包都导入后共有12个不同Agent的完整结果。两份新评价均为A80 / F100 / B100 / 综合94，范围限本次仓位查询。导入输出的`mapping`记录本机报告ID；源报告UUID只作来源记录，不应复制为其他电脑的固定报告链接。重复导入不会重复创建同一报告，遇不同内容的同路径文件会明确拒绝覆盖。

再导入MangoSwap的完整兑换报告及公开原件（约1.4MB、3200个文件），同样离线重放，不需要RPC、LLM、钱包或充值：

```powershell
uv run --env-file .env --no-sync python scripts/public_reports.py import data/public-reports-swap-v3.tar.gz --initialize
```

此包默认只向数据库追加最新V2完整报告（综合98.70），与前两个完整报告包合计13个不同登记身份的完整范围分；它们包括研究、查询与资产操作，不等于13个自主交易Agent。包内两份旧PARTIAL作为历史附件安全恢复，需要在网站查看这两个历史版本时再执行：

```powershell
uv run --env-file .env --no-sync python scripts/import_local_report.py runtime/spraay-public-original-20261027
uv run --env-file .env --no-sync python scripts/import_local_report.py runtime/spraay-public-reassessment-20261027
```

源报告UUID仅作来源记录，本机链接使用导入输出的ID。受控付费采集由已获授权的操作者执行；导入与浏览公开包只读复核证据，不签名或付款。数据包SHA-256为`a9a161f82eed34e4676cfea263a7e132071ddbf5fa6bd291b4ace5f93a9d6933`。

接着导入真实资产执行的证据包（约235KB，521个公开文件）；此步骤同样离线，按原请求、哈希、历史状态和业务规则重建，不产生新评分：

```powershell
uv run --env-file .env --no-sync python scripts/chain_execution_evidence.py import data/chain-execution-evidence-v1.tar.gz
```

导入后可看[Olas交易者#219](http://127.0.0.1:7754/?agent=olas-omen-trader-219)、[缺源对象#1949](http://127.0.0.1:7754/?agent=olas-omen-trader-1949)和[Brain三步资产操作](http://127.0.0.1:7754/?agent=brain-defi)。Olas使用Service Registry注册，当前只展示历史核验；实时评分尚缺可归属服务入口和完整任务尝试范围，不混入ERC-8004自动接入流程。

本机Windows已经配置项目PostgreSQL及`.venv`时，可以后台启动，关闭终端仍保留API和worker：

```powershell
powershell -File scripts/start_platform_background.ps1
# 本会话已授权免费公共只读采证时：
powershell -File scripts/start_platform_background.ps1 -EnablePublicReadOnly -Proxy http://127.0.0.1:7897
```

此脚本复用本项目原数据库，只绑定回环地址；不会替换已占用端口。其他环境继续使用下方两个终端入口。

打开第一个终端，启动网页和API：

```powershell
uv run --env-file .env --no-sync python -m uvicorn reputation_platform.api:create_app --factory --host 127.0.0.1 --port 7754
```

打开第二个终端，在相同目录启动worker：

```powershell
uv run --env-file .env --no-sync python -m reputation_platform.worker
```

浏览器打开 **[http://127.0.0.1:7754/](http://127.0.0.1:7754/)**。无需另开Vite。两个终端应保持运行，Ctrl+C可停止对应进程。

默认worker关闭公网采集，可以浏览已有数据；新提交会说明尚未开启公开取证。本机常驻公开执行此前被拒绝，维持public-off。已有明确授权的单身份只读验收，可在确认队列为空并暂停默认worker后使用以下单次方式：

```powershell
uv run --env-file .env --no-sync python -m reputation_platform.worker --once --enable-public-readonly --public-reference eip155:56:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:49467 --public-request-timeout 45 --proxy http://127.0.0.1:7897
```

当前受控网络实现要求本机HTTP代理`127.0.0.1:7897`，不是任意代理地址均可。上述开关只开启已支持的公开只读流程，不发起付费Agent任务、签名或链上写入。

`--public-reference`限定一个规范身份，其他提交继续public-off；`--once`只处理队列中的一个作业，不按身份过滤队列，运行前须核对队列。45秒超时仅允许此单次限定方式，默认15秒；V3 v2通用评价预算64次、最多十四次业务调用（7F/7B）、1MiB响应、零业务重试，B观测窗口预定30秒。单次Worker完成后退出，常驻Worker用不带`--once`的启动命令。Mihomo Fake-IP环境复用固定HTTPS DNS解析、IP固定和原域名TLS。预测任务可能使用付费LLM翻译，需相应授权；仓位查询不调用模型。`GET /api/runtime`返回数据库、队列和Worker真实心跳，API健康不代表Worker正在处理任务。

Base #2290（Clawdia）的历史只读接入为PARTIAL：MCP发现接口A90.87，F/B/综合待评价，IPFS注册原件超时。目录缓存不能当已认证元数据；该对象仍不算完整评分。机制和原件见[历史审计](docs/runbooks/HISTORICAL_EVALUATION_AND_AGENT2290_20261019.md)。

网站包含“浏览Agent”和“接入并评价”两个入口。目录默认链上资产操作优先、同类综合分降序，可按业务/状态/报告范围筛选；分数仍只属于各报告范围，不表示跨政策的全局排名。详情先说明真实功能和链上动作，再显示三维及代表样本；历史、方法和原件折叠保留。可提交的ERC-8004身份示例：

```text
eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2359
```

示例不保证未来一定有足够证据出完整分数，平台按实际资料返回结果。

## 自备RPC和LLM账号

**个人账号、密钥、数据库、费用记录和私有配置不随仓库提供。其他使用者需要配置自己的服务。**

| 用途 | 当前接入 | 需要准备什么 |
| --- | --- | --- |
| Gnosis历史查询 | 固定公开RPC `https://rpc.gnosischain.com` | 当前可使用公开端点，不必填私人账号；能否取得历史数据取决于上游可用性 |
| BSC / Base注册及历史查询 | 已审查的ZAN固定端点 | 自己的ZAN项目；完整Base mainnet RPC URL保存为一行`secrets/zan-base-rpc.txt`，自动读取；其他路径可通过`REPUTATION_ZAN_KEY_FILE`指定 |
| 声明提取、预测问题中文翻译 | 可配置 OpenAI 兼容 Chat Completions / Responses；保留旧 DeepSeek 配置 | 在本地 `runtime/platform-config/llm.json` 填 Base URL、模型、协议及 Key 文件路径，见[LLM 配置说明](docs/runbooks/LLM_CONFIGURATION.md) |
| 平台存储 | PostgreSQL | 自己的数据库、账号、密码，通过`REPUTATION_DATABASE_URL`指定 |

用本机编辑器填入被Git忽略的个人文件（`secrets/`或`runtime/secrets/`）。LLM文件存**API key**；ZAN文件存**含项目密钥的完整RPC URL**，不是裸key。只把文件路径放进环境配置，不把文件内容放到命令行、前端或GitHub PR里。

ZAN推荐直接创建`secrets/zan-base-rpc.txt`后运行现有启动脚本；也支持私密`runtime/platform-config/zan-key-file.txt`保存自选文件路径。启动器自动为API/Worker导出选中的`REPUTATION_ZAN_KEY_FILE`，Python采集进程也可跨平台自动读取。运行`.venv/Scripts/python.exe scripts/check_zan_connection.py`仅检查Base链ID与区块高度；ZAN请求复用安全自动代理/Fake-IP解析，保留固定端点、只读方法、IP固定与TLS校验。详见[ZAN本地配置](docs/runbooks/ZAN_CONFIGURATION.md)。

凭证路径也可在相关采集CLI中通过显式`--key-file`或`--zan-key-url-file`指定，优先于环境变量。原开发机可用`runtime/platform-config/llm-key-file.txt`保存已有key文件的路径，避免复制密钥。普通网站用户不需要填写后台账号。

评分计算与离线核验本身不依赖LLM直接给分；但**当前网站对新就绪预测任务会调用中文翻译步骤**，没有当前配置的已验证翻译缓存时，应配置自己的模型服务。支持 DeepSeek、OpenAI、Qwen、GLM 和兼容中转站的文本 Chat Completions；模型须返回约定 JSON。新配置按模型、协议、端点指纹隔离翻译缓存，旧报告仍按原证据核验。仅运行网页、浏览原报告或执行不需要模型的通用资料核验，不需要模型余额。

LLM 网络默认自动选择代理：专用 `REPUTATION_LLM_PROXY` → 旧 CLI `--proxy` → `HTTPS_PROXY` / `ALL_PROXY` → Windows/macOS 系统静态代理 → 直连。专用变量可设 `direct` 强制直连，或填写 `http://PROXY_HOST:PROXY_PORT`、`https://PROXY_HOST:PROXY_PORT`、`socks5://PROXY_HOST:PROXY_PORT`；`HTTP_PROXY` 不作为 HTTPS 的替补，`NO_PROXY` 始终匹配原域名，不执行 PAC/WPAD 或接受 `socks5h` 远程 DNS。`REPUTATION_LLM_DNS_MODE=auto` 默认只在全部系统 DNS 结果都是 `198.18.0.0/15` 且有代理时使用 Cloudflare 固定 IP HTTPS DNS 查询 A/AAAA；`system` 禁用回退。全部目标仍须为公网，混合/私网结果或 DNS 失败会拒绝；连接使用数字 IP CONNECT/SOCKS 并保留原域名 TLS/Host，不重定向或降低 TLS 验证。代理需支持数字 IP CONNECT，Linux/macOS 真机尚未验证。完整说明见[LLM 配置说明](docs/runbooks/LLM_CONFIGURATION.md#llm-代理与-dns)。

可选运行 `.venv/Scripts/python.exe scripts/check_llm_connection.py`，只发送 `GET models` 检查连接和私密 `llm.json` 指定的模型，不发起推理。

RPC不是任意供应商网关：链、端点与认证方式由后台固定白名单控制，注册资料不能指定RPC。原有`configs/`部分文件是已发布证据所绑定的历史配置，不要为了填个人密钥而改写；使用上面的本地凭证入口。更换RPC供应商需要单独适配。

## 数据与当前完成范围

完整评分发布包对应12个不同身份：9个研究预测、1个增仓历史特例、Brain/Hallmark两份仓位查询。新增执行证据包另对应10个Olas交易者（8个样本核齐、2个缺源），尚无完整分。两类数量分开统计；多份报告不重复算身份。各机器的候选/历史报告数取决于本机数据，当前工作站实核见[STATUS.md](STATUS.md)。

**仓库包含两个经过审计的完整评分发布包**：`data/public-reports-v1.tar.gz`保留原10个不同真实Agent的完整报告；`data/public-reports-position-v2.tar.gz`补充Brain/Hallmark两份最新完整仓位评价及核验必需公开证据。按上文依次导入即可浏览12个不同Agent的完整结果；只浏览和核验这些已有结果不需要配置RPC或LLM密钥。补充包摘要、源报告ID和分数见[data/public-reports-position-v2.json](data/public-reports-position-v2.json)。

未导入前新数据库为空。三个包不等于开发机的整个runtime或数据库，不包含个人密钥、私有配置、费用流水、临时日志及全部试运行报告。前端dist和依赖仍需自行安装/构建。

可以在网页提交受支持身份自行取证，或导入自己合法取得的完整证据包。导入时须保留所有被manifest引用的原件及相对目录；仅有一份report.json不能替代完整证据：

```powershell
uv run --env-file .env --no-sync python scripts/import_local_report.py runtime/YOUR_REPORT_DIRECTORY
```

2026-10-20最新两份完整报告使用`query.pancakeswap-v3-position/v2`和`service-fulfillment-v1`，各有10A/7F/7B，A80/F100/B100/S94。导入补充包后查看[Brain详情](http://127.0.0.1:7754/?agent=agent-e9357377962d8c944359ca49)或[Hallmark详情](http://127.0.0.1:7754/?agent=agent-0e9825a984849eea12b970ac)。每方63个公开只读请求、14个业务调用，零业务重试。Hallmark单次自动发布；Brain首次遇来源分派错误，修复后复用原件恢复发布。开工14份报告与旧政策保留，包括此前v1的两份PARTIAL和旧ERC20单F报告；新两份完整报告和公开原件现通过独立补充包分发，原10报告包保持不变，其他本机试运行结果未随包分发。身份、任务、证据及边界见[本轮报告](docs/runbooks/COMPLETE_CAPABILITY_EVALUATION_20261020.md)，此前v1结果见[历史实施报告](docs/runbooks/CROSS_PROVIDER_CHECKER_VALIDATION_20261019.md)。

完整预测评分仍限已核实的Fixed Price Native/Omen/IPFS证据链；V3的F只核五项静态事实，B只核请求/对象绑定、完整交付和预定窗口。未知提供方须先认证并审阅真实契约；Clawdia路由与旧固定ERC20查询仍缺独立任务证据。新Olas执行样本不评价盈利、选市质量、当前在线或完整失败率。桌面及390px链执行页面已完成本轮真实浏览器检查；运行状态以各机器`/api/runtime`为准，历史开发机的停机/审批记录不是当前启动状态。

为同类新提供方扩展已支持的输入输出映射时，新建并审阅一个配置版本，后台用`REPUTATION_POSITION_REVIEW_CONFIG=configs/position-adapter-reviews-v2.json`选择它；路径相对仓库根目录，必须先有真实审阅文件。新评价冻结该路径，旧报告继续按自身冻结版本复核。当前v1配置及其117项证据依赖已被报告引用，不能原地追加或改写；环境变量也不代替身份认证、安全审阅和单独执行授权。第三提供方目前只有离线复用测试，没有新增真实成绩。

## 开发、验证与仓库

- [PLAN.md](PLAN.md)：当前任务和推进顺序。
- [STATUS.md](STATUS.md)：实际完成、验证记录、限制和Git/PR状态。
- [docs/runbooks/LOCAL_PLATFORM.md](docs/runbooks/LOCAL_PLATFORM.md)：原开发机Windows快捷启动及运行记录。该快捷脚本依赖原机工具目录；其他机器优先使用本页的通用入口。
- [GIT_SETUP.md](GIT_SETUP.md)：原项目断开远程、新实现接入及PR方式。
- [docs/adr/](docs/adr/)：评分与证据规则；历史政策和已发布证据保持可复算。

部分真实集成验收依赖未入Git的证据和独立PostgreSQL，缺少条件时应显示NOT_RUN/BLOCKED，不把skip当作完整集成通过。只运行必要受影响验证，复用已有有效结果。

目标仓库：[Ryanjxy123/web3-agent-reputation](https://github.com/Ryanjxy123/web3-agent-reputation)。本次通过重构PR替换项目实现，保留远程历史，不强推main；个人密钥、私有运行目录和数据库不上传，已完成评分以独立公开证据包交付。
