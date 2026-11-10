# ADR-0036：缺省deadline的请求时间窗测量校准

状态：独立测量版本request-interval-v1；transaction-agent-evidence-v3、A/F/B权重30/40/30、覆盖目标及正常B门禁不变。ADR0032及旧source/plan/report原字节保留。

## 真实问题与决定

原v1将响应provider timestamp误当deadline创建时刻，要求两个整数秒时间相差精确默认TTL。真实A21的默认600秒请求返回execute deadline1793209693，响应timestamp17:38:14.039Z（整数秒1793209094），差599秒。请求观测17:38:09.482452Z、elapsed3750ms；deadline和最终响应字段可能在这段处理窗的不同时间生成，且calldata只有整数秒。该事实不足以判服务违背600秒缺省约定。

仅新计划顶层明确`deadline_default_clock_policy=request-interval-v1`启用校准。无marker的旧source/plan继续原v1精确差值算法，保存旧报告可按原结论复算。新plan-v5只追加测量metadata并引用v4 SHA，tasks、cases、原始请求及原件不改变；它是已有38任务的回顾性测量校准，不是新增样本或事后改变业务参数。

## 确定性判据

delta = decoded execute deadline - floor(provider timestamp秒)。默认值D与实际请求耗时E毫秒来自冻结声明及原始观测：

- delta==D：PASS。
- delta在[D-ceil(E/1000)-1,D+1]内但非精确：UNKNOWN，时间生成点和整数秒精度不能排除正常缺省值。
- delta超出该可观测窗：FAIL，说明公开时间/参数与缺省值不一致；不臆断内部根因。
- 缺provider时间或实测耗时，且非精确值无法定位：UNKNOWN。

窗口的量纲来自本次请求持续时间和一秒整数精度，不是SLA、不设固定网络延迟扣分阈值，不用主机当前时间或新请求重测。A21窗口[595,601]、599秒为UNKNOWN，不改成PASS。默认slippage检查保持；A38真实typed HTTP500校验失败保持；任何资金、授权、路由、确认规则不变。

## 来源、兼容及验收

新校准来源hash固定本ADR，记录旧source/report/manifest摘要及新plan的测量marker。新report使用新的runtime目录及软件文本快照；不覆盖旧报告、原计划、原HTTP/RPC或PG历史。追加计划沿首次任务冻结时钟验证原件，不能用新metadata冻结时间否定合法旧请求。

一项定向验收保留真实A21输入/响应/耗时，覆盖599秒UNKNOWN、精确600秒PASS、明显错误TTL FAIL、缺时间UNKNOWN、v1仍FAIL及旧已发布v1原件的完整离线重放。只改变已识别的测量错误，不调权重或数量门槛，不为得到绿色结果给不确定样本补通过。
