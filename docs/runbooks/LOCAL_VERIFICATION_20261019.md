# 2026-10-19 本机同步与启动核验

后续 LLM 改造已支持配置式 Chat Completions / Responses，当前配置和验证结果见 [LLM 配置说明](LLM_CONFIGURATION.md) 及 STATUS；以下保留改造前的历史运行事实。

本机目录：`D:/大三上/软件前沿技术/区块链竞赛/web3-agent-reputation`。本轮以同步、检查和本地复现为范围，不提交、不推送、不调用付费模型、不发链上交易。

## 仓库同步

- 原分支 `audit/competition-final-delivery-20261013` 的 `c7f1841` 保留。
- 开始时无未提交修改；确认 origin 为目标 GitHub 仓库，fetch 成功。
- 切换本地 main，以 `git merge --ff-only origin/main` 从 `257e52b` 更新至 `3a680f3c5c82b51d3cc0b6fd51eb32bbb1cc9b39`（PR #17 合并）。HEAD 与 origin/main 为 0 ahead / 0 behind。
- 新版忽略规则不再覆盖既有 `.bootstrap-incoming/README.md`，故该原文件成为未跟踪文件；未覆盖、移动或删除。

## 实际实现

- 新版是 Vue 3/TypeScript + FastAPI + 独立 Python worker + PostgreSQL 的模块化单体。API 托管构建后的网页，无需另启 Vite。
- 当前没有独立 Verifier 服务；core/report 模块和导入器负责离线证据核验、规则复算。旧版 Foundry/Anvil、合约、Compose 不是本次启动依赖。
- 前端包含目录搜索、范围/状态筛选、排序、接入表单、任务进度、历史报告、三维分数图示和逐样本证据。
- worker 规范化注册身份、采集资料、自动匹配已支持方案、采样、核验并发布报告；默认关闭公网采集。未启用时返回 NEEDS_INFO，不虚构分数。
- 最终分数由确定规则计算：服务可用性30%、功能声明一致性40%、交易行为可靠性30%；本包完整报告每份10A/7F/7B样本。LLM负责有来源声明提取及预测题翻译，不直接给声誉分。
- 完整预测方案限已经核实的 Fixed Price Native/Omen/IPFS 证据链；通用业务答案正确性、跨专项组合、跨独立提供方的同类完整复用仍未完成。历史交付文件可访问不代表实时推理在线。

## 十个 Agent 的数据性质

`data/public-reports-v1.tar.gz` 包含10个不同注册身份的最新完整历史报告及14,737个公开文件；报告UTC生成日期为2026-10-18，部分上海时间为19日凌晨。它们是已采集真实公开证据的归档交付，本次复用并离线核验，不是本机重新执行十个 Agent 的实时任务，也不是前端硬编码评分。

本轮已逐文件校验包内 SHA-256/长度，10份报告按当前规则从样本复算均与索引一致；完整导入的最终状态见本页“启动验收”。

| 对象 | 评价范围 | 综合分 |
| --- | --- | ---: |
| Brain DeFi #363709 | 历史增仓特例 | 97.93 |
| Olas #2135 | 历史预测 | 88.27 |
| Olas #2182 | 历史预测 | 90.56 |
| Olas #2198 | 历史预测 | 89.72 |
| Olas #2235 | 历史预测 | 98.71 |
| Olas #2267 | 历史预测，存在真实无效输出 | 29.80 |
| Olas #2340 | 历史预测 | 91.28 |
| Olas #2359 | 历史预测 | 84.39 |
| Olas #2360 | 历史预测 | 88.62 |
| Olas #4110 | 历史预测及登记日期补录 | 78.46 |

范围评分只能解释报告列明的样本、功能和时间，不代表 Agent 全部能力。

## 本机环境与最小修复

- Python 3.12.4、uv 0.9.3、Node 22.17.0、pnpm实际安装执行11.25.0、PostgreSQL17.11。
- uv未加入本机PATH，使用 `runtime/tools/uv-env/Scripts/uv.exe`。PATH的pnpm显示10.12.4，但项目执行按packageManager委派11.25.0；锁定安装日志确认该版本。
- `uv sync --locked`、`pnpm --dir apps/web install --frozen-lockfile`、前端typecheck/build已通过。首次pnpm安装因旧node_modules需要确认而在无TTY环境中中止；设置本次进程 `CI=true` 后成功。没有改依赖或锁文件。
- 新数据库独立使用 `runtime/platform-postgres`，监听 `127.0.0.1:55438`，库/角色 reputation。旧 `runtime/postgres`、链状态、证据和配置保留。
- 本机既有 `D:/web3-runtime` 是指向本仓库runtime的junction，用于复用已经安装的PG工具；PG数据目录本身不是junction。
- 三个启动/停止脚本写死旧目录名 block_chain_new_new，已移除该名称条件，保留仓库文件检查及数据库marker、进程、端口、防覆盖检查。
- PowerShell7下PG原生中文路径被错误解码，导致真实已启动的PG被误判身份不符。改用ASCII hex读取data_directory后按系统ANSI解码；start/stop一致按原生编码读取postmaster.pid，marker明确UTF-8读取。幂等start实际退出0；没有降低身份检查。
- 启动器退出时改为结束本次API进程树，避免Windows虚拟环境Python包装进程退出后留下Uvicorn。临时端口7755实际启动、默认worker `--once`、退出释放端口均PASS。本轮快捷启动器明确使用PowerShell7（实测7.6.5）；不承诺Windows PowerShell5.1的进程树清理重载。
- `.env` 是旧版配置（不含新版三个REPUTATION变量），未覆盖，也未加载。新版应用默认读取新建的 `runtime/platform-config/database-url.txt`；口令只保留在Git忽略的本地文件，未输出。
- 本机Docker引擎未运行，但新版无需Docker。

## LLM兼容性与本地配置

当前固定为DeepSeek Responses协议，不能只改配置切到OpenAI、Qwen、GLM。

- `services/platform/src/reputation_platform/model_analysis.py` 固定 `deepseek-flash`、`https://api.deepseek.com/responses` 和DeepSeek余额接口。
- `safe_http.py` 只允许凭证发往指定DeepSeek端点；请求/响应使用Responses字段和结构，不是通用Chat Completions。
- API key路径优先级：CLI `--key-file` → `REPUTATION_LLM_KEY_FILE` → `runtime/platform-config/llm-key-file.txt`（存另一个key文件的路径）→ `runtime/secrets/deepseek-api-key.txt`。key文件内容为单行API key。
- 后续最小切换范围包括新请求model/endpoint配置、凭证域名白名单、供应商余额逻辑、请求/响应协议差异。`question_translation.py` 用当前model/endpoint重建历史缓存请求；直接改常量会使历史证据核验失败，必须同时保留旧请求核验依据。本轮未重构。
- 官方入口：[DeepSeek API Keys](https://platform.deepseek.com/api_keys)、[Responses文档](https://api-docs.deepseek.com/api/create-response/)。免费页面读取可达，不代表本机模型调用已验证。

## RPC与网络

| 网络 | Chain ID | 当前配置端点 |
| --- | ---: | --- |
| Gnosis主网 | 100 | https://rpc.gnosischain.com |
| BSC主网 | 56 | https://api.zan.top/node/v1/bsc/mainnet |
| Base主网 | 8453 | https://api.zan.top/node/v1/base/mainnet |

`configs/generic-rpc.json` 与 `registration_discovery.py` 同时限制链、端点和认证。ZAN不是链协议要求，但当前网站Base/BSC链路固定其端点与认证，不能只填其他供应商URL。单独流动性探测CLI的PublicNode/BNB选项不代表网站全链路支持任意供应商。

ZAN文件路径优先级：CLI `--zan-key-url-file` → `REPUTATION_ZAN_KEY_FILE` → 调用方fallback → `runtime/secrets/zan-rpc-url.txt`。文件必须存**含项目密钥的完整ZAN Base mainnet HTTPS RPC URL**；即使查询BSC也从该格式提取项目key。个人配置用环境变量覆盖旧开发机fallback，不改已发布证据绑定的历史配置。

若使用ZAN，注册账号、创建项目并获得Base mainnet完整RPC URL；官方入口：[ZAN](https://zan.top)、[注册说明](https://docs.zan.top/docs/sign-up-and-log-in)、[快速开始](https://docs.zan.top/docs/quick-start-guide)。使用Gnosis公开端点或仅浏览归档报告不需要ZAN账号。

本机已有HTTP代理127.0.0.1:7897，但四个相关域名的系统DNS实测分别解析到198.18.0.41–44（非公网），SafeHttpClient的单次Gnosis eth_chainId尝试返回destination_policy_blocked，未取得RPC链ID。生产的pinned传输同样要求真实公网DNS，不会绕过SSRF校验。实时取证前需在本机代理/DNS中对这些域名配置真实公网解析；不要关闭目标地址检查。本轮未改系统代理/DNS。

## 启动验收

- 独立PG初始化及建表成功；API与默认public-off worker运行，首页、`/api/health`、`/api/agents`、`/openapi.json`均200。
- 浏览器实际提交2359，POST成功入队；worker处理为NEEDS_INFO/DONE，消息明确没有外部请求和新分数。任务ID与响应记录在 `runtime/local-verification-20261019/job-smoke.json`。
- CI同款评分边界用例 `python -m unittest discover -s tests -p test_scoring.py -v`：1 passed；三个PowerShell脚本语法通过。
- 完整公开包导入已成功（exit0，约13分钟），恢复14,723个原本不存在的runtime文件，10份报告在单一事务中写入新库。原件：`runtime/public-report-restore-799c7827ca73c01faec650e5573d2ad7/result.json`，`database_imported=true`、`network_requests=0`。
- 真实socket HTTP验收exit0：10个Agent/10份COMPLETE报告，逐个详情、报告及各一份真实附件均200且SHA匹配；API返回分数与报告一致；0活动任务；首页JS/CSS与本次dist逐字节一致。直接请求本地配置文件及通过证据接口越界请求均404。记录：`runtime/local-verification-20261019/api-verification.json`。
- 浏览器实际刷新后显示10/10完整范围分；从低到高排序、搜索2267只剩1/10、打开29.80分报告并查看99.34/0/0三维结果和真实Invalid response说明、打开2235的98.71分完整报告均成功。页面控制台未记录warning/error。截图位于 `runtime/local-verification-20261019/directory.jpg`、`report-scores.jpg`、`report-overall.jpg`、`job-public-off.jpg`。服务保持运行在 http://127.0.0.1:7754/ ，PG55438；进程记录（含启动时间用于核实归属）和日志位于同目录。

## 需要用户操作与下一步

浏览现有结果不需要外部账号。新增实时取证需要先解决上述DNS，再按需注册服务并在本机编辑器填入：

- `runtime/secrets/deepseek-api-key.txt`：自己的DeepSeek API key及可用余额。
- `runtime/secrets/zan-rpc-url.txt`：自己的完整ZAN Base mainnet RPC URL。

这些位置均受Git忽略；不要在聊天中发送密钥，也不要放到前端、命令行参数或根目录任意txt。`.env`不会自动加载；使用环境变量或显式`uv --env-file`，不要覆盖保留的旧.env。

重新启动已有展示（仓库根目录，PowerShell7，端口7754空闲时）：

```powershell
pwsh -NoProfile -File .\scripts\start_local_platform.ps1
```

或分别运行API与默认worker（终端保持打开）：

```powershell
.\scripts\start_local_postgres.ps1
.\.venv\Scripts\python.exe -X utf8 -m uvicorn reputation_platform.api:create_app --factory --host 127.0.0.1 --port 7754
# 另一个终端
.\.venv\Scripts\python.exe -X utf8 -m reputation_platform.worker
```

在凭证、DNS均就绪且用户另行确认付费调用后，先停止默认worker，再在新worker终端设置路径并启用公开模式；不要同时留下两个不同模式worker竞争同一队列：

```powershell
$env:REPUTATION_LLM_KEY_FILE = (Join-Path (Get-Location).Path 'runtime/secrets/deepseek-api-key.txt')
$env:REPUTATION_ZAN_KEY_FILE = (Join-Path (Get-Location).Path 'runtime/secrets/zan-rpc-url.txt')
.\.venv\Scripts\python.exe -X utf8 -m reputation_platform.worker --enable-public-readonly --proxy http://127.0.0.1:7897
```

本轮未验证新LLM调用、带凭证ZAN请求、新实时完整评分或链上写入；没有借用旧文档的费用授权。只对本轮受影响启动和复现路径做验证，没有运行依赖原开发机私有资料的全套集成测试。
