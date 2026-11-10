# 0040：CoW campaign 前瞻追加与原冻结时钟继承

状态：2026-10-29，新增显式 `previous_plan={path,sha256}` 证据链。旧无 previous_plan 的 CoW 来源与 fixture 保持兼容；评分标准、v3权重、正常 B 门槛和所有旧任务不变。

真实触发：旧 C02 订单因本机预检耗时导致提交时剩余有效期不足，在原生 submit 前停止。旧任务、原 UID、签名状态和22个功能任务原件必须保留；新尝试只能由操作者前瞻冻结新 UUID/新订单，不能重发旧 UID 或把旧失败重命名。

每个 predecessor 必须是 manifest 内精确 SHA 的公开冻结计划，链无循环、冻结时间不倒退。旧 task 字典及其顺序逐项相同；只允许追加 prospective task，旧 UUID/id不重复。身份、服务、owner、链、评分、声明快照、协议、appData、operator、响应映射、时钟容差与范围保持。case身份、规则、required_decisive不变，成员保留原前缀，只可追加本次新任务。

任务首次出现的 plan path/SHA/frozen_at 从完整 lineage 继承。C01仍沿原 retained pilot intent 的回顾时钟。assembler 根据每项实际 TASK_INTENT 精确选择包含相同任务字典的 lineage版本，检查其plan SHA、原请求、身份及created_at；HTTP不得早于该实际版本冻结。旧 C03–C08可以继续原v1执行，新C31不能伪装成v1任务。报表评分仍沿首次冻结时钟，导出收全部 previous plans 原字节；无缺源补PASS。

只改通用离线报表/原件收集和装配器，不改 operator、signer、protocol、已pin代码或旧冻结输入，不生成正式 plan/source/report。一个必要离线组合以真实v1及旧HTTP原件验证受控追加C31、时钟继承、旧请求/previous SHA/政策/门槛篡改拒绝；受控新节点只在临时目录，不算实验或真实任务。
