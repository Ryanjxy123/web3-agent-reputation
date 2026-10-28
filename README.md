# 基于多源证据的 Web3 Agent 声誉评价平台

面向公开注册并提供服务信息的Web3 Agent，收集注册资料、自然语言功能描述、服务接口、关联合约和交易历史，评价**服务可用性、功能声明一致性、交易行为可靠性**。

当前发布数据只保留 **MangoSwap #26345**，旧Agent发布包与候选/实例记录已从当前版本移除。实现采用Vue 3＋TypeScript、FastAPI、独立worker及PostgreSQL；不需要运行父目录旧项目。

## 当前演示

MangoSwap提供即时资产兑换、定时和限价订单管理，由用户钱包签名调用Base合约。平台复用34个真实任务、153项判据，核原意图、实际调用、回执、事件、资产/授权和订单状态。三笔V4实验包括原生ETH兑换、定时创建撤销、限价创建查询撤销，后两笔本金全退。

当前单值评分：**A100 / F91.67 / B100 / 综合96.67**。按有效可判的通过/失败计算；未知与未采单列，不补成0或100。原ETH/WETH标识不一致仍影响F；A只对应已有28份可判响应；10个链上履约任务为8次兑换和2次订单管理。规则见[ADR-0029](docs/adr/0029-single-score-and-report-scope.md)。

页面主区展示功能、三维/综合单分和代表性样本。报价、模拟、成交、撤销退款按真实阶段命名，完整任务与原件可展开。当前结果限于已测功能和样本。

## 任务证据工作台

界面提供概览、任务链路、评价报告和链上证据四个入口。任务链路按当前报告的task_key、sample_id和原件引用重建，支持任务筛选、节点/步骤/判据联动、合约调用检查、原件按需预览、链上链接与历史步骤回放。回放在已有关系上显示定向信号，抵达后同步点亮节点与证据面板，仅在前端重放，不重新执行交易。未记录的服务内部过程不补造，浏览无需钱包。原生兑换、订单撤销退款、方案返回和未知测量分别展示，分数与评分规则保持。

实现位置、当前环境说明和真实截图见[视觉与链路实施记录](docs/runbooks/VISUAL_TRACE_WORKBENCH_20261028.md)。

进一步的空间背景、全息概览、折返执行拓扑与动态证据回放已完成；支持减少动态效果与页面隐藏暂停。主要改动、真实浏览器截图和MP4/GIF见[视觉深化与动态回放验收](docs/runbooks/VISUAL_DEPTH_AND_REPLAY_20261028.md)。

当前展示采用三级信息：默认解释用户请求、执行主体、实际业务结果与核验结论；关键链上操作主动展开，地址/哈希缩略并可完整复制；完整字段、判据、证据引用与原始 JSON 集中在技术详情。业务完成与核验差异、未知或未采可同时存在，订单撤销退款不会显示为自动成交。资产名称标注差异采用温和提示，与真实执行失败和重大风险分别呈现，原判定及计分保持。实现与浏览器验收见[业务信息层级优化](docs/runbooks/BUSINESS_FIRST_TRACE_20261028.md)。

## 队友更新到最新工作台

最新交付位于 **`codex/evidence-workbench`** 分支，尚未合并到 `main`。本次包含：

- `0d0ca38`：深色空间界面、真实任务链路与历史回放；业务概览、关键链上操作、原始证据三级展示；支持按任务读取的只读证据接口。
- `aba8a52`：资产名称标注差异改为温和提示，真实执行失败和重大风险保留告警；原始判定、评分和证据不变。

已有仓库的队友在仓库根目录执行：

```powershell
git fetch origin
git switch codex/evidence-workbench
git pull --ff-only origin codex/evidence-workbench
uv sync --locked
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web run build
```

构建后重启下节的 API 服务，打开 <http://127.0.0.1:7754/?agent=mangoswap-26345>。已经导入当前 MangoSwap 公开包的环境无需为本次前端更新重复导入。首次运行仍需按下节配置自己的 PostgreSQL 并导入仓库中的公开包；只浏览报告无需启动 worker。

本次代码已通过前端构建、10项投影测试及真实浏览器检查；原布局/只读接口的有效验证沿用，各阶段证据见上方实施记录。

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

只浏览已有报告无需启动worker。需要处理新的评价请求时，另开终端启动worker：

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
