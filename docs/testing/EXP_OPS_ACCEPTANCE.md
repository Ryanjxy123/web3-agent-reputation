# EXP-1 / OPS-1 修复验收

日期：2026-10-12。基线 main `60dec2cf3466d1d1e575490b6eca5efedbe6f80b`；任务分支 `fix/exp1-ops1`。只处理两项既有审计问题，不修改已发布 v0.1.0 资产、生产数据、评分定义或冻结实验原件。

## EXP-1

实际复现：复制正式 v2 至 `runtime/exp1/repro`，修改 `normal_write-0/trace.json` 的 evaluate_ms=-1 和 rpc_attempts=0，原 CLI exit 0 并写出错误统计。漏洞在离线读取/统计边界：源码清单自校验和 input/Bundle 哈希未覆盖 trace 的计时、状态及关键指标；既有 publication-manifest 未被使用。

修复复用既有 publication/source ZIP。默认固定已审阅正式清单摘要，其他数据必须提供独立保留的可信摘要，拒绝自洽重封清单绕过；全部原件先校验，同一份内存字节进入解析、源码及 Bundle 复核。增加时间/数值/计数/唯一任务及跨文档一致性验证，失败明确拒绝正式统计。analyse 仅向输入目录外新空目录输出。新 capture 封存源码/采集数据，执行计划一次读并匹配冻结摘要，不重写历史原件。

独立 Review 发现并已修复：校验后再次读取的竞态；阶段时间和/attempt 时间漏检；trace 与 Bundle 计划、观察、输入证据及版本缺少交叉绑定；新捕获执行计划与冻结计划可分离。最后 Review 无剩余可行动 P0/P1/P2 阻断，未扩大到其他缺陷。

历史核对：152/152 清单成员、82/82 exact 源码成员、36 个不同 run/slot/request 全部匹配；全部原始 rows、汇总指标和成本保持一致，CSV/SVG 内容一致，报告仅增加可信边界说明。Verifier 判定/原因 36/36，风险 33/33，旧 rule2/report1.1 的 3 个 N/A 继续排除风险比较。共享管道耗时总计 evaluate=119504.2302ms、verify=16788.2594ms、report=97047.7043ms、RPC=2433、HTTP=48；未重新开展无必要的 36 次正式采集。

定向测试通过：`pytest tests/unit/test_task11_integrity.py tests/unit/test_task11_comparison.py -q` 主运行 97 passed/0skip（691.52s），随后真实 runner 计划摘要不一致和超大整数边界各 1 passed，合计 99（92新增+7既有），均 exit0；只有既有 websockets 弃用警告。Ruff、Mypy70、新测试 Mypy、74 Schema、diff --check 通过。稳定版本新副本修改 normal_write-0 同样字段，CLI 使用独立新 `--analysis-output` 后明确 exit1，原因是 trace 发布哈希不一致，未创建任何统计输出。格式有效、冻结内容完整性和原始实验真实性分别说明；哈希不证明测量者诚实。

## OPS-1

按授权顺序，EXP-1 阶段提交 `93fdb88` 后开始。实际复现命令为 `uv run --env-file .env --all-packages pytest -q -s docs/audit/reproductions/test_security_counterexamples.py -k quota_exhaustion_persists_in_real_worker`，exit0，反例成立：真实 PostgreSQL/API/Worker 同一服务的 8 次健康刷新，前 6 次成功，第 7/8 次没有快照，累计 HTTP=64，旧身份成为 UNVERIFIED。

根因是 64 次尝试本属有限采集会话预算，缓存 Reader 却将其延续至 Worker 整个生命周期；既有业务没有日/小时重置窗口。每个获准、尚未开始的新 ingest 创建独立客户端并 finally 关闭，完成后下一次独立刷新自动获得新预算。已开始的不确定作业与已保存结果继续不重发、不重复快照。现有 pending 去重、权限、租约、fencing、付款停止、失败计数、64 次上限及 DNS/TLS/白名单均保留。使用已有 PostgreSQL origin 锁和审计在 socket 前核对状态及持久预算，跨新会话/Worker 重建和公共评价共享至少 1 秒节流。配额耗尽通过既有 JobView.reason_code 明示 REQUEST_QUOTA_EXCEEDED，与身份 UNKNOWN 平台归因和用户 grant 配额分开。

独立 Review 实际发现并修复两项中断边界：取消锁获取后，SQLAlchemy close 归还连接池但未释放 PostgreSQL session advisory lock；完成审计数据库失败后，过早 start 审计可使下一次请求绕过完成后间隔。旧实现分别真实失败，新实现等待后台 SQL 完成并关闭异常 session、保护整个退出清理，在完成审计未成立时持锁等待完整间隔且继续传播原数据库异常。最终独立 Review 无剩余可行动 P0/P1/P2 阻断。

新增真实 PostgreSQL/API/Worker 集成 12 项：恢复文件 8 passed/0skip（最终 32.65s），节流文件 4 passed/0skip（18.06s），均 exit0。覆盖 8 个客户端/8 次健康刷新/80 请求与持久计数、会话预耗后 5 请求耗尽及下一新作业 10 请求恢复、双 API 并发单 pending、开始前 SQL 失败零请求、保存前后重领不重发、取消/失租关闭、服务重建节流、公共 verify RPC 共用锁、锁取消及完成审计失败。数据库/API/Worker 是真实实现，HTTP 使用离线 MockTransport，不声称这 12 项是公网测评。初轮相关既有测试 156 passed/1 failed；原故障注入按“第 2 次 fenced”定位被新增 socket 前审计提前命中，已改为 10 个响应完成后的真实中断边界，原 10 请求/UNKNOWN/不重发断言保持，身份文件 10 passed 重验通过。

扩大的身份/公共评价/HTTP/Registry 回归初轮为 167 passed/1 failed（255.91s）：公共 Bundle 测试曾查询全部 public.egress，却只与 fixture 清空后的评价请求比对，新增初始化身份审计造成 66 对 56。修正为当前 run 的 56 条原断言，并独立要求初始化身份 10 条；独立复核确认没有降低评价/配额/节流标准。修正后完整定向 168 passed/0skip（243.26s）、exit0，涵盖真实 PostgreSQL/Anvil/API/Worker 公共评价/报告/Bundle 路径；Ruff、Mypy70、74 Schema 和 diff 检查通过。

## 整体回归及交付

跨模块独立 Review 已完成：评分/充分度/报告/执行/复核与 SEC-1/2/3 边界保持；Verifier 仅扩参数类型以接受同一份内存 ZIP，历史语义未升级。43 份历史 Bundle（4×1.0、5×1.1、33×1.5、1×1.6）全部离线 PASS，Path/BytesIO 两入口结果完全一致，原 SHA256 不变；旧 1.0 仍为 NOT_AVAILABLE_LEGACY_REPORT、Anchor NOT_CHECKED。独立 Verifier/公共 Bundle/HTTP/读取隔离单元回归 234 passed/0skip（64.61s），exit0。

稳定阶段提交 `bb0c0e69a675ee75eca6ddb73f426a0de6bf9201` 在独立测试端口 30611/30612 上运行 `uv run --env-file .env --all-packages python runtime/exp-ops/run-full-check.py`，包装器只保存日志/源码摘要并调用原 `scripts/check.py`。FAIL_ON_SKIP=1，2026-10-12T13:33:40Z–14:52:52Z，exit0/PASS（4752.406s），前后 `source_changed=[]`。完整 Python 1701 passed/0skip（4678.51s），比基线1597增加104项（EXP92+OPS12）；Ruff、Mypy70、74 Schema、生成TS无漂移、Web类型/构建、21单元/5 Vite集成/11浏览器组、Foundry14/0failed/0skip/256fuzz、ABI3全部通过。两条既有上游弃用警告未隐藏。完整日志与摘要保存在忽略的 runtime/exp-ops，未提交配置、数据库或个人环境数据。这次本地全量先于下述 SVG 跨平台修复，不代表修复后的最终源码已在本地全量重验。

首轮 PR head `c698151da66021af2725329a8be1a761fa29e495` 的 Linux CI run `38266398865`：foundation-compose SUCCESS；foundation-quality FAILURE，Python 1700 passed/1 failed（1562.20s）。唯一失败是 `test_outputs_are_consistent_and_cannot_overwrite_a_frozen_result`：Linux 默认 LF 与冻结 SVG 的 CRLF 相差一个字节。只在 SVG writer 显式指定 `newline="\r\n"`，不改冻结原件、测试或严格字节断言。独立进程模拟 Linux 默认 LF：旧 writer FAIL，新 writer 通过原断言，SVG/CSV 字节与冻结结果一致，JSON 语义一致；原失败测试单独重验 1 passed（10.28s），Ruff/diff 检查通过。最终源码全量回归须由包含该修复的新 head Linux CI 验证，旧 head 的 Compose 成功不代替新 head 门禁。

SVG 修复后的完整 EXP 定向重验：`uv run --env-file .env --all-packages pytest -q tests/unit/test_task11_integrity.py tests/unit/test_task11_comparison.py`，exit0，99 passed/0skip（763.89s），既有 websockets 弃用警告保留。两位独立收尾 Review 均确认该一行修复、严格断言及门禁记录无新增可行动阻断；未重复本地78分钟全量，最终新源码由新head完整 Linux CI验收。

PR #16：<https://github.com/Ryanjxy123/web3-agent-reputation/pull/16>。最新 head 的 foundation-quality/foundation-compose 和 mergeCommit 以该 PR 的权威终态为准；必须两项 CI 成功、无冲突且无 required reviewer approval 阻塞后才正常合并。最终 CI/合并由此门禁决定，不能将已结束的旧 head 或本地结果替代最新 head CI。本机 Docker Linux engine 不可用，只由实际 Linux foundation-compose 验证容器闭环，不把本地配置解析描述为 Compose 通过。合并后核对 main/origin/main 和受测源码、工作区及本任务分支清理，最终身份与核对结果保存于忽略的 `runtime/exp-ops/final-delivery.json`，不为记录自身合并 SHA 再提交文档，不改历史 Release。范围内无已知可行动 P0/P1 阻断；最终比赛交付验收由后续授权任务执行，本轮不扩展。
