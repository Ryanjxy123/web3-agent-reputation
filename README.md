# 基于多源证据的 Web3 Agent 声誉评价平台

面向公开注册并提供服务信息的Web3 Agent，收集注册资料、自然语言功能描述、服务接口、关联合约和交易历史，评价**服务可用性、功能声明一致性、交易行为可靠性**。

当前发布数据只保留 **MangoSwap #26345**，旧Agent发布包与候选/实例记录已从当前版本移除。实现采用Vue 3＋TypeScript、FastAPI、独立worker及PostgreSQL；不需要运行父目录旧项目。

## 当前演示

MangoSwap提供即时资产兑换、定时和限价订单管理，由用户钱包签名调用Base合约。平台复用34个真实任务、153项判据，核原意图、实际调用、回执、事件、资产/授权和订单状态。三笔V4实验包括原生ETH兑换、定时创建撤销、限价创建查询撤销，后两笔本金全退。

当前单值评分：**A100 / F91.67 / B100 / 综合96.67**。按有效可判的通过/失败计算；未知与未采单列，不补成0或100。原ETH/WETH标识不一致仍影响F；A只对应已有28份可判响应；10个链上履约任务为8次兑换和2次订单管理。规则见[ADR-0029](docs/adr/0029-single-score-and-report-scope.md)。

页面主区展示功能、三维/综合单分和代表性样本。报价、模拟、成交、撤销退款按真实阶段命名，完整任务与原件可展开。当前结果限于已测功能和样本。

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

导入仓库唯一的MangoSwap发布包。包内含评分、必要历史原件和三笔V4证据，可离线复算，不需要钱包、RPC或LLM：

```powershell
uv run --env-file .env --no-sync python scripts/public_reports.py import data/public-reports-single-score-v3.tar.gz --initialize
```

启动网页/API：

```powershell
uv run --env-file .env --no-sync python -m uvicorn reputation_platform.api:create_app --factory --host 127.0.0.1 --port 7754
```

另开终端启动worker：

```powershell
uv run --env-file .env --no-sync python -m reputation_platform.worker
```

浏览器打开 **[http://127.0.0.1:7754/](http://127.0.0.1:7754/)**，或[直接打开MangoSwap](http://127.0.0.1:7754/?agent=mangoswap-26345)。无需再启动Vite。默认worker为public-off，浏览已发布报告不会发起新付费任务或资产交易。`.env`通过uv的`--env-file`显式加载。

本开发机已有数据库与私有配置时，可用`powershell -File scripts/start_platform_background.ps1`后台启动；它不替换已占用端口。其它机器按上述通用命令配置自己的数据库即可。

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

`data/`只发布MangoSwap单分包及其必要声明。旧对象记录已移除，Git历史未改写；已有个人数据库不会因拉取代码自动删除。新机器只导入上述包即可得到当前演示数据。公开包包含复核必需原件，钱包登录、P256密钥和私有配置均排除。

通用评分和协议适配代码保留。旧实例采集CLI已改为显式传入操作者的profile/config，不再默认选择旧对象。评分与原件只追加、分数由后端复算，前端不手填。单值规则/证据来源与本轮验证详见[单分交付记录](docs/runbooks/MANGOSWAP_SINGLE_SCORE_20261027.md)。

当前CI检查纯规则、MangoSwap真实来源/公开包、前端构建，以及真实PostgreSQL并发租约、过期恢复、不可修改报告与HTTP闭环。已有有效测试不因提交重复跑；更改关键行为或出现真实失败时执行必要检查。
