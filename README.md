# 基于多源证据的 Web3 Agent 声誉评价平台

面向公开注册的 Web3 Agent，关联注册资料、自然语言功能声明、接口、合约和历史交易，生成有证据可追溯的中文评价报告。

固定评价维度为**服务可用性、功能声明一致性、交易行为可靠性**，综合权重为30% / 40% / 30%。资料不足时明确显示缺项，不补成0分或满分。用户在网站提交注册标识后，由平台自动匹配已支持的评价方案。

这是对原项目的重新实现。当前采用Vue 3 + TypeScript前端、FastAPI API、独立worker和PostgreSQL；不需要运行原项目的微服务、合约或Docker Compose。

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
REPUTATION_ZAN_KEY_FILE=runtime/secrets/zan-rpc-url.txt
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

数据包约16.5MB，恢复公开原件到原runtime相对目录，由已有核验器重建分数后入库；不会覆盖不同内容的本地文件，也不包含个人账号或数据库。首次导入会离线核验约1.5万份依赖，可能耗时数分钟。

打开第一个终端，启动网页和API：

```powershell
uv run --env-file .env --no-sync python -m uvicorn reputation_platform.api:create_app --factory --host 127.0.0.1 --port 7754
```

打开第二个终端，在相同目录启动worker：

```powershell
uv run --env-file .env --no-sync python -m reputation_platform.worker
```

浏览器打开 **[http://127.0.0.1:7754/](http://127.0.0.1:7754/)**。无需另开Vite。两个终端应保持运行，Ctrl+C可停止对应进程。

默认worker关闭公网采集，可以浏览已有数据；新提交会说明尚未开启公开取证。需要实际收集免费公共只读证据时，停止默认worker，改为：

```powershell
uv run --env-file .env --no-sync python -m reputation_platform.worker --enable-public-readonly --proxy http://127.0.0.1:7897
```

当前受控网络实现要求本机HTTP代理`127.0.0.1:7897`，不是任意代理地址均可。上述开关只开启已支持的公开只读流程，不发起付费Agent任务、签名或链上写入。

网站包含“浏览Agent声誉”和“接入Agent产生评价”两个入口。目录默认按综合分从高到低排序，支持搜索、状态/范围筛选；详情包含历史报告、三维解释、样本与原始证据。可提交的规范身份示例：

```text
eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2359
```

示例不保证未来一定有足够证据出完整分数，平台按实际资料返回结果。

## 自备RPC和LLM账号

**个人账号、密钥、数据库、费用记录和私有配置不随仓库提供。其他使用者需要配置自己的服务。**

| 用途 | 当前接入 | 需要准备什么 |
| --- | --- | --- |
| Gnosis历史查询 | 固定公开RPC `https://rpc.gnosischain.com` | 当前可使用公开端点，不必填私人账号；能否取得历史数据取决于上游可用性 |
| BSC / Base注册及历史查询 | 已审查的ZAN固定端点 | 自己的ZAN项目；把该项目的完整Base mainnet RPC URL保存为一行文件，通过`REPUTATION_ZAN_KEY_FILE`指定 |
| 声明提取、预测问题中文翻译 | 固定DeepSeek Responses接入，`deepseek-flash` | 自己的DeepSeek API key与可用余额；单行key文件通过`REPUTATION_LLM_KEY_FILE`指定 |
| 平台存储 | PostgreSQL | 自己的数据库、账号、密码，通过`REPUTATION_DATABASE_URL`指定 |

先创建被Git忽略的`runtime/secrets/`，用本机编辑器填入自己的文件。LLM文件存**API key**；ZAN文件存**含项目密钥的完整RPC URL**，不是裸key。只把文件路径放进环境配置，不把文件内容放到命令行、前端或GitHub PR里。

凭证路径也可在相关采集CLI中通过显式`--key-file`或`--zan-key-url-file`指定，优先于环境变量。原开发机可用`runtime/platform-config/llm-key-file.txt`保存已有key文件的路径，避免复制密钥。普通网站用户不需要填写后台账号。

评分计算与离线核验本身不依赖LLM直接给分；但**当前网站对新就绪预测任务会调用中文翻译步骤**，没有已验证翻译缓存时，应配置自己的DeepSeek key。仅运行网页、浏览原报告或执行不需要模型的通用资料核验，不需要模型余额。

RPC不是任意供应商网关：链、端点与认证方式由后台固定白名单控制，注册资料不能指定RPC。原有`configs/`部分文件是已发布证据所绑定的历史配置，不要为了填个人密钥而改写；使用上面的本地凭证入口。更换RPC供应商需要单独适配。

## 数据与当前完成范围

开发机已完成10个不同真实公共Agent的完整范围评分，综合分29.8–98.71：9个复用历史预测方案，1个历史增仓特例。具体对象、真实退出码及限制见[STATUS.md](STATUS.md)。范围评分不代表Agent全部能力，历史交付文件可访问也不等于实时推理在线。

**仓库包含经过审计的完整评分发布包**`data/public-reports-v1.tar.gz`，覆盖10个不同真实Agent的最新完整报告及核验必需公开证据。按上文导入后即可浏览；只浏览和核验这些已有结果不需要配置RPC或LLM密钥。

未导入前新数据库为空。公开包不等于开发机的整个runtime或数据库：不包含个人密钥、私有配置、费用流水、临时日志、旧试运行报告，也不把38个候选和46份历史报告冒称全已随包分发。前端dist和依赖仍需自行安装/构建。

可以在网页提交受支持身份自行取证，或导入自己合法取得的完整证据包。导入时须保留所有被manifest引用的原件及相对目录；仅有一份report.json不能替代完整证据：

```powershell
uv run --env-file .env --no-sync python scripts/import_local_report.py runtime/YOUR_REPORT_DIRECTORY
```

完整预测评分目前限已核实的Fixed Price Native/Omen/IPFS证据链；未知协议、证据不足或未适配能力会列出缺项。通用功能正确性、跨专项组合及第二独立提供方的同类完整复用仍有待完善。浏览器桌面/手机视觉验收以用户实际试用反馈继续改进；构建或HTTP成功不当作视觉验收。

## 开发、验证与仓库

- [PLAN.md](PLAN.md)：当前任务和推进顺序。
- [STATUS.md](STATUS.md)：实际完成、验证记录、限制和Git/PR状态。
- [docs/runbooks/LOCAL_PLATFORM.md](docs/runbooks/LOCAL_PLATFORM.md)：原开发机Windows快捷启动及运行记录。该快捷脚本依赖原机工具目录；其他机器优先使用本页的通用入口。
- [GIT_SETUP.md](GIT_SETUP.md)：原项目断开远程、新实现接入及PR方式。
- [docs/adr/](docs/adr/)：评分与证据规则；历史政策和已发布证据保持可复算。

部分真实集成验收依赖未入Git的证据和独立PostgreSQL，缺少条件时应显示NOT_RUN/BLOCKED，不把skip当作完整集成通过。只运行必要受影响验证，复用已有有效结果。

目标仓库：[Ryanjxy123/web3-agent-reputation](https://github.com/Ryanjxy123/web3-agent-reputation)。本次通过重构PR替换项目实现，保留远程历史，不强推main；个人密钥、私有运行目录和数据库不上传，已完成评分以独立公开证据包交付。
