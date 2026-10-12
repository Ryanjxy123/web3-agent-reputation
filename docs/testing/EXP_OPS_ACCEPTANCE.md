# EXP-1 / OPS-1 修复验收

日期：2026-10-12。基线 main `60dec2cf3466d1d1e575490b6eca5efedbe6f80b`；任务分支 `fix/exp1-ops1`。只处理两项既有审计问题，不修改已发布 v0.1.0 资产、生产数据、评分定义或冻结实验原件。

## EXP-1

实际复现：复制正式 v2 至 `runtime/exp1/repro`，修改 `normal_write-0/trace.json` 的 evaluate_ms=-1 和 rpc_attempts=0，原 CLI exit 0 并写出错误统计。漏洞在离线读取/统计边界：源码清单自校验和 input/Bundle 哈希未覆盖 trace 的计时、状态及关键指标；既有 publication-manifest 未被使用。

修复复用既有 publication/source ZIP。默认固定已审阅正式清单摘要，其他数据必须提供独立保留的可信摘要，拒绝自洽重封清单绕过；全部原件先校验，同一份内存字节进入解析、源码及 Bundle 复核。增加时间/数值/计数/唯一任务及跨文档一致性验证，失败明确拒绝正式统计。analyse 仅向输入目录外新空目录输出。新 capture 封存源码/采集数据，执行计划一次读并匹配冻结摘要，不重写历史原件。

独立 Review 发现并已修复：校验后再次读取的竞态；阶段时间和/attempt 时间漏检；trace 与 Bundle 计划、观察、输入证据及版本缺少交叉绑定；新捕获执行计划与冻结计划可分离。最后 Review 无剩余可行动 P0/P1/P2 阻断，未扩大到其他缺陷。

历史核对：152/152 清单成员、82/82 exact 源码成员、36 个不同 run/slot/request 全部匹配；全部原始 rows、汇总指标和成本保持一致，CSV/SVG 内容一致，报告仅增加可信边界说明。Verifier 判定/原因 36/36，风险 33/33，旧 rule2/report1.1 的 3 个 N/A 继续排除风险比较。共享管道耗时总计 evaluate=119504.2302ms、verify=16788.2594ms、report=97047.7043ms、RPC=2433、HTTP=48；未重新开展无必要的 36 次正式采集。

定向测试通过：`pytest tests/unit/test_task11_integrity.py tests/unit/test_task11_comparison.py -q` 主运行 97 passed/0skip（691.52s），随后真实 runner 计划摘要不一致和超大整数边界各 1 passed，合计 99（92新增+7既有），均 exit0；只有既有 websockets 弃用警告。Ruff、Mypy70、新测试 Mypy、74 Schema、diff --check 通过。稳定版本新副本修改 normal_write-0 同样字段，CLI 使用独立新 `--analysis-output` 后明确 exit1，原因是 trace 发布哈希不一致，未创建任何统计输出。格式有效、冻结内容完整性和原始实验真实性分别说明；哈希不证明测量者诚实。

## OPS-1

按授权顺序，EXP-1 阶段提交后开始。当前尚未执行修复或验收。

## 整体回归及交付

最终完整 Python/PostgreSQL/Anvil/API/Worker/Web/Foundry/ABI 门禁和 GitHub required checks 待两项阶段验收后运行，未执行项不计通过。本机 Docker Linux engine 的已有限制由实际 Linux foundation-compose 验证，不以本地配置解析替代容器验收。
