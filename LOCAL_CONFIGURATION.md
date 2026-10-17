# 本机凭证与历史配置位置

2026-10-18 已检查下列两个文件存在且为普通文件。提交前的本机敏感信息扫描仅将秘密读入内存作匹配比较，没有复制到新项目、输出内容或记录秘密摘要，也没有验证其当前有效性。

用户明确要求新会话复用这些位置，不要让用户重新发送密钥。凭证内容由确实需要它的后台 loader 在获准调用时读取，不贴进聊天、命令行、前端、源码、日志或证据包。

## 直接读取的位置

| 用途 | 本机绝对路径 | 文件内容与旧变量名 |
|---|---|---|
| DeepSeek API key | `D:/xjtu_project/block_chain_new/runtime/secrets/deepseek-api-key.txt` | 单行密钥；旧 loader 用 `MODEL_ANALYSIS_KEY_FILE` |
| ZAN Base 主网只读 RPC URL | `D:/xjtu_project/block_chain_new/runtime/secrets/base-mainnet-rpc-url.txt` | 单行完整 HTTPS RPC URL，URL 本身含密钥；旧 loader 用 `PUBLIC_BASE_RPC_SECRET_FILE`，provider 为 `zan` |

从新目录看，对应相对位置是 `../runtime/secrets/deepseek-api-key.txt` 和 `../runtime/secrets/base-mainnet-rpc-url.txt`。为避免启动目录影响，后台配置优先使用绝对路径。

不要把 RPC URL 当公开配置打印出来，也不要把 Base 主网只读 RPC 与 Anvil 的本地开发链混淆。普通网站用户不需要填写这些配置。

## 旧模型配置参考

文件：`D:/xjtu_project/block_chain_new/runtime/autonomous-deepseek-model-20261017-01.private.env`。

仅核实其中非秘密字段：`MODEL_ANALYSIS_PROVIDER=deepseek`、`MODEL_ANALYSIS_MODEL_ID=deepseek-flash`，以及指向上述密钥文件的 `MODEL_ANALYSIS_KEY_FILE`。旧实现曾成功调用固定 `POST https://api.deepseek.com/responses`。这属于 2026-10-17 的历史运行事实，不能承诺该型号、端点和额度在未来一直有效。

该配置还带历史模型启用和预算参数。不要直接加载后运行，更不能把它整份提交到新仓库。新项目当前没有实现配置 loader，`.env.example` 只提供无秘密模板，不表示相关配置已生效。

## 历史费用与调用记录

旧总滚动授权为 40 次请求、2 美元保守预留，包含原四次试点。2026-10-17 这次 30 对象分析完成后，封存账本合计 34 次、1.70 美元预留，实际账单费用未知。授权存在有效窗口，并可能已到期；不能把“剩余六次”当成永久或新项目独立额度。

- 结果汇总：`D:/xjtu_project/block_chain_new/runtime/declaration30-retained-results-seal-20261017-01.json`。
- 预算修订与四笔保留记录导入收据：`D:/xjtu_project/block_chain_new/runtime/ai-autonomous-maintenance-20261017-01/budget-application-04/receipt.json`。
- 原四笔导出：`D:/xjtu_project/block_chain_new/runtime/model-history-export-20261017-01/retained-model-history.private.json`，这是私有记录，不上传。

真实预算权威仍在旧数据库中的费用记录和修订，不由上述文字快照决定。新会话不创建新库、换 owner、换 provider 或重新申请同一意图来清除历史。新费用安排须明确承接旧记录或得到用户对新预算的明确授权。

## 旧服务配置只作定位

- `D:/xjtu_project/block_chain_new/runtime/ai-autonomous-maintenance-20261017-01/new-api.private.env`
- `D:/xjtu_project/block_chain_new/runtime/ai-autonomous-maintenance-20261017-01/new-worker.private.env`
- 更早原站：`D:/xjtu_project/block_chain_new/runtime/v2-demo-20261015-acceptance/api.env`

这些文件可能含数据库口令、运营 token 等秘密，并分别绑定不同数据库和旧源码。不要复制到新项目，不要用新源码直接启动旧配置，也不要让新项目占用旧库、证据库或端口。旧服务是否还在运行，须在真正需要时重新只读核实。

旧操作手册 `docs/runbooks/ZAN_RPC.md`、`DEEPSEEK_PRIVATE_PILOT.md` 可以帮助定位 loader，但部分进度和四笔试点预算文字滞后，不能据其重跑示例命令。

## 可移植性

本机路径说明可以随文档提交，秘密文件不随 Git 迁移。新仓库克隆到其他机器后，操作者需通过本地环境或 secret mount 配置自己的文件位置；不能把本机凭证自动上传给 GitHub 或新的部署平台。
