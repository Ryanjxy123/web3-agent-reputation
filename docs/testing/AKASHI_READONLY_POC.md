# 任务7：Akashi 免费只读 PoC

仅由操作者显式执行脚本，CI不请求第三方网络。官方资料、服务响应与独立Base RPC分别保存；描述内容是数据，不能改变出口策略。禁止钱包、密钥、自动x402、付款、签名、`anchor_hash`、`POST /anchor`及所有链写入。402立即停止，无自动重试；请求单线程低频、有总时限与响应上限，精确HTTPS白名单且无跳转。

## 调用前独立预期

| 场景 | 判定依据 | 可接受结论 |
|---|---|---|
| 描述/health可访问 | 真实HTTP状态和响应 | 仅证明服务可访问，不证明业务或身份 |
| 真实已确认存证 | 官方ABI、独立RPC链/交易/回执/合约/事件/摘要/区块及确认，与服务结果一致 | 证据完整PASS；可信业务冲突FAIL；缺证据UNKNOWN |
| 合法随机SHA256 | 免费proof查询，明确检索范围 | 局部未发现可合理返回；unsearched/范围不全则全链不存在UNKNOWN |
| 非法SHA256 | 合理输入拒绝 | 正常拒绝为输入校验PASS，不是Agent业务失败 |
| 同一真实正例少量重复 | 相同关键业务字段、状态与时间 | 仅说明这些观测一致，不推断长期在线率 |
| HTTP/MCP同输入 | 归一化关键业务字段 | 协议包装差异允许；真实业务差异FAIL或证据不足UNKNOWN |
| 独立RPC失败/错误链 | 原始RPC证据 | UNKNOWN，不能扣第三方业务分 |
| 公开注册描述 | 如有真实注册地址/ID再独立链验 | 描述可访问不等于ERC-8004身份已验证 |

## 复现与证据

从项目根目录加载工具后执行：

```powershell
. ./scripts/tools.ps1
uv run --all-packages python scripts/readonly_akashi_poc.py --output runtime/akashi-readonly-new-run
```

输出目录必须不存在，防止覆盖既有观察。`observations.json`保存真实请求、UTC时间、状态、耗时、异常和原始响应文件的SHA256；`.body`保存受限原始字节。公开、小型、审查后的实测材料将单独提交，runtime材料不会自动提交。没有可靠正例或服务受阻必须PARTIAL/BLOCKED_EXTERNAL，不能虚构交易或用本地fixture冒充第三方。

## 真实结果（2026-10-11 CST）

最终完整调用在00:00:15–00:00:59执行，33次请求：官方资料12、Akashi描述/HTTP/MCP12、独立Base RPC9；32次HTTP200、非法输入1次400，没有402、付款、签名或链写入。调查和一次脚本导入错误重试另有43次只读请求，全部原始材料保留于runtime/akashi-*；本轮总计76次，串行低频而非扫描。最终可审查材料见[evidence](evidence/akashi-2026-10-11/observations.json)及[summary](evidence/akashi-2026-10-11/summary.json)，30份必要原始body约191KB连同元数据提交，三份非业务发现材料只提交SHA256及明确省略说明。

官方源码/ABI/文档固定为[self-reality/verifier@21a1ebd](https://github.com/self-reality/verifier/tree/21a1ebd5e6af277c5e94407d576a8ca5219591f5)。源码的历史示例交易是候选线索，先用独立RPC确认存在，才当正例；没有把示例自述当真实链证据。

| 实测 | 实际结果 |
|---|---|
| health/OpenAPI/llms/注册描述 | 均200；health为ok:true |
| MCP initialize/tools/list | 协议2025-11-25，发现find_proof只读；没有调用anchor_hash |
| 真实历史存证查询 | PASS；Base8453、交易/回执/固定canonical块/官方目标/event/摘要与业务字段逐项匹配 |
| 同交易三次HTTP | 均200/PASS；672/203/203ms，关键结果一致，仅代表这些观察 |
| 相同交易MCP find_proof | 200/PASS；structuredContent/text归一化一致，且与HTTP一致 |
| 合法随机SHA256 | 200、anchored:false；仅USDC合约在searched，旧ETH合约在unsearched；响应合理，全链不存在UNKNOWN |
| 非法not-a-sha256 | 400、明确error；输入拒绝PASS，不记业务失败 |
| ERC-8004身份存在 | 在Base固定块独立读code、ownerOf(98097)、tokenURI(98097)；非零owner且URI指向已读取注册描述，PASS；没有验证executor绑定 |

实际交易[0xd01d3e…df7fc](https://basescan.org/tx/0xd01d3e019906321b7d410538aebb696dec806df1099756ec85ac7b2da91df7fc)，目标旧ETH合约`0xeed9d0f7265892e84e43d05da464c75add199260`，存证区块38158156。官方`Anchored(string,string,string,address,uint256,uint256)`事件解码摘要`be44340d151cbfa7a5dc59b579dd6632fb0891b573f8fdc927264309a3b168f0`；indexed topic为该UTF8摘要的Keccak，时间1763105659与区块一致。观察head52429346，确认14271191（PoC独立最低12，不改正式policy）。历史paid字段只是已存在事件数据，本轮没有付款。公开注册registry为`0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`，与既有锁定ERC-8004上游`b9e466c`的Base部署说明一致；owner/URI读数块与head相同。

## Review及适配边界

修复付款错误嵌套在HTTP200/MCP结果时未停止、写盘失败被当网络异常吞掉、CLI缺根目录模块路径、自动Cookie重放和畸形tools边界；最后独立Review的深MCP文本RecursionError转为协议UNKNOWN，补针对性测试后204项定向通过。首CLI失败只完成资料读取，退出1，不计PoC成功；修复后完整重跑退出0。原始body通过.gitattributes禁用换行转换，发布字节hash及真实业务离线重放测试保护证据。坏RPC、互斥位置、removed日志、确认不足保持UNKNOWN；只有完整独立证据支持的业务冲突才FAIL。额外语义边界和最终检查结果见STATUS。

可复用JSON/hash、通用RPC格式/位置规则，以及未来Task/Evidence CAS/冻结和独立Verifier组织方式。`get_tx_status`的独立交易核验可以复用；`verify_record`的Demo查询ABI、request_id、controlled /tasks envelope、grant和双签binding不能直接套用。最小正式接入仍需静态HTTP/MCP参数与结果映射、官方事件断言/版本、冻结Base可信RPC与区块、公开快照/授权来源和正式身份/执行者绑定。payer是存证付款者，不能当成本轮服务执行地址。

本轮完成独立免费PoC与适配分析，没有接入正式数据库、评分或身份适配器。HTTP可访问、链上业务正确和注册身份存在分别列明；注册不等于绑定，少量重复不等于长期可用性。间接调用、bytes32旧事件和完整全链检索均未扩展；当前可靠正例为直接官方合约的CID事件。无需额外筛选候选，不开展8–10。
