# 本地 LLM 配置与切换

LLM 用于从已保存资料提取功能声明、翻译预测问题；最终评分与独立证据核验仍按现有规则执行。浏览已经导入的十个 Agent 的历史报告不需要 LLM 凭证。以下示例只有占位符，不代表已经通过真实厂商调用验证。

## 在哪里填写

推荐只维护两个被 Git 忽略的本地文件：

1. `runtime/platform-config/llm.json`：API 基础地址、模型、协议和密钥文件路径。
2. `runtime/secrets/llm-api-key.txt`：用本地编辑器写入自己的单行 API Key，不加引号、不填 URL。

在项目根目录创建目录，再用本地编辑器保存下面的 JSON；也可首次复制 `templates/llm.example.json`，不要覆盖已有私密配置。不要把密钥放进命令行或聊天：

```powershell
New-Item -ItemType Directory -Force runtime/platform-config, runtime/secrets | Out-Null
```

```json
{
  "base_url": "https://YOUR_LLM_HOST/YOUR_API_PREFIX",
  "api_key_file": "runtime/secrets/llm-api-key.txt",
  "model": "YOUR_MODEL_ID",
  "api_style": "chat_completions"
}
```

把 `YOUR_LLM_HOST/YOUR_API_PREFIX` 替换为服务商文档中的 HTTPS API 基础地址，把 `YOUR_MODEL_ID` 替换为该账号确实可用的模型 ID。密钥文件中的内容只进入服务端请求头，不发送到前端。

本机仓库绝对位置为 `D:/大三上/软件前沿技术/区块链竞赛/web3-agent-reputation`，因此配置文件为 `D:/大三上/软件前沿技术/区块链竞赛/web3-agent-reputation/runtime/platform-config/llm.json`，示例密钥文件为 `D:/大三上/软件前沿技术/区块链竞赛/web3-agent-reputation/runtime/secrets/llm-api-key.txt`。配置中的相对密钥文件路径按仓库根目录解析。

## 配置优先级

默认自动读取 `runtime/platform-config/llm.json`，不需要额外的配置管理工具。可用 `REPUTATION_LLM_CONFIG_FILE` 指定另一个本地 JSON 文件。以下环境变量分别覆盖 JSON 中的同名配置：

| 环境变量 | 对应 JSON 字段 |
| --- | --- |
| `REPUTATION_LLM_BASE_URL` | `base_url` |
| `REPUTATION_LLM_API_KEY_FILE` | `api_key_file` |
| `REPUTATION_LLM_MODEL` | `model` |
| `REPUTATION_LLM_API_STYLE` | `api_style` |

密钥文件的完整优先级是：CLI `--key-file` → `REPUTATION_LLM_API_KEY_FILE` → 旧 `REPUTATION_LLM_KEY_FILE` → JSON 的 `api_key_file` → 原有 `runtime/platform-config/llm-key-file.txt` 路径指针 → 默认 DeepSeek 密钥文件。切换时检查是否遗留环境变量覆盖 JSON，避免以为修改文件却仍使用旧值。模板将旧变量注释，已有本地环境中的旧变量需要自行清除或更新。

应用不会自动加载 `.env`。如沿用环境变量方式，使用当前 PowerShell 的 `$env:REPUTATION_LLM_...` 设置，或用 `uv run --env-file .env.local ...` 显式加载。Base URL 即使没有 Key，也作为本地私人配置处理，不写入受 Git 跟踪的文件。

## 各供应商配置示例

以下各行均为占位符，需从对应服务的官方控制台或 API 文档取得实际值。`api_key_file` 可固定为上面的单一私密文件，切换厂商时在本地替换其内容。

| 服务 | `base_url` 占位示例 | `model` 占位示例 | `api_style` |
| --- | --- | --- | --- |
| DeepSeek 通用接口 | `https://YOUR_DEEPSEEK_HOST/YOUR_API_PREFIX` | `YOUR_DEEPSEEK_CHAT_MODEL` | `chat_completions` |
| OpenAI | `https://YOUR_OPENAI_HOST/YOUR_API_PREFIX` | `YOUR_OPENAI_CHAT_MODEL` | `chat_completions` |
| 通义千问 Qwen | `https://YOUR_QWEN_HOST/YOUR_OPENAI_COMPATIBLE_PREFIX` | `YOUR_QWEN_MODEL` | `chat_completions` |
| GLM | `https://YOUR_GLM_HOST/YOUR_OPENAI_COMPATIBLE_PREFIX` | `YOUR_GLM_MODEL` | `chat_completions` |
| 自定义中转站 | `https://YOUR_RELAY_HOST/YOUR_API_PREFIX` | `YOUR_RELAY_MODEL_ID` | `chat_completions` |
| 兼容 Responses 的服务 | `https://YOUR_RESPONSES_HOST/YOUR_API_PREFIX` | `YOUR_RESPONSES_MODEL` | `responses` |

API 前缀由服务商决定：需要 `/v1` 时将其包括在 `base_url` 中；需要其他前缀时完整保留。程序不会给所有厂商强加 `/v1`。也可以给出已经带 `/chat/completions` 或 `/responses` 的完整地址，程序按选定协议规范化端点，避免重复拼接。

显式配置 Base URL、模型或协议中的任一项后，缺省协议为 `chat_completions`，但必须同时提供 Base URL 与模型名，不会把缺项静默补成旧模型。没有这些连接配置、只指定新旧密钥文件时，保留原有 DeepSeek Responses 与模型默认值，以便既有本地配置继续工作。协议、模型或参数不受供应商支持时会明确失败，不自动切换模型。Chat Completions 模型须支持普通文本消息并在回答中提供约定 JSON；工具调用、多模态、流式协议及自动路由不在本次适配范围。

要恢复仅用旧 Key 指针的配置，先将本地 `llm.json` 改名保存（例如 `llm.json.disabled`），并清除 `REPUTATION_LLM_BASE_URL`、`REPUTATION_LLM_MODEL`、`REPUTATION_LLM_API_STYLE` 环境覆盖；旧 `REPUTATION_LLM_KEY_FILE` 与旧路径指针仍按原方式读取。不删除或改写历史证据。

## LLM 代理与 DNS

这些设置只影响后台 LLM 请求。`REPUTATION_LLM_PROXY` 未设置或为空时自动选择网络路径；设为 `direct` 强制直连，也可填写 `http://PROXY_HOST:PROXY_PORT`、`https://PROXY_HOST:PROXY_PORT` 或 `socks5://PROXY_HOST:PROXY_PORT`。请替换占位符，不把本机代理地址或认证信息写入公开文件。

代理选择顺序是：`REPUTATION_LLM_PROXY` → 旧 CLI `--proxy` → 标准 `HTTPS_PROXY` / `ALL_PROXY`（也识别相应小写变量）→ Windows/macOS 系统静态代理 → 直连。HTTPS 优先使用 `HTTPS_PROXY`，其次 `ALL_PROXY`；`HTTP_PROXY` 仅用于 HTTP，不能作为 HTTPS LLM 请求的默认替补。`NO_PROXY` 始终按原始目标域名匹配，包括专用变量或 CLI 指定的代理；系统代理自身的绕过规则也会应用于系统代理。程序不执行 PAC/WPAD，也拒绝 `socks5h://` 等让代理远程解析目标域名的模式。

在当前 PowerShell 中可按需要选择一种方式，然后重新启动使用该环境的 LLM 脚本或长驻进程：

```powershell
# 自动识别；没有这个环境变量时可省略此行。
Remove-Item Env:REPUTATION_LLM_PROXY -ErrorAction SilentlyContinue
# 或强制直连：$env:REPUTATION_LLM_PROXY = "direct"
# 或显式代理：$env:REPUTATION_LLM_PROXY = "http://PROXY_HOST:PROXY_PORT"
$env:REPUTATION_LLM_DNS_MODE = "auto"
```

`REPUTATION_LLM_DNS_MODE` 只接受 `auto`（默认）或 `system`。两者都先解析系统 DNS，并要求目标的全部地址为公网；DNS 查询失败、混合公网/保留地址或任何私网结果都会拒绝连接。`auto` 仅在**全部**系统 DNS 结果都位于 Fake-IP 网段 `198.18.0.0/15`，且已选定代理时，才向 Cloudflare 的固定公网 IP 发起验证证书的 HTTPS DNS 查询，查询 A 和 AAAA；回退结果仍须全部通过公网检查。`system` 禁用此回退；直连模式也不会触发它。

通过验证后，实际连接固定到已核验的数字 IP，HTTP/HTTPS 代理使用数字 IP CONNECT，SOCKS5 也使用数字目标；代理端必须支持数字 IP CONNECT。TLS SNI、证书校验和 HTTP Host 仍使用原域名，不跟随重定向，也不降低 TLS 验证标准。无需修改系统 DNS 或代理软件配置。Windows/macOS 系统静态代理读取有平台分支；本轮没有在 Linux/macOS 真机验证。

诊断写入每次请求的 `<request-key>.network.json`，只含代理来源/类型、Fake-IP是否出现、DNS来源、安全状态、阶段与错误类别，不记录目标域名、数字IP或代理认证。`system_dns`失败时检查系统解析；`independent_dns`失败时检查所选代理是否能到达HTTPS DNS服务；`target_connect`的ProxyError/超时应检查代理可用性与数字目标支持。`destination_policy_blocked`保持拒绝私网/混合DNS，Fake-IP下若没有代理或选择了system模式也会拒绝。LLM请求期间屏蔽httpx/httpcore可能输出私人地址/请求头的INFO/DEBUG日志，其他线程日志保持原行为。

同步系统DNS解析本身的等待时间由操作系统控制；解析完成后，独立DNS、连接和响应读取共用剩余时间预算。无法安全取得公网地址时应修正可信代理配置或解析服务可达性，不要添加保留网段白名单或关闭证书校验。

## 安全与历史记录

- 仅允许受控 HTTPS 公网端点，拒绝 URL 用户名/密码、查询参数、片段、内网地址及不安全 DNS 解析；不能把 Key 放进 Base URL。
- 自定义端点不会关闭现有公网 DNS 校验、IP 固定、超时、响应大小限制或凭证作用域校验。Fake-IP 仅按上述受限条件回退；不能安全取得公网地址时拒绝连接。
- 配置标识区分模型、协议及端点，隔离新翻译缓存；历史报告仍按其保留证据核验。配置变更可能使后续任务需要新翻译，因此真实执行前应评估费用。
- `.gitignore` 覆盖 `.env`、`.env.local`、`.env.*.local`、`secrets/` 和整个 `runtime/`；没有忽略所有 `.txt`。`.env.example` 只提供占位模板。`.gitignore` 无法保护已经被 Git 跟踪的文件，也不能保护复制到其他目录的配置。

可在根目录检查当前约定路径的忽略状态，输出只含路径与规则：

```powershell
git check-ignore -v -- .env.local runtime/platform-config/llm.json runtime/secrets/llm-api-key.txt runtime/secrets/zan-rpc-url.txt
git ls-files -- .env '.env.*' 'runtime/*' 'secrets/*'
```

第二条正常只应列出不含凭证的示例。若发现真实私密文件已被跟踪，先停止提交并人工评估移出索引和轮换凭证；不要擅自改写 Git 历史。

## 切换、重启与验证

1. 用本地编辑器修改 `runtime/platform-config/llm.json` 的 `base_url`、`model`、`api_style`；在指定密钥文件内填写对应 Key。
2. 清除或更新覆盖 JSON 的旧 LLM 环境变量，保留需要的数据库/RPC 配置。
3. 已运行网站可以继续浏览历史报告。JSON 配置由每次 LLM 脚本启动时读取；本次修改了 worker 导入的历史核验模块，应用本次代码或更改长驻进程环境变量后应重启。先在自己启动它的终端按 `Ctrl+C`，然后重新运行下列默认本地启动命令：

```powershell
pwsh -NoProfile -File .\scripts\start_local_platform.ps1
```

默认 `public-off` 只启动本地服务，不发付费模型请求。它会复用本项目数据库；不要停止、清理或重建数据库。启动器不接管占用 7754 端口的既有服务，若服务由其他终端管理，应先确认其所属启动器。

打开 [本地网站](http://127.0.0.1:7754/)，检查已有 Agent 目录和历史报告；访问 [健康接口](http://127.0.0.1:7754/api/health) 应返回数据库就绪。此步骤只能确认平台可用，不能证明真实模型凭证有效。

不加 `--execute` 的声明分析/预测翻译脚本为准备模式。真正调用需在明确授权费用后，使用对应脚本的 `--execute` 和上述 LLM 网络设置，或启用网站公共只读任务流程。不要仅为检查配置而批量重评十个 Agent。

### 只检查配置，不连接模型

填好四项与单行 Key 后，在仓库根运行下面命令。它只检查本地配置、Key 格式和精确端点作用域；不解析 DNS、不连接模型，也不输出配置值。它不能确认供应商可用性或账号权限。

```powershell
@'
from reputation_platform.settings import load_llm_config, load_llm_key_file
from reputation_platform.safe_http import PublicTarget, SafeHttpClient
try:
    config = load_llm_config()
    SafeHttpClient((PublicTarget("config-check", config.endpoint, "POST"),),
        enabled=True, provider_config=config, provider_key_file=load_llm_key_file(), pin_public_dns=True)
except (RuntimeError, ValueError, OSError):
    raise SystemExit("配置未通过：请检查四项配置、覆盖环境变量及单行 Key 文件。") from None
print("本地 LLM 配置与 Key 格式通过；没有发起网络请求。")
'@ | .\.venv\Scripts\python.exe -X utf8 -
```

### 可选免费连通性与模型检查

先在私密 `runtime/platform-config/llm.json` 中指定要检查的 `model`，并清除不需要的环境覆盖，再在仓库根运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\scripts\check_llm_connection.py
```

该检查按生效配置只发送 `GET models`，检查网络、凭证及列表中是否包含指定模型，不发起推理或生成请求。供应商未提供兼容的模型列表接口时会报告检查失败；不能据此断言其推理接口不可用。模型在列表中也不能证明其推理权限、JSON 遵循能力或效果；真实推理需另行确认。

## 网络适配实际验证（2026-10-19）

Windows本机自动读取系统HTTP代理，在Fake-IP环境中经独立HTTPS DNS与固定公网IP连接，免费GET models返回HTTP200并列出`gpt-6-luna`。用户另行授权后只执行一次真实Chat Completions，HTTP200、模型匹配、回答OK，usage为11输入+5输出=16 token，没有重试、批量评价或链上交易。私密Base URL和Key未写入本说明，Key仍需用户轮换此前在聊天暴露的值。

既有平台未中断；健康接口数据库ready、10份历史报告与各一附件、3个前端资源均通过回归，评分和证据摘要未变。跨平台代理/DNS/安全边界采用Mock测试，Linux/macOS和远程认证代理未进行真机验证；免费模型列表成功也不能证明所有评分任务的JSON质量或模型效果。

本轮最终76项LLM/缓存/网络测试通过，其中新增网络覆盖40项（传输23、代理选择7、集成10）；另6项原HTTP/Provider/pinned/ZAN边界测试通过。包含直连公网DNS、HTTP/HTTPS代理、SOCKS5、双层TLS身份、Fake-IP、SSRF/重绑定、异常/超时、日志脱敏和仅GET models授权。锁文件检查与Python编译通过。测试命令：`.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -p 'test_llm*.py' -v`。

## 前轮通用配置验证（历史）

Mock 覆盖 Chat Completions / Responses 请求解析、四项切换、旧变量兼容、超时/异常响应、SSRF/DNS、凭证作用域和转义回显脱敏；缓存用例验证模型隔离、历史材料及篡改拒绝。旧网络边界、引用校验与评分回归通过。全程没有真实模型调用或链上交易。

44 个相关单元测试通过（LLM 29、缓存/离线声明 7、旧边界 8）。可复跑本轮新增测试：`.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -p 'test_llm*.py' -v`。

92 份已有翻译缓存、9 份翻译材料离线核验通过。原 7754 与临时新代码 API 均通过 10 个 Agent / 10 份历史报告 / 各一附件回归，分数、报告/附件摘要及前端资源字节保持一致；私密配置访问均为 404。浏览器验证目录和 2235 报告加载完成，控制台未记录 warning/error。临时 API 已停止，原网站未中断。

本轮已在0活动任务时核对进程身份并重载默认 public-off Worker，错误日志为空，网站/数据库仍健康。填写 JSON 后，下一次 LLM 脚本会读取新值；只有更改长驻进程环境变量或再次修改代码时才需重载。本次后台进程身份记录见 `runtime/llm-verification-20261019/worker-reload.json`，旧轮记录里的 Worker PID 已过时。

真实供应商可用性、模型 JSON 遵循能力和账号权限尚未验证；旧声明分析的完整原始投影/observation 不在本机公开归档中，不能宣称已完成该真实资产的全部重建。验证收据位于被忽略的 `runtime/llm-verification-20261019/`。
