# ZAN Base 本地配置

在本地编辑器创建`secrets/zan-base-rpc.txt`，存一行自己的完整Base Mainnet HTTPS RPC URL。文件内容格式如下，占位符必须由自己的ZAN项目凭证替换：

```text
https://api.zan.top/node/v1/base/mainnet/YOUR_ZAN_API_KEY
```

`secrets/`已被Git忽略。不要将真实URL写入源码、配置模板、命令行参数或前端。无需修改`configs/`中已绑定历史证据的网络配置。Windows、Linux和macOS的Python读取机制相同；文件支持UTF-8及UTF-8 BOM。

## 文件路径和启动

凭证选择顺序：CLI `--zan-key-url-file` → `REPUTATION_ZAN_KEY_FILE` → 私密`runtime/platform-config/zan-key-file.txt` → 存在的`secrets/zan-base-rpc.txt` → 调用方历史配置fallback → 原默认`runtime/secrets/zan-rpc-url.txt`。环境变量及指针中的相对路径以项目根目录为基准；旧CLI路径行为保留。

使用推荐路径时，队员只需写入自己的RPC URL并运行已有启动流程。需要自选路径时，在被忽略的`runtime/platform-config/zan-key-file.txt`保存该文件的路径，例如`secrets/zan-base-rpc.txt`；不要把RPC URL写进这个路径指针。

PowerShell启动器`start_local_platform.ps1`在未设置该变量时，通过同一Python配置函数自动导出`REPUTATION_ZAN_KEY_FILE`给API/Worker及子进程，退出后恢复启动终端原环境；不会改系统环境变量。直接运行Python或在Linux/macOS部署时，采集进程也通过同一函数读取本地文件，无需依赖PowerShell。

FastAPI主要负责网站、任务和历史报告，不在健康接口中调用RPC；实际链上查询由Worker调用的采集模块读取凭证。默认启动仍是`public-off`，填写RPC不会自动触发评价或模型调用。

## 只读检查

在项目根运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\scripts\check_zan_connection.py
```

Linux/macOS对应使用`.venv/bin/python scripts/check_zan_connection.py`。脚本只调用`eth_chainId`，确认`0x2105`/8453后调用`eth_blockNumber`；无重试、无签名、无链上交易。诊断及脱敏原始响应位于被忽略的`runtime/zan-base-check-*`。

若需整体重启，在原启动终端停止自己的启动器，再运行：

```powershell
pwsh -NoProfile -File .\scripts\start_local_platform.ps1
```

已有7754服务运行时无需为检查RPC重启；启动器不会接管已占用的端口。网站`http://127.0.0.1:7754/`与`/api/health`只验证平台及数据库，不能替代RPC实测。

## 网络及安全

ZAN固定Base/BSC端点及只读方法白名单保持不变。凭证仅在传输时附加，公开请求计划与证据URL不含项目Key；JSON转义的凭证回显及第三方库日志也会脱敏。未带ZAN凭证的Agent Endpoint和Gnosis仍使用原网络路径，不能让Agent指定代理或任意RPC。

ZAN请求复用现有受控传输：专用`REPUTATION_ZAN_PROXY` → CLI代理 → `HTTPS_PROXY`/`ALL_PROXY` → Windows/macOS系统静态代理 → 直连。专用变量可为`direct`或HTTP/HTTPS/SOCKS5代理URL；`NO_PROXY`针对原目标生效。它不读取LLM专用代理设置。

`REPUTATION_ZAN_DNS_MODE=auto`为默认值：仅全部系统DNS结果为198.18/15 Fake-IP且存在代理时，通过固定公网IP的证书验证HTTPS DNS获取A/AAAA；全部结果仍须公网，再固定数字IP连接，保留原域名Host/TLS身份。`system`禁用该回退。私网、混合地址、异常DNS仍拒绝，不跟随重定向、不关闭证书验证。不执行PAC/WPAD或支持socks5h远程DNS；独立DNS不可达时需检查可信代理网络。同步系统DNS等待时间由操作系统控制。

## 2026-10-19 本机记录

已用系统HTTP代理安全处理Fake-IP；项目SafeHttpClient实测eth_chainId=8453、eth_blockNumber=52,804,922。实际注册发现模块`DiscoveryEvidence/_rpc`再次取得8453，证明历史配置中的旧开发机凭证路径已由本地选择机制正确覆盖。共3次只读RPC，0交易、0模型调用、0Agent评价。

原7754网站和数据库未中断；确认0活动任务后仅重载既有默认public-off Worker，其进程内验证凭证有效、环境路径一致，启动检查本身未发RPC。10份历史报告/各一附件、3个前端资源回归通过，评分与证据摘要一致。进程记录`runtime/zan-base-verification-20261019/worker-reload.json`及`worker-startup-check.json`；此前Worker PID记录已过时。

ZAN配置/脱敏/自动网络集成5项测试通过；既有LLM/缓存/网络76项覆盖经回归，脱敏格式兼容性问题修正后29项LLM重测通过，另原HTTP/pinned/provider边界5项通过。Linux/macOS和BSC账号权限未做真实请求验证。

该Key曾出现在聊天中，应在ZAN控制台轮换。轮换后只替换本地凭证文件的一行URL；下次新建客户端读取新值，无需修改源码或指针。未提交或推送代码。
