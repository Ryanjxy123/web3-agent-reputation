# 基于多源证据的 Web3 Agent 声誉评价平台

面向公开注册的 Web3 Agent，关联注册资料、自然语言功能声明、接口、合约和历史交易，生成有证据可追溯的中文评价报告。

固定评价维度为**服务可用性、功能声明一致性、行为履约可靠性**，综合权重为30% / 40% / 30%。B的具体含义随版本化政策说明：历史政策核交易履约，新查询政策核可观察服务交付。资料不足时明确显示缺项，不补成0分或满分。用户在网站提交注册标识后，由平台自动匹配已支持的评价方案。

这是对原项目的重新实现。当前采用Vue 3 + TypeScript前端、FastAPI API、独立worker和PostgreSQL；不需要运行原项目的微服务、合约或Docker Compose。

2026-10-20已完成两家真实提供方的仓位查询完整评价：Brain #49467（MCP）与Hallmark #338475（A2A）共用Position/v2 Checker，自动冻结各7个F和7个互斥B任务，均取得A=80、F=100、B=100、综合94。新政策`service-fulfillment-v1`的B核验可观察服务交付；成绩只属于本次协议发现与仓位查询范围。LLM网络回归修复后49项及相关9项通过。详见[本轮实施报告](docs/runbooks/COMPLETE_CAPABILITY_EVALUATION_20261020.md)。API及数据库在线，两次限定Worker均已退出；常驻Worker和浏览器视觉验收仍受此前策略拒绝限制。

## 环境准备

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

`--public-reference`限定一个规范身份，其他提交继续public-off；`--once`只处理队列中的一个作业，不按身份过滤队列，所以运行前必须核对队列。45秒上限仅允许此单次限定方式，默认仍15秒；V3 v2通用评价总预算64次、最多十四次业务调用（7F/7B）、1MiB响应、零重试，B观测窗口预定30秒。完成后单次Worker退出；当前常驻Worker恢复受此前自动审批拒绝限制，本轮没有恢复它。公开采集在系统DNS全部返回Mihomo Fake-IP且使用上述代理时，复用已验证的固定HTTPS DNS解析，仍拒绝私网/混合地址并保留IP固定和原域名TLS。预测就绪路径可能使用付费LLM翻译，需另有相应费用授权；本轮仓位评价不调用模型。`GET /api/runtime`分别返回数据库、队列和Worker心跳状态；API健康不表示Worker正在处理任务。

本轮Checker扩展前，2026-10-19本机曾仅对Base #2290（Clawdia）完成一次真实只读接入：MCP发现接口A=90.87，F/B/综合待评价，报告PARTIAL；IPFS注册原件超时，不能将目录缓存当作已认证元数据。当前常驻Worker恢复public-off，已生成报告仍可浏览；常驻公开Worker启动被自动审批拒绝，尚未启用后续提交的持续公开评价。历史10报告未改，实际机制和能力边界见[历史审计与2290报告](docs/runbooks/HISTORICAL_EVALUATION_AND_AGENT2290_20261019.md)。

网站包含“浏览Agent声誉”和“接入Agent产生评价”两个入口。目录默认按最近更新排序，也可按名称排序，支持搜索、状态/范围筛选；各报告展示自己的范围分，不把不同政策和能力排成综合分榜单。详情包含历史报告、三维解释、样本与原始证据。可提交的规范身份示例：

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

开发机现有13个Agent、16份报告，其中12份完整报告对应12个不同身份：9个历史预测、1个历史增仓特例，加Brain/Hallmark两份新仓位查询完整评价。具体对象、真实退出码及限制见[STATUS.md](STATUS.md)。范围评分不代表Agent全部能力；不同政策和能力的分数不直接排名，历史交付文件可访问也不等于实时推理在线。

**仓库包含经过审计的完整评分发布包**`data/public-reports-v1.tar.gz`，覆盖10个不同真实Agent的最新完整报告及核验必需公开证据。按上文导入后即可浏览；只浏览和核验这些已有结果不需要配置RPC或LLM密钥。

未导入前新数据库为空。公开包不等于开发机的整个runtime或数据库：不包含个人密钥、私有配置、费用流水、临时日志、旧试运行报告，也不把38个候选和46份历史报告冒称全已随包分发。前端dist和依赖仍需自行安装/构建。

可以在网页提交受支持身份自行取证，或导入自己合法取得的完整证据包。导入时须保留所有被manifest引用的原件及相对目录；仅有一份report.json不能替代完整证据：

```powershell
uv run --env-file .env --no-sync python scripts/import_local_report.py runtime/YOUR_REPORT_DIRECTORY
```

2026-10-20最新两份完整报告使用`query.pancakeswap-v3-position/v2`和`service-fulfillment-v1`，各有10A/7F/7B，A80/F100/B100/S94。查看[Brain报告](http://127.0.0.1:7754/?agent=agent-e9357377962d8c944359ca49&report=0812985f-8777-4629-8fba-3db4b3e1e65a)或[Hallmark报告](http://127.0.0.1:7754/?agent=agent-0e9825a984849eea12b970ac&report=c88165ca-df10-4cb2-aeb2-6e8680c605c2)。每方63个公开只读请求、14个业务调用，零业务重试。Hallmark单次自动发布；Brain首次遇来源分派错误，修复后复用原件恢复发布。开工14份报告与旧政策保留，包括此前v1的两份PARTIAL和旧ERC20单F报告；新报告与原件仅在本机，未加入原10报告公开包。身份、任务、证据及边界见[本轮报告](docs/runbooks/COMPLETE_CAPABILITY_EVALUATION_20261020.md)，此前v1结果见[历史实施报告](docs/runbooks/CROSS_PROVIDER_CHECKER_VALIDATION_20261019.md)。

完整预测评分仍限已核实的Fixed Price Native/Omen/IPFS证据链；V3的F只核五项静态事实，B只核请求与对象绑定、完整交付及预定观测窗口。未知提供方需要先认证、匹配真实Schema、审阅免费只读契约并获得执行许可；Clawdia路由与旧固定ERC20查询仍缺独立任务证据。当前API在线；默认public-off Worker恢复启动被自动审批拒绝，常驻Worker未运行，新提交暂留队列，可按上方默认命令手动启动。浏览器工具因无法可靠识别Windows URL而停止，桌面/手机视觉验收未完成；构建和API通过不当作视觉验收。

为同类新提供方扩展已支持的输入输出映射时，新建并审阅一个配置版本，后台用`REPUTATION_POSITION_REVIEW_CONFIG=configs/position-adapter-reviews-v2.json`选择它；路径相对仓库根目录，必须先有真实审阅文件。新评价冻结该路径，旧报告继续按自身冻结版本复核。当前v1配置及其117项证据依赖已被报告引用，不能原地追加或改写；环境变量也不代替身份认证、安全审阅和单独执行授权。第三提供方目前只有离线复用测试，没有新增真实成绩。

## 开发、验证与仓库

- [PLAN.md](PLAN.md)：当前任务和推进顺序。
- [STATUS.md](STATUS.md)：实际完成、验证记录、限制和Git/PR状态。
- [docs/runbooks/LOCAL_PLATFORM.md](docs/runbooks/LOCAL_PLATFORM.md)：原开发机Windows快捷启动及运行记录。该快捷脚本依赖原机工具目录；其他机器优先使用本页的通用入口。
- [GIT_SETUP.md](GIT_SETUP.md)：原项目断开远程、新实现接入及PR方式。
- [docs/adr/](docs/adr/)：评分与证据规则；历史政策和已发布证据保持可复算。

部分真实集成验收依赖未入Git的证据和独立PostgreSQL，缺少条件时应显示NOT_RUN/BLOCKED，不把skip当作完整集成通过。只运行必要受影响验证，复用已有有效结果。

目标仓库：[Ryanjxy123/web3-agent-reputation](https://github.com/Ryanjxy123/web3-agent-reputation)。本次通过重构PR替换项目实现，保留远程历史，不强推main；个人密钥、私有运行目录和数据库不上传，已完成评分以独立公开证据包交付。
