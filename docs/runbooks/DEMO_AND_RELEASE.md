# 开发运行、演示与发布目标

当前包已提供 M0+M1 的可运行契约；M2 评分扩展仍不在本轮范围。命令必须使用真实 API、worker、PostgreSQL 和 Anvil，失败退出码不能伪装成功。

## 1. 环境初始化与完整新成员路线
M0生成.env.example（仅变量名、假值、明确本地chain限制），setup创建未提交的随机token/runtime配置，安装锁定依赖；doctor检测Docker/Compose/Foundry/Python/Node以及端口冲突。
目标顺序：setup → compose启动postgres/anvil → migrate → deploy-local → seed → api/worker/fixture/web → doctor → demo。
必须等待服务健康，不靠固定sleep假设部署完成；migrate失败不启动业务worker。Windows可使用 `scripts/dev.ps1` 包装同一Python CLI，不能有两套业务逻辑。
API/worker的默认服务运行入口可为 `uv run reputation api`、`uv run reputation worker`；命令由M0在pyproject注册并在README写实测用法。

## 2. 部署与seed幂等
部署配置保存chain_id/genesis/block/deployment_instance_id/contract_address/ABIhash/代码版本；复用前重新校验bytecode/实例，而不只看本地文件存在。
检测Anvil重置时停止使用旧地址，提示显式deploy/reseed；不把旧报告删除或说链上记录仍有效。
seed重复不会重复注册或业务写入；固定fixture标识与ledger状态有映射。随机任务输入不是所有run共享一个固定request。
seed不读取业务真实材料、不使用主网、不向公网发布Anvil默认私钥。

## 3. 最小演示
A与D都声明可存证。展示相同业务类型、不同随机request/input→A真实业务事件吻合→D receipt成功但request/摘要不符→查看逐项断言→导出报告→真实anchor→独立验证→修改副本后拒绝。
首轮样本少，显示“部分评价，不生成综合分”是正确结果，不是演示失败。完整20/10/10与三能力评分在M2 full suite展示。

## 3.1 发布与独立复核

在 `smoke_reports.py` 生成两份未发布 bundle 后运行 `smoke_m1.py`。脚本将 A 报告排入 `anchor_jobs`，worker 先持久化 nonce 和 signed transaction，再广播 `EvaluationAnchor.anchorReport`；随后用 `reputation-verify` 做离线重算、可信 RPC 在线复核，并验证修改 bundle 会失败。

独立复核命令：

```powershell
uv run --all-packages reputation-verify runtime/local-chain/report-a.zip
uv run --all-packages reputation-verify runtime/local-chain/report-a.zip --rpc-url http://127.0.0.1:8545
```

第一条命令只证明 bundle 内部一致性，anchor 为 `NOT_CHECKED`；第二条命令只使用操作者提供的 RPC，成功时报告 `CONFIRMED`。Verifier 不读取 ZIP 内的 RPC 地址。
A/D是受控测试代理，不声称已有商业Agent；8004scan公开注册样本另页展示，回放单独标记。

## 4. 完整演示与实验
A–H，写入画像和只读画像分开；展示低可用性、夸大能力、任务不匹配、新对象unknown、地址待验证、版本更新、合法只读NA。
至少一次golden算例作为单元测试，而非现场硬编码分数。真实实验由fixture行为生成数据；结果差异保留原因。
UI/API指标仅在实际测试环境测量，注明硬件/负载/数据量；不能把PRD“P95目标<1s”改写为“实测<1s”。

## 5. 备份与复現
备份PostgreSQL、evidence blobs、fixture ledger、受信部署配置；密钥另用受控安全方式，不放公开包。
报告包本身足以离线重算，但不能重建整个运行环境或证明链下真实调用；复現整个实验还需固定代码、容器/依赖锁、规则、数据集和运行配置。
本地链可重置；公开复核需受信外部链与最终性假设。恢复后先doctor核对instance，不能沿用旧chain状态。

## 6. 发布
clean主分支commit通过ACCEPTANCE后才tag；生成版本、变更、许可、完整性清单与已知问题。
竞赛提交目录与Git开发仓库分开，生成匿名副本时排除.git、用户路径、学校/队员/导师信息、remoteURL和屏幕账号，保留必要第三方许可来源；匿名细则以负责人重新核对官方要求为准。
不改写Git历史来匿名，不删除运行失败记录，不把规划当实际测试报告。
