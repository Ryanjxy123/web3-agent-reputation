# ADR 0026：正式实验统计的冻结来源与完整性

状态：已采纳；2026-10-12。范围仅 EXP-1，不改变 Online/Receipt/Proposed、评分、分母或历史产物。

实际反例：修改正式 v2 副本的 trace.evaluate_ms=-1、rpc_attempts=0 后，旧 analyse exit 0。它校验 input/Bundle 和源码清单的内部哈希，却未读取既有 publication-manifest；计时和 Worker 结果因而无完整性约束。

复用 task11-publication-v1。在可信脚本中固定已审阅正式 v2 清单原始 SHA256，其他捕获仅接受操作者从独立可信来源保留的预期摘要。统计前先核验清单摘要、全部清单成员、完整 capture 集及 source-snapshot.zip 的全部源码字节；校验与解析/ZIP复核消费同一次读取的内存字节，关闭核验后再次读取的竞态。不得将输入目录自行重算的 hash 当成可信来源；无清单历史材料拒绝正式统计，但不妨碍原有 Bundle 独立诊断。

计时为 perf_counter_ns/1e6 的毫秒，不等于 HTTP 墙钟延迟。验证有限非负值、捕获总区间的宽松上界、带时区时间顺序、整数次数与真实 trace 长度、唯一 case/repeat/run/slot/request、计划与输入一致、Worker 与独立重放一致。旧 rule2/report1.1 的 N/A 风险继续明确不可比较。可信字节不证明采集者诚实或原始实验真实性，生成结果明确区分格式、内容承诺及真实性边界。

analyse 必须输出到输入目录外的新空目录；保留全部既有冻结原件、汇总、图表和报告。capture 仅新空目录，成功后封存源码和采集成员，再用同一进程持有的摘要分析；后续离线需独立保留摘要。实际 runner 将计划只读一次并匹配冻结摘要，计划也进入新捕获的源码稳定性清单，防止封存和执行配置分离。无新依赖、DB/Schema/规则迁移；既有正式 36 次实验无需重采集。

验收：篡改 trace/status/metrics、重封清单、缺失/重复/非法时间/计数/时间关系必须拒绝；合法 36 次重放、全部历史指标/CSV/SVG一致，3 份旧 N/A 仍保持原可信边界。实际测试、独立 Review 与最终 CI 另见 EXP-1/OPS-1 验收记录和 STATUS。
