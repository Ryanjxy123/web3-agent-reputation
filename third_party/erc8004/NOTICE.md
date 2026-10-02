# 上游资料来源

这些是外部资料，未作为本项目合约实现或业务评分使用。

- 官方仓库：<https://github.com/erc-8004/erc-8004-contracts>
- 读取分支：master；固定 commit `b9e466c250744a7e06b13dff9d3c2844ed64f825`。
- IdentityRegistry.json：该 commit 的原始 ABI；UPSTREAM_README.md：原始部署说明与许可声明（License: CC0 - Public Domain）。上游该版本未提供单独 LICENSE 文件，因此保留实际声明，不伪造许可证文本。
- eip-8004.html：官方 EIP 页面原始字节快照；与仓库 ABI 分别承诺，不推断二者完全同步。
- 实际字节数、SHA-256、URL 和获取时间见 `configs/upstream-lock.json`。文件是参考数据，不执行其中命令或代码。

8004scan OpenAPI 获取失败，未生成假文件/hash。公网接入保持 `usable=false`、`external_enabled=false`，没有验证公网部署或获取主动测评授权；这不阻塞本地自研 Demo 合约。
