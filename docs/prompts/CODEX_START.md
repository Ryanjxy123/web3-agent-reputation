# 首次交给Codex的执行提示词

复制下方内容；先把本包repo内容按非覆盖安装方式放在仓库根目录。已有规则文件冲突时先合并。

```text
你正在为一个区块链比赛实现 Web3 Agent 多源证据声誉评价平台。我是项目/仓库负责人。
本地目录：D:\大三上\软件前沿技术\web3-agent-reputation
预期远程：https://github.com/Ryanjxy123/web3-agent-reputation.git

本次不是再讨论方案，请按已落地的规划开始写实际代码。首轮范围严格限定 M0 + M1；通过后交接，不自行扩成多链、付费LLM、完整A2A/MCP或主网业务。

0. 先核对当前工作目录、现有AGENTS.md及上级有效指令、git status/branch/remote/log、已有代码。查看.bootstrap-incoming中的冲突文件，先合并规则与规划，保留已有代码、LICENSE和未提交改动。不能假定空仓库。
1. 按顺序完整阅读 AGENTS.md、PLAN.md、docs/implementation/STATUS.md、docs/implementation/BACKLOG.md、docs/architecture/ARCHITECTURE.md，再读本轮任务对应的docs/specs/*、docs/integrations/ERC8004.md、docs/runbooks/WINDOWS_AND_GIT.md。PLAN是本次执行契约，STATUS是跨会话交接状态。
2. 先完成M0-01审查记录，再逐卡执行。保持模块化单体：platform中的API和worker共用业务层；core无网络/DB；verifier不依赖平台API/数据库；前端Vue3/TS/Vite，PostgreSQL队列，Foundry/Anvil本地链。根据真实环境解析并锁定依赖，禁止假锁文件。
3. M1必须有：三个本地合约、真实正常/无关交易两个受控Agent、可信owner/executor绑定、持久幂等任务、独立RPC业务断言、脱敏证据报告、真实报告摘要上链、独立复核器。先做一条真实纵向链路，不先做排行榜或复杂首页。
4. 保留PASS/FAIL/UNKNOWN/NOT_APPLICABLE与原因码。写入超时/崩溃后先查任务状态和链上事件，不能盲重发。成功receipt不等于本次任务成功。M1小样本报告必须partial、综合分null，不得降低policy-v1的20/10/10门槛制造完整高分。
5. 本包已有scoring_reference和36项离线测试，它只是参考基线，不是完整平台。先跑check_bootstrap，再逐步加入真实单元/数据库/合约/安全/E2E测试。独立复核必须从证据重做断言/统计/评分；JCS/Keccak和锚定receipt分离按spec实现。未知不能变0，报告篡改不能扣给Agent。
6. 上游ERC-8004/8004scan只作身份/候选入口，按官方资料锁ABI/commit/OpenAPI。取不到就记BLOCKED，保持公网默认关闭；不虚构公开Agent或拿外部站内分数当自研真值。公网接入不阻塞本地M1。
7. Git先核对remote等价性与远程历史。已有main不直接开发；建立/复用feat/foundation-m0-m1。远程有历史先正确接入，不创建无关历史；仅确认远程为空才按runbook做bootstrap例外。每个逻辑单元测试后做可解释小提交，审查secrets与暂存范围。不得reset --hard、clean -fd、强推、自动stash、改全局Git身份或覆盖用户改动。
8. 完成并验证的工作，在remote匹配且认证可用时正常push当前工作分支；不要push已有main、合并自己的PR或替我更改分支保护。认证/工具缺失时如实记录，不说已同步；继续不依赖它的本地任务。保留当前审批与沙箱安全设置，不要求绕过所有限制。
9. 每完成一张任务卡更新STATUS/PLAN进度，附实际命令、通过/失败/未运行、产物路径、commit与阻塞。禁止TODO空壳、写死结果、伪造测试输出、删除失败案例或擅自改阈值过测。确需偏离规格时写ADR说明影响与理由。
10. 会话结束按：已完成task_id与文件、实测命令及结果、尚未完成/阻塞、当前分支与commit、push是否成功、下一任务和命令，交接。若资源/环境不足，留下可继续的真实状态，不把未测部分标完成。

现在从M0-01开始，在实际仓库按顺序执行，直到本轮M0/M1完成或出现明确的环境阻塞。
```
