# 任务 8 正式适配器的真实只读响应

来自最终 `runtime/task8-live-20261011-4` 的原始 acceptance.json 和全部 16 份 CAS 意图/响应，逐字节复制；DNS 子目录为同一轮 8 次请求的可信解析原始 wire/TLS 审计。`operator_dns.py` 是本机 fake-IP 环境使用的明确操作者 DNS-over-TLS resolver；只接受固定 Akashi 主机与固定 8.8.8.8:853，验证 dns.google TLS，未集成默认平台出口。

结果：8 次免费只读尝试，HTTP200/200/200/400，MCP200/202/200/200，HTTP重复正例与MCP规范化一致。原 body 由 CAS Keccak/长度和 SHA256 双重保存，Cookie/认证/session 未进入公开材料；没有支付、签名或链写入。

这里仅证明真实调用和协议/证据能力，不宣称新身份验证、executor 控制权、独立链上业务复核、综合分或任务 10 闭环。运行失败记录留在本机 runtime 并在 STATUS/runbook 单列，没有删除失败、用缓存替代新调用或把离线重放称作 live。

正常 DNS 可执行 THIRD_PARTY_READONLY 的命令。本机 fake-IP 复现命令（在仓库根目录）：

```powershell
uv run --all-packages python -c "import asyncio,importlib.util; from pathlib import Path; from scripts.akashi_readonly_adapter import accept; spec=importlib.util.spec_from_file_location('operator_dns','docs/testing/evidence/akashi-formal-2026-10-11/operator_dns.py'); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); asyncio.run(accept(Path('runtime/akashi-formal-reproduction-new'),resolver=module.resolve))"
```

使用操作者 resolver 不改变 SafeHttpClient 的公网 IP、pin、Host/SNI、TLS、限频或配额检查。新的调用结果以实际记录为准，不保证第三方始终可达。
