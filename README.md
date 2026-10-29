# 基于多源证据的 Web3 Agent 声誉评价平台

当前网站只提供**浏览既有Agent评价报告**：查看功能介绍、排序筛选、三维评分、任务样本与多源证据。普通用户不能自主提交Agent评价请求；“浏览Agent／接入并评价”切换及接入页面不再属于当前产品。历史自动接入实现仅作为后台或未来扩展能力保留。

本轮四个已在测对象均已完成本轮范围评价并正式发布：MangoSwap、Hydrex、Topaz、Ophis。**已停止新增Agent实验，不再以10个对象为目标。** 合计146个实际任务、32笔真实兑换及2笔订单管理；这些是已测范围评价，不代表全部声明功能均已验证。

面向公开注册并提供服务信息的Web3 Agent，收集注册资料、自然语言功能描述、服务接口、关联合约和交易历史，评价**服务可用性、功能声明一致性、交易行为可靠性**。

四个对象使用同一套三维单分规则，按协议核验各自的任务证据。实现采用Vue 3＋TypeScript、FastAPI、独立worker及PostgreSQL；不需要运行父目录旧项目。正式输入、未知项与交付状态见[四对象收口记录](docs/runbooks/TRADING_CLOSEOUT_20261029.md)。

## 当前演示

| 对象 | 任务数 | A 可用性 | F 功能一致性 | B 行为可靠性 | 综合分 |
| --- | ---: | ---: | ---: | ---: | ---: |
| MangoSwap | 34 | 100 | 91.67 | 100 | **96.67** |
| Topaz | 38 | 100 | 98 | 100 | **99.2** |
| Hydrex | 43 | 82.22 | 100 | 100 | **94.67** |
| Ophis MCP | 31 | 100 | 100 | 100 | **100** |

MangoSwap提供即时资产兑换、定时和限价订单管理，由用户钱包签名调用Base合约。平台复用34个真实任务、153项判据，核原意图、实际调用、回执、事件、资产/授权和订单状态。三笔V4实验包括原生ETH兑换、定时创建撤销、限价创建查询撤销，后两笔本金全退。

MangoSwap当前单值评分：**A100 / F91.67 / B100 / 综合96.67**。按有效可判的通过/失败计算；未知与未采单列，不补成0或100。原ETH/WETH标识不一致仍影响F；A只对应已有28份可判响应；10个链上履约任务为8次兑换和2次订单管理。规则见[ADR-0029](docs/adr/0029-single-score-and-report-scope.md)。

页面主区展示功能、三维/综合单分和代表性样本。报价、模拟、成交、撤销退款按真实阶段命名，完整任务与原件可展开。当前结果限于已测功能和样本。

Topaz生成Base链USDC/WETH兑换方案，按通用原子兑换协议核验报价、完整调用、独立模拟和真实执行。当前38个任务保留36份HTTP响应及2次平台传输中断，8笔真实兑换已核64块以上确认距离；另有16份历史完整模拟。F98保留真实非法输入响应不符，未把时钟精度或缺证据统一扣给Agent。

Hydrex通过Virtuals ACP接收兑换意图并生成Base链路由方案，由买方钱包签名执行。正式扩采报告包含43个实际任务、48个冻结槽位，8笔真实兑换为双方向各4笔。4项完整窗口超时使A降至82.22；H13、H33保持UNKNOWN，H24的Kyber入口另有独立部署与runtime绑定。F100只对应已知可判判据，声明覆盖仍为PARTIAL；未知、未采和模拟均不冒充成交。其身份、交付、实际交易、净资产与授权清零保留原件，详见[Hydrex扩采发布记录](docs/runbooks/HYDREX_EXPANDED_RELEASE_20261029.md)。

Ophis通过公开MCP接口提供CoW报价、订单构建与校验，由买方钱包签名，solver在Base结算。31个任务包含8笔双向真实兑换，均核UID、Trade、本人净资产、期限、授权归零及至少85块距离；原门槛仍为64块。F的93项可判判据通过、15项UNKNOWN，严格整任务计数为16通过/15未知，所以100分只描述已知可判部分，声明覆盖仍为PARTIAL。目录登记已核实，ERC-8004链注册未证实；独立同块余额、同期盈余基准和原生submit公开证据缺项保留UNKNOWN。

后台来源工具直接重放任务原件，不要求复制MangoSwap父报告；它不是面向普通用户的自助接入入口。0x、Hydrex包装协议、Kyber、原子兑换和CoW按通用协议核验；TheSafeRouteBot等历史候选材料保留，不启动后续实验，也不计正式评分对象。见[来源规则](docs/adr/0030-unsigned-swap-source-replay.md)及[历史交付记录](docs/runbooks/TRANSACTION_COHORT_RELEASE_20261028.md)。

## 网站任务证据工作台

本轮同步队友的空间背景、概览、任务链路回放和证据检查工作台。先展示Agent功能、已测范围与真实业务结果，具体输入输出、链上动作和原始JSON按需展开。链路动画解释步骤关系，不代表真实请求耗时。报价/模拟与实际成交按真实B证据区分，ACP链上交付和HTTP调用分别呈现；评分与原始报告不因可视化改变。

队友设计与历史视觉验收见[业务优先工作台](docs/runbooks/BUSINESS_FIRST_TRACE_20261028.md)。Hydrex任务链路按已认证RPC observation与原任务执行hash展开，服务费交易不算兑换履约；Ophis按UID解释solver结算，签名钱包与交易发送者分别标明。本轮四对象均已正式发布，未自动启动其它候选。

## 安装与打开网站

需要Python3.12、uv0.9.3、Node.js至少22.12、pnpm11.25.0，以及自己的PostgreSQL数据库（当前验证17.11）。在本仓库根目录执行：

```powershell
uv sync --locked
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web run build
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

编辑本机`.env`，填自己的数据库连接。账号需要创建项目表和触发器的权限：

```dotenv
REPUTATION_DATABASE_URL=postgresql://YOUR_DB_USER:YOUR_DB_PASSWORD@127.0.0.1:5432/YOUR_DATABASE
```

导入当前四对象发布包；已从Git公共依赖原字节独立离线重放4份报告，exit 0，无网络或数据库操作。详情见[四对象收口记录](docs/runbooks/TRADING_CLOSEOUT_20261029.md#四对象公开包与复现)。

```powershell
uv run --env-file .env --no-sync python scripts/public_reports.py import data/public-reports-trading-closeout-v4.tar.gz --initialize
```

启动网页/API：

```powershell
uv run --env-file .env --no-sync python -m uvicorn reputation_platform.api:create_app --factory --host 127.0.0.1 --port 7754
```

仅浏览已发布报告无需启动worker；本机需要运行后台worker时可另开终端，默认仍为public-off：

```powershell
uv run --env-file .env --no-sync python -m reputation_platform.worker
```

浏览器打开 **[http://127.0.0.1:7754/](http://127.0.0.1:7754/)**，或直接查看[MangoSwap](http://127.0.0.1:7754/?agent=mangoswap-26345)、[Topaz](http://127.0.0.1:7754/?agent=topaz-agent-113284)、[Hydrex](http://127.0.0.1:7754/?agent=hydrex-routing-54947)、[Ophis](http://127.0.0.1:7754/?agent=mcp-registry%3Afi.ophis%2Fmcp%400.2.0)。无需再启动Vite。默认worker为public-off，浏览已发布报告不会发起新付费任务或资产交易。`.env`通过uv的`--env-file`显式加载。

本开发机已有数据库与私有配置时，可用`powershell -File scripts/start_platform_background.ps1`后台启动；它不替换已占用端口。其它机器按上述通用命令配置自己的数据库即可。

没有设置`REPUTATION_DATABASE_URL`时，本机可在私有`runtime/platform-config/active-database-url.txt`指定当前演示连接，未配置则使用原`database-url.txt`。用于隔离已撤下对象的历史数据库；不删除旧报告，也不把私有连接上传。

## RPC、LLM和钱包配置

个人账号、密钥和数据库不随仓库提供。只浏览已有报告不需要模型或链服务账号；需要新增采证时按用途自行准备：

| 用途 | 配置方式 |
| --- | --- |
| PostgreSQL | `.env`的`REPUTATION_DATABASE_URL` |
| Base/BSC链上读取 | 自己的ZAN项目；完整私有RPC URL存`secrets/zan-base-rpc.txt`，或用`REPUTATION_ZAN_KEY_FILE`指定私有文件路径；见[RPC配置](docs/runbooks/ZAN_CONFIGURATION.md) |
| 声明提取/文本处理 | 自己的模型账号或兼容中转；私有`runtime/platform-config/llm.json`配置Base URL、模型、协议及密钥文件路径；见[LLM配置](docs/runbooks/LLM_CONFIGURATION.md) |
| 新真实交易实验 | 专用已授权钱包；会话/签名器只存本地，不包含在公开证据包中 |

密钥只写被忽略的`.env`、`secrets/`或`runtime`私有配置，不放前端、Git或公开报告。已发布证据绑定的`configs`不能改成个人密钥配置。程序外网走SafeHttpClient，RPC限操作者可信配置；需要代理时设置自己的实际地址，LLM支持`REPUTATION_LLM_PROXY`。当前开发机HTTP代理端口为7897，不能照搬为其它机器的可用代理。

**严格禁止发币、Agent tokenize、发行身份或报告NFT。** 现有注册身份与既有资产只用于真实业务评价；不以API付款、平台存证或DEX成交冒充Agent自主策略。

## 数据与验证

最终四对象包`data/public-reports-trading-closeout-v4.tar.gz`已通过独立离线verify（exit 0）：4份报告、4917份runtime恢复、25份Git原字节环境前置，0联网/0数据库写入。归档6381791字节、4941文件（含索引4942成员），SHA256 `9cbf2cfff85f7b1af9ef16fce542488f7217773838cd3c19d6a50c90a9f3460e`；3类已知本机秘密及私钥标记扫描0命中。回执见`runtime/package-review-trading-closeout-20261029/verification-receipt.json`和`exact-secret-scan.json`。

网站四对象的真实PostgreSQL导入、列表、Ophis含斜杠标识详情、正式报告、C08单笔兑换链视图与附件SHA已核验。当前代码检查点`a80f327`，分支`codex/hydrex-expanded-evaluation`；最终提交、PR与CI状态以`runtime/release-closeout-review-20261029/git-delivery.json`交付回执为准。

通用评分和协议适配代码保留。旧实例采集CLI已改为显式传入操作者的profile/config，不再默认选择旧对象。评分与原件只追加、分数由后端复算，前端不手填。单值规则/证据来源与本轮验证详见[单分交付记录](docs/runbooks/MANGOSWAP_SINGLE_SCORE_20261027.md)。

当前CI检查纯规则、共用协议解码、真实来源/公开包、前端构建，以及真实PostgreSQL并发租约、过期恢复、不可修改报告与HTTP闭环。已有有效测试不因提交重复跑；更改关键行为或出现真实失败时执行必要检查。

本次移除自助接入页面后，`pnpm --dir apps/web run build`的类型检查和构建exit 0（Vite538ms），本机已提供新构建；前端不再包含评价提交或作业轮询调用。本次提交与[PR #24](https://github.com/Ryanjxy123/web3-agent-reputation/pull/24)的CI状态见交付回执`runtime/release-closeout-review-20261029/git-delivery.json`，已有评分与数据包保持原版本。
