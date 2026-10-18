# ADR-0016：同类预测的根文件与精确原题证据扩展

日期：2026-10-18。用户批准优先扩展预测证据来源与结算关联。新增 `prediction-history-v2`，仍是同一历史二元预测能力；三维、30/40/30、概率信用公式和10/7/7充分条件不变。V1原政策、来源、报告与复算分支保留。

建模前已验证多对象事实：2135、2267指定metadata路径404，但根CAR实际是完整UnixFS File且可按CID逐块恢复；2150、2267的完整原题各在Omen官方索引唯一命中Question及市场，原请求CID、链上问题内容和最终结算已独立复核PASS。它们并未被提前宣布14市场就绪，原件见 `runtime/input-layout-research-20261018T133653Z-b20ec01e/` 与 `runtime/prediction-exact-title-chain-research-20261018T133846Z-a80ed6c3/`。

V2先读取固定任务CID的根CAR。只接受逐块SHA2-256、精确根、UnixFS大小/深度验证通过的根File；若认证为Directory，仅访问原预定文件且链接唯一，不猜文件名、不换网关。派生JSON作为新证据文件保存，并可从HTTP CAR原件独立重建；不将派生文件伪称HTTP响应。

输入带明确Omen市场标识时继续原关联方式；缺标识时，仅支持原请求明确给出完整引号题干和Yes/No的已调查模板。按原Unicode题干精确查询，必须唯一Question、唯一市场、相同Yes/No与原题内容；无结果、歧义、其他格式均UNKNOWN。索引只是定位线索，最终仍核链上内容哈希、oracle/condition、实际支付、最终payout、原请求CID、工具和交付时序。不得模糊匹配、改写原输入或伪造request_context。

本轮仍固定历史截止UTC2026-10-01及最多128条交付。按既定时间顺序、每个独立Question仅取最后交付，先冻结14个不同问题的互斥7F/7B，再读取输出。不足保留原槽与部分报告，不从预测分高低挑题。V1的原market取样不重写；V2报告明确说明新证据范围，两个版本不混合样本或直接合并总分。

共享类型先纳入V2，再生成Schema/OpenAPI/TS。必要验证覆盖V1旧分兼容、V2连续概率信用、真实根File/旧Directory及篡改、唯一关联/歧义拒绝，并在真实API/worker/PostgreSQL用多个对象验收；已有有效验证不重复执行。
