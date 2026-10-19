# 本机凭证与历史配置位置

2026-10-18 已检查下列两个文件，并在本轮后台真实调用中分别用于 DeepSeek 与 ZAN 历史只读查询。提交前敏感信息扫描仅在内存匹配，不复制秘密到新项目、不输出内容或秘密摘要。当前有效不代表未来凭证永不失效。

用户明确要求新会话复用这些位置，不要让用户重新发送密钥。凭证内容由确实需要它的后台 loader 在获准调用时读取，不贴进聊天、命令行、前端、源码、日志或证据包。

## 直接读取的位置

| 用途 | 本机绝对路径 | 文件内容与旧变量名 |
|---|---|---|
| DeepSeek API key | `D:/xjtu_project/block_chain_new/runtime/secrets/deepseek-api-key.txt` | 单行密钥；旧 loader 用 `MODEL_ANALYSIS_KEY_FILE` |
| ZAN Base 主网只读 RPC URL | `D:/xjtu_project/block_chain_new/runtime/secrets/base-mainnet-rpc-url.txt` | 单行完整 HTTPS RPC URL，URL 本身含密钥；旧 loader 用 `PUBLIC_BASE_RPC_SECRET_FILE`，provider 为 `zan` |

从新目录看，对应相对位置是 `../runtime/secrets/deepseek-api-key.txt` 和 `../runtime/secrets/base-mainnet-rpc-url.txt`。为避免启动目录影响，后台配置优先使用绝对路径。

不要把 RPC URL 当公开配置打印出来，也不要把 Base 主网只读 RPC 与 Anvil 的本地开发链混淆。普通网站用户不需要填写这些配置。

新工具已核实同一 ZAN 项目密钥可用于固定 BSC 端点，并实际读取历史状态。SafeHttpClient 只在实际传输时添加私有密钥段，计划与观测保留无密钥地址；原先无密钥地址加 Bearer 返回 400，不能继续沿用。凭证不允许发送到注册资料指定的其他 RPC，见 ADR-0003。

## 旧模型配置参考

文件：`D:/xjtu_project/block_chain_new/runtime/autonomous-deepseek-model-20261017-01.private.env`。

仅核实其中非秘密字段：`MODEL_ANALYSIS_PROVIDER=deepseek`、`MODEL_ANALYSIS_MODEL_ID=deepseek-flash`，以及指向上述密钥文件的 `MODEL_ANALYSIS_KEY_FILE`。旧实现曾成功调用固定 `POST https://api.deepseek.com/responses`。这属于 2026-10-17 的历史运行事实，不能承诺该型号、端点和额度在未来一直有效。

该配置还带历史模型启用和预算参数。不要直接加载后运行，更不能把它整份提交到新仓库。新项目使用显式 CLI 和固定端点凭证加载，不加载旧 `.env`，不恢复旧预算门禁；`.env.example` 只是无秘密模板。

2026-10-18 已只读核对 [DeepSeek 官方文档](https://api-docs.deepseek.com/api/create-response/)，当前文档仍列出 `deepseek-flash` 与 `POST /responses`。本轮真实调用与余额检查结果以 STATUS 为准。

## 当前模型使用授权

2026-10-18 用户明确：不设置请求数或费用上限，使用现有 DeepSeek 余额，余额不足时告知，不因旧费用规定停工。此前 20 次/1 美元提议未生效，不再实现或读取旧预算门禁。实际模型 usage 与响应保留，不自动充值；该授权不包含付费 Agent 业务、签名或资产操作。

## 历史费用与调用记录（仅存档）

旧总滚动授权为 40 次请求、2 美元保守预留，包含原四次试点。2026-10-17 这次 30 对象分析完成后，封存账本合计 34 次、1.70 美元预留，实际账单费用未知。授权存在有效窗口，并可能已到期；不能把“剩余六次”当成永久或新项目独立额度。

- 结果汇总：`D:/xjtu_project/block_chain_new/runtime/declaration30-retained-results-seal-20261017-01.json`。
- 预算修订与四笔保留记录导入收据：`D:/xjtu_project/block_chain_new/runtime/ai-autonomous-maintenance-20261017-01/budget-application-04/receipt.json`。
- 原四笔导出：`D:/xjtu_project/block_chain_new/runtime/model-history-export-20261017-01/retained-model-history.private.json`，这是私有记录，不上传。

上述旧记录保留，不清除或改写；它们不再是本项目调用的预算权威。当前使用遵循用户最新余额授权，不需要迁移旧费用账本或重建费用审批系统。

## 旧服务配置只作定位

- `D:/xjtu_project/block_chain_new/runtime/ai-autonomous-maintenance-20261017-01/new-api.private.env`
- `D:/xjtu_project/block_chain_new/runtime/ai-autonomous-maintenance-20261017-01/new-worker.private.env`
- 更早原站：`D:/xjtu_project/block_chain_new/runtime/v2-demo-20261015-acceptance/api.env`

这些文件可能含数据库口令、运营 token 等秘密，并分别绑定不同数据库和旧源码。不要复制到新项目，不要用新源码直接启动旧配置，也不要让新项目占用旧库、证据库或端口。旧服务是否还在运行，须在真正需要时重新只读核实。

旧操作手册 `docs/runbooks/ZAN_RPC.md`、`DEEPSEEK_PRIVATE_PILOT.md` 可以帮助定位 loader，但部分进度和四笔试点预算文字滞后，不能据其重跑示例命令。

## 可移植性

新项目本机平台另外使用本目录 `runtime/platform-config/database-url.txt`（PG 连接秘密）、`db-password.txt` 和 `profiles.json`（已适配对象/保留证据引用）。它们由本机启动与运营配置产生，不复用旧数据库，均被 Git 忽略且不能公开下载。独立 PG 为 127.0.0.1:55438，API 为 127.0.0.1:7754；命令和实际验收见 [LOCAL_PLATFORM](docs/runbooks/LOCAL_PLATFORM.md)。

本机路径说明可以随文档提交，秘密文件不随 Git 迁移。新仓库克隆到其他机器后，操作者需通过本地环境或 secret mount 配置自己的文件位置；不能把本机凭证自动上传给 GitHub 或新的部署平台。

## Codex 本机 HTTP 代理（2026-10-18）

用户明确要求先修复反复重连。检查发现 Windows 系统代理已启用 `127.0.0.1:7897`，但 Process/User/Machine 的代理环境变量均为空；桌面日志另有 WebSocket 建连失败。已将以下变量写入当前 Windows 用户环境，并发送环境变更通知：

```text
HTTP_PROXY=http://127.0.0.1:7897
HTTPS_PROXY=http://127.0.0.1:7897
ALL_PROXY=http://127.0.0.1:7897
NO_PROXY=localhost,127.0.0.1,::1
```

使用显式代理、`--retry 0` 的 curl 检查：GitHub 仓库 API 返回 HTTP 200 / CONNECT 200；未认证 GET Codex responses 返回 HTTP 405 / CONNECT 200。两次 curl 均退出 0，证明代理路径可用，不代表已验收桌面 WebSocket。环境写入及通知命令退出 0，已回读确认。

正在运行的 Codex 进程不能从子 shell 热继承变量，需完全退出桌面应用后重新启动。重启后用实际消息确认不再反复重连；当前状态为 `RESTART_VERIFICATION_PENDING`，不重复上述 HTTP 检查。当前会话的外网工具命令显式设置代理。这是开发工具配置，不是新项目获准主动评价公网 Agent。

已通过系统 `skill-installer` 安装用户指定仓库的 `skills/productivity/grill-me`，其内容调用同仓 `skills/productivity/grilling`，故一并安装；成功命令均退出 0。安装位置分别为 `C:/Users/yq/.codex/skills/grill-me` 和 `C:/Users/yq/.codex/skills/grilling`。本轮已读取指令使用，后续回合可发现这些 skills。
