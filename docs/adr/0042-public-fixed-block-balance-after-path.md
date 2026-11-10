# 0042：公开固定块 balance-after RPC 原件的窄路径准入

状态：2026-10-29，仅调整公共报告包的路径准入，不改变评分、报告、冻结计划或原始证据。

`scripts/public_reports.py` 的 `PRIVATE_NAME` 拒绝 `balance-before` 和 `balance-after` 名称。现有真实 CoW 取证把固定区块 `eth_call` 响应命名为 `balance-after-<digits>`；这些公开 RPC 原件是重放净资产结果所需输入，单纯按文件名拒绝会使合法报告包无法离线恢复。

例外仅适用于以下完整、规范路径，两处 UUID 均须为规范 UUIDv4，campaign 目录仍须通过既有公开路径与父目录检查：

```
runtime/<safe-campaign>/tasks/<canonicalUUID>/states/<canonicalUUID>/chain/balance-after-<digits>.observation.json
runtime/<safe-campaign>/tasks/<canonicalUUID>/states/<canonicalUUID>/chain/balance-after-<digits>.response.bin
```

规则不按提供方名称、域名或 Agent ID 分支。不放宽 `balance-before`、`REQUEST_INTENT`、非 `chain` 目录、其它文件名/扩展名或私有父目录；其余秘密名称、路径越界和私有材料拒绝规则保持。该例外不是任意钱包快照的公开许可，也不是内容脱敏或秘密检测的替代品。

路径准入只解决归档文件名冲突。原 manifest SHA、observation 与正文绑定、固定块 RPC 参数以及原报告完整离线重放仍须通过，不能仅因路径匹配就认定链状态正确或允许伪造、改名的材料。软件来源仍复制为不可变快照并核哈希，不执行快照，不覆盖既有包、报告或原件。

验证限一项离线路径组合：28个真实公开路径通过，22项错误 UUID、其它目录/后缀、before、REQUEST_INTENT 及私有父目录负控被拒绝。`python -m unittest discover -s tests -p test_public_balance_rpc_paths.py -v` 为1 test／0.002秒／exit 0，未重跑旧套件；实际报告包仍另经SHA核验和离线重放，此项不计为新增业务样本。
