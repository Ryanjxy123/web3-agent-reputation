# ADR 0004：M1 自研演示合约

状态：采用；2026-10-02。

三个合约严格区分身份声明、业务记录和评价承诺。DemoAgentRegistry 是自定义本地协议，不实现 ERC-721/8004；部署 instance 非零，URI 长度 1–4096 bytes；修改递增 revision，转让清除旧 executor 声明，声明本身不是可信签名绑定。

DemoRecordRegistry 按实际 msg.sender/requestId 去重；重复请求无论摘要相同与否都 revert。HTTP 幂等由 Agent 账本提供。合约没有外部调用、资产或代理。

EvaluationAnchor 使用显式最小角色实现：不可变部署 admin 只管理 evaluator allowlist，不自动成为发布者；链头与历史按 evaluator/agentKey 隔离。重复同报告返回原 sequence 且不发重复事件；任何历史字段冲突拒绝，新报告必须引用当前 head。管理权限可撤销 evaluator；管理员不能修改已发布记录。

选择显式角色而非引入完整角色继承依赖，因为当前仅两类权限、没有委托角色图或升级需求。无第三方合约代码复制。后续若需要管理权迁移，需新 ADR/合约版本，不能静默改变该信任边界。

ABI 由 Solc 0.8.30/Foundry 1.8.4 编译产物导出并校验漂移；既有 ProtocolVersion 探针没有业务引用，已用真实合约测试替换。Foundry 测试覆盖事件全部字段、权限、零字段、去重、所有权失效、前向链及发布者隔离；256 次模糊输入验证业务记录不可覆写。
