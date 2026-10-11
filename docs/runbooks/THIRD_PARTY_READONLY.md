# 正式 Akashi 免费只读适配器（任务 8）

默认 API/Worker 保持受控协议；任务 8 完成安全出口、静态 HTTP/MCP 适配和可注册证据，不冒充任务 9 身份关联或任务 10 正式评价闭环。没有业务评分、写入任务或 executor VERIFIED。

## 命令与边界

```powershell
. ./scripts/tools.ps1
uv run --all-packages python scripts/akashi_readonly_adapter.py --allow-public-readonly --output runtime/akashi-formal-readonly-new
```

输出目录必须尚不存在，避免覆盖前一轮结果。一次命令最多 8 次实际网络尝试：HTTP 两次固定真实历史 tx、一次随机 hash、一次固定非法输入；MCP 初始化、通知、发现、find_proof 各一次。每次至少隔 1 秒，零自动重试；402/付款要求立即停止。无支付凭据、签名、主网写入、RPC 或任意 URL 参数。

`acceptance.json` 包含查询、现有 Observation、规范化响应和 EvidenceRecord。`blobs` 保存每次发送前的 CAS 意图和接收后审计。先校验每个 blob 的 byte_count/Keccak，再对保留的原 body 重算 SHA256；HTTP 200/accepted 不等于业务 PASS。未知 hash 的有限搜索结果不能证明全链不存在；400 只表示非法输入被拒绝，正式业务负例归因由后续规则执行。

在应用事务内用 `result.registered(connection, store)` 注册已有 PostgreSQL evidence_blobs，并使用返回的新 Observation，避免重复内容对应的证据 ID 漂移；Worker 可把这段包入既有 queue.fenced。尚未建立正式快照/授权/plan 前，不从现有 controlled API 自动调用该适配器。

## DNS 环境

必须有真实公网 DNS 答案，全部答案通过公网校验才连接。本机代理 fake-IP `198.18.0.85` 被拒绝，不能为此关闭策略、TLS 或改代理。操作者可以在进程内给 `accept(output, resolver=trusted_resolver)` 注入可信解析器；仍使用同一 SafeHttpClient pin/SNI/SSRF 检查。

本轮真实验收使用固定 Google DNS-over-TLS（8.8.8.8:853、dns.google、现有 certifi CA），运行时助手及 DNS 原始 wire/TLS 指纹在 `runtime/task8_dot_dns.py` 和 `runtime/task8-trusted-dns-20261011`。用于绕开本机 fake-IP 解析方式，未绕过公网 IP 检查，不声称 DNSSEC。默认命令在 fake-IP 环境会明确失败；应先恢复可信系统 DNS，或审核操作者的 resolver 注入。

## 验收记录

本轮第一次系统 DNS 运行退出 1，5 次意图均因 PUBLIC_IP_REQUIRED 拒绝，未得到第三方响应。第二次可信 DNS 运行 HTTP/MCP 正例规范化一致，但非法输入前发生一次 ConnectError，退出 1，未自动重试，失败证据保留。第三次完整运行退出 0：HTTP 200/200/200/400，MCP 200/202/200/200；共 8 次尝试，正例/重复/MCP 归一一致，无 402、付款或主网写入。

最后一次在最终源代码上重验的run4同样退出0、8次请求全部符合上述状态，公开材料来自run4。完整原材料位于 `runtime/task8-live-20261011-{1,2,3,4}`；公开脱敏的成功运行与原始 body hash 见 `docs/testing/evidence/akashi-formal-2026-10-11`。整轮29次意图、23份实际响应，5次IP拒绝/1次ConnectError全部保留，无自动重试、付款或402。

这些是任务 8 真实协议证据，不能当作新链上核验、ERC-8004 身份验证或正式计分结果；任务 7 的历史链核验没有被本次调用替代。301项定向验证及稳定代码d8297bb的完整Foundation CI（Python985/0skip、Web2、Foundry14/256fuzz、Schema/TS/ABI/Ruff/Mypy）通过，当前代码重放4份真实历史A/D Bundle全部PASS。
