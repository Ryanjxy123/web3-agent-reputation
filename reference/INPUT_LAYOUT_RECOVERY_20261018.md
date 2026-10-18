# 预测输入根文件恢复：两真实对象的有界可行性结果

结论：固定的两条 `metadata.json` HTTP404 均由读取布局不匹配造成；同一官方网关的根CAR成功返回且通过逐块CID校验。两份输入实际都是 **UnixFS File根节点**，不是包含 `metadata.json` 的目录。可以实现共用的根文件支持，无需按Agent名称或注册号定制。恢复输入不等于完成评分。

## 固定对象与真实结果

按各对象原资格记录顺序，分别取**首条**明确HTTP404；未按任务结果挑选，未读取交付输出。

| 注册号 | 原资格位置 | 请求号前缀 | 根CAR | 真实输入 | 原始字段 | 实际工具 |
|---|---|---|---|---|---|---|
| 2135 | 0 | `0xb9514f61…` | HTTP200，380字节，1块 | UnixFS Type=2，272字节，无目录链接 | `prompt/tool/nonce` | `prediction-request-rag-claude` |
| 2267 | 0 | `0x1564e026…` | HTTP200，264字节，1块 | UnixFS Type=2，156字节，无目录链接 | `prompt/tool/nonce` | `prediction-request-rag` |

两份原始JSON均没有 `request_context`，因此不能直接声称已经定位Omen市场。本子任务只认证“内容与既有官方索引CID一致”；原collector在404前未保存该记录的链事件anchors，本子任务未新增RPC，CID到具体链上请求的归属仍交独立链证据核验。此限制不否认恢复的字节确实属于所请求的CID。

认证过程检查了实际请求根块存在、每块SHA256与CID一致、DAG-PB/UnixFS类型、文件大小及重建字节；文件SHA单独记录，未拿文件SHA冒充DAG根CID。未把CAR header声明的根当作内容来源证明。

## 官方依据

- 当前官方客户端 [`push_metadata_to_ipfs`](https://github.com/valory-xyz/mech-client/blob/main/mech_client/infrastructure/ipfs/metadata.py) 虽在本地创建 `metadata.json`，但上传的是该文件；[`IPFSClient.upload`](https://github.com/valory-xyz/mech-client/blob/main/mech_client/infrastructure/ipfs/client.py) 使用 `wrap_with_directory=False`，返回文件CID。本地文件名不构成CID下的路径。
- [UnixFS规范](https://specs.ipfs.tech/unixfs/)通过Data.Type区分普通目录、文件和分片目录；不能只凭dag-pb codec推断布局。
- [Trustless Gateway规范](https://specs.ipfs.tech/http-gateways/trustless-gateway/)规定根 `?format=car&dag-scope=entity` 对文件获取文件DAG，对目录获取列链接所需块。若根确为目录，只能沿认证的实际链接继续读取，不能猜文件名。
- 官方客户端还存在仅在本地计算CID而未向公共IPFS上传的路径；因此不能把所有404都解释成布局问题，也不能保证任意历史CID可恢复。

## 共用实现与兼容性

随后已获授权实现纯core共用CAR读取：`read_car_file` 的显式 `filename=None` 表示根File，提供filename时仍严格要求真实目录中的唯一同名链接；`inspect_car_root` 只检查实际根类型与链接。原 `verify_car_file` 接口和旧目录返回保持兼容。新平台函数 `collect_root_or_path_content` 先读取根CAR，根File本地派生JSON并记录 `layout=unixfs-root-file-v1`；根Directory仅在原预定filename真实存在时使用原路径，不猜其他文件。

新版调用、可信URL范围和RetainedEvidence对应重验分支由主流程接入；默认旧版采集与已发布报告不自动切换。一次必要离线验证已通过：两真实File逐字节提取且错误CID拒绝，旧2198 Directory的757字节文件与历史proof字典完全不变。平台新采集路径尚待主流程真实集成验收，此处不声称已取得新的完整评分对象。

只对确定的路径404做布局判别，不把网络故障、鉴权、付费或限流当成更换入口的许可；保留请求上限。当前两份输入缺市场ID，市场关联及有效结算须另行独立核验，不能由输入可恢复推导完整分。

## 原件与命令

研究目录：`runtime/input-layout-research-20261018T133653Z-b20ec01e/`。

- `plan.json`：发出请求前固定两对象、CID、原索引与404来源摘要、最大请求数。
- `manifest.json`：2次新GET；每对象仅1次，均BACKGROUND，使用SafeHttpClient、`http://127.0.0.1:7897`，无重试、无交付输出读取。
- `findings.json`、`analysis-manifest.json`：离线认证、真实字段及完整摘要。
- `recovered-input-2135.json` / `recovered-input-2267.json`：从认证根文件提取的原始字节。

实际命令，均退出码 **0**：

```powershell
./.venv/Scripts/python.exe -X utf8 runtime/input-layout-research-20261018T133653Z-b20ec01e/probe.py
./.venv/Scripts/python.exe -X utf8 runtime/input-layout-research-20261018T133653Z-b20ec01e/inspect_inputs.py
./.venv/Scripts/python.exe -X utf8 runtime/input-layout-research-20261018T133653Z-b20ec01e/verify_shared_reader.py
```

本子任务只在授权后新增上述共用读取能力；常读进度文档、冻结政策、历史采样与已发布报告未改动，没有新增模型调用或评分。初始研究读取仅2GET，后续共享规则验证为0网络。
