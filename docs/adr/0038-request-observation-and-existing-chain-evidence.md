# 0038：真实请求观察时间与已有执行链原件引用

状态：2026-10-29，新 Hydrex v2 报告发布前校正。旧 v1 source/report、已冻结计划和 ADR 原件不变；共享 v3 评分规则、30/40/30、SLA、B 门槛、八调用及执行判据均不改。

问题一：`unsigned_swap_campaign._delivery` 的 `observed_at` 是已认证提供方提交时间；没有交付时应保持空。它同时被拿来决定 SharedTask 是否实际采样，会使真实已请求但超时或未付款的任务在网站少计。H38 有真实 requirement、资金及完整无交付观察窗，A 可判 FAIL；H44 有真实 requirement 但未证资金就绪，A 必须 UNKNOWN。两者都属于实际请求，均不应与只有冻结计划的槽位混淆。

决定：仅 SharedTask/样本的采证时间通过 `_task_observed_at` 选择。已认证提交优先；否则可以使用 `_delivery` 已核官方 history、准确链/job、client、provider 和冻结 requirement JSON 后保存的 `requirement_submitted_at`。已有真实执行仍按其时间扩展。缺原始 history、缺任务绑定或只有计划时没有观察时间。此字段不回写 `facts['observed_at']`，也不改变 provider 提交、SLA、模拟有效窗或归因；未付款请求继续 UNKNOWN。

问题二：精简执行 proof 只采新增 receipt/tx/header/post-state/code/head，exporter 原来未把同执行 prepare/observe 中已有的成功 `eth_chainId` 读引用到 execution，导致报表因缺源停止。不能把计划 chainId 或客户端常量填成 RPC 结果，也不需要重发业务或重复读取。

决定：exporter 仅复用该 execution 自己 prepare/observe 的成功可信 RPC 原件，校验 status/body/hash/JSONRPC id、精确 method/params 与实际链值。失败、429、无 body、错误链均不能补这个槽位；原失败保留。先检查 response 文件为公开同目录 `.response.bin` 再读，不接受私密路径。receipt、post-state、规范区块和确认条件沿用原算法；真正缺源是平台补证问题，不能称 Agent FAIL。软件和本 ADR 进入新 artifact 输入，旧发布原件不覆盖。

核验：一个必要离线真实 H38/H44/H40 chain fixture 验收，包含已付款超时、未付款 UNKNOWN、只有计划/缺 history/错 UUID、错误链、429 和不安全路径负控；实际完整内存重放也只读现有原件，不写 source/report。工程测试不计新的业务任务。官方交付原文、链上认证交付和实际兑换分别计数，不能把 48 冻结槽位当实际请求。
