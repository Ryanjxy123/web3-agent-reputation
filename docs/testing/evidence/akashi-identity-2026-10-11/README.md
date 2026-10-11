# 任务 9：真实 ERC-8004 注册与只读端点关联

这里是修复阶段 Review 问题后，单轮 `runtime/task9-live-20261011-2` 的真实材料。采集结束时间为 `2026-10-11T04:31:06.734Z`。`acceptance.json`、注册原文 `metadata.body`、`openapi.body`、20 份 CAS 意图/响应、10 份 DNS 原件和 `source-manifest.json` 均逐字节复制；`audit.json` 是该轮原件的离线审计结果。`publication-manifest.json` 列出这些原件的字节数与 SHA-256。旧 run1 留在本机 runtime，标记 `pre-review-NOT_FINAL`，没有混入最终验收材料。

注册身份：Base `8453`，Identity Registry `0x8004a169fb4a3325136eb29fa0ceb6d2e539a432`，agentId `98097`。固定块为 `52451849`，区块 hash 为 `0x6e8fc723ddaa8096f44749ab9a45a4bc1c117049866ae0f7f204c22d1bf18e6f`；Owner 为 `0xa88630300706488e9d31597ccc4394206f4d4c6c`。同一块下读取注册表 bytecode、官方 ABI 的 `ownerOf(uint256)` 和 `tokenURI(uint256)`，并在读取元数据前后重新检查该块 hash。URI 为 `https://anchor.akashi-notari.com/.well-known/agent-registration.json`。

共 10 次免费身份只读请求，全部 HTTP 200：chainId、genesis、选定区块、注册表 bytecode、Owner、tokenURI、一次区块复核、注册元数据、OpenAPI、第二次区块复核。没有请求 `/proof`、没有调用 MCP 工具，没有支付、签名或链上写入。

结果为注册身份 **PASS**、HTTP `/proof` 与 MCP `/mcp` 入口和注册声明的关联 **PASS**。HTTP 入口还核对了原始 OpenAPI 的固定服务 origin、所选 GET 参数和免费只读声明。关联结果证明所选固定入口与注册资料一致；executor 控制权和业务能力均为 **UNKNOWN**。本材料没有执行 EIP-712 控制权证明、能力实测、评分、正式测评 Evidence Bundle 或任务 10 完整闭环。

CAS 使用 Keccak 和字节数承诺；可保留的原始响应同时记录 SHA-256。`audit.json` 校验全部 CAS、原始响应 hash、规范 ABI 编码与 Owner/URI、官方 ABI 固定 hash、原元数据/OpenAPI承诺，并以这两份原文重新计算两个端点关联。注册表 bytecode 的 hash 是本次观察到的代理代码承诺，不宣称锁定了代理背后的完整实现。

本机系统 DNS 返回 fake-IP，因此这轮使用明确操作者配置的 Google DNS-over-TLS：固定 `8.8.8.8:853`、TLS 名称 `dns.google`、证书验证开启，只接受固定 `mainnet.base.org` 和 `anchor.akashi-notari.com`。`dns/` 保存每次 A/AAAA 查询与响应的原始 wire、TLS 审计和完整地址集合；与 CAS 中 SafeHttpClient 的解析地址逐项一致。所有地址继续接受公网检查和数字 IP socket pin，Host、TLS SNI、证书、限频与配额规则保持生效。没有声称 DNSSEC 已验证。操作者 resolver 保留在本机 runtime，没有改为默认平台配置。

正常 DNS 环境可在仓库根目录新建一次独立验收：

```powershell
uv run --all-packages python scripts/akashi_identity_smoke.py --allow-public-readonly --output runtime/akashi-identity-reproduction-new
```

命令拒绝覆盖旧目录；公开服务是否可达及注册信息是否变化，以新采集的记录为准。`source-manifest.json` 保存本轮关键实现文件的 SHA-256，并确认调用前后内容一致。读取或解析失败保留 UNKNOWN 与真实材料，不用历史缓存冒充新调用。
