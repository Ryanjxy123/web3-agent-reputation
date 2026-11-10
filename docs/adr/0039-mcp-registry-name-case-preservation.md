# 0039：MCP 官方登记名称保留 ASCII 大小写

状态：2026-10-29，最小解析校正。官方 MCP Registry 的具体版本原件包含 `io.github.TSavo/swapchan@0.3.0`；原 lower-only 名称正则错误拒绝此有效公开名称。

MCP reference 名称的 namespace 和 server 两部分字符类增加 `A-Z`，解析结果精确保留原大小写，不 casefold、不 lowercase，不按服务名称分支。前缀、分隔符、版本及其余字符规则不变。此为支持官方标识的语法修正，不改变 eip155、8004scan、ACP UUID 规则、共享类型或评分。

身份核验仍要求 reference、官方 GET URL、具体 name/version 和 remote 精确一致。大小写不同的字符串是不同标识；仅解析可接受不表示它已登记。错误 case 即使本地重算 proof/response 哈希，也不能冒充原官方 metadata。public_registry_verified 与未证明的链注册继续分开，无 A/F/B 改分。

验收为一个可移植离线组合：真实官方版本 observation/body/既有失败 proof 原字节；正确名称恢复核验，错误 case、重哈希后的 metadata/URL case 篡改、错误 remote、非 ASCII 混淆与格式负控被拒。旧 eip155/ACP 规范化结果不变。仅修改 parser、新 test/fixture 和本 ADR；不修改已冻结 ADR0034、任何 Ophis pinned operator/protocol/report/plan、金融或 RPC 配置，不新增网络/钱包/密钥/PG操作。
