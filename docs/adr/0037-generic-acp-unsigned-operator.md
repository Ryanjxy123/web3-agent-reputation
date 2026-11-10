# 0037：ACP 原始请求字段映射与通用 unsigned 操作者

状态：DRAFT，2026-10-29。扩展独立 unsigned v2 的冻结输入映射；v1、core、共享 v3 单分、30/40/30、64 块与正常 B 目标不变。不按对象名、注册 ID 或品牌选择评分分支。

`plan.request_mapping` 仅提供 canonical→native 字段名、native→canonical source 值、声明中的缺省滑点/上限及 route offering 范围。字段必须存在于认证 offering schema，默认值、上限和 source 值须与该声明一致。投影的是临时副本，原 requirement、schema、HTTP/history 原字节、提交哈希和冻结 UUID 不变；错误匹配同时识别 native 字段名。每个 task 使用其最早冻结版本的映射和声明，追加版本不能漂移旧任务。无 mapping 完整沿原路径。未适配辅助 offering 保持 UNKNOWN，不把缺 route/amount 当成交易失败。

首个接入草案仅使用已有完整公开 ACP 目录及真实 provider event 绑定的身份。另一未补 provider event 的目录项不冻结。30 原槽位包含 20 正常报价、4 无效报价与6辅助筛选；正常 B 双向各四仍为目标。辅助六槽位无独立 checker 时不进入正常 A/F case 分母，不能把目录、计划、schema 投影、本地差分或一次模拟算成实际采样/成交。此前 job82343 的 EOA 收款与 UUID 仅作身份/资格背景，不冒充未来 SMA 任务。

操作者从认证 native delivery 与冻结 `normalized_expected`/输出指针构造同一八 CALL：输入/输出余额、精确 approve、原始 unsigned route、approve(0)、输入/输出余额及剩余 allowance。仍复用现有协议解码、模拟、canonical receipt、ERC20净事件与前后余额核验，不新增对象评分器或 Hydrex wrapper 假定。真实交易只由 root 在专用显式阶段签发；本实现交付不运行任何 phase、网络或钱包动作。

RPC 只经既有 SafeHttpClient transport；read phase 无 send、无 overrides、固定同块代码及状态绑定。prepare 默认要求明确 REVIEWED 的部署资料；缺 runtime/来源或未审入口即停止。Kyber opaque 可按精确 payload 或经 root 审核的固定 runtime+明确 entry 范围绑定，前提为外层精确输入/本人净 minimum、不存在任意 owner call 的源码依据。仍核 payload 哈希及实际 selector；pool/path/AMM fee 细节不因该授权变 PASS。空 DRAFT profile 不提供任何放行。

ACP job/API/费用老脚本文件不改。新进程 wrapper 替换旧单 offering 的绑定函数，逐项核同一认证 metadata 的 provider、offering name/id、requirements、费用/SLA、原 task UUID 和 request。campaign_source 始终是原冻结 lineage，不生成伪冻结 view。API/费用与单任务分批付款客户端继续复用，任务创建、费用、cleanup均不补 swap B。

签名/发送 intent 在发送前持久化；已有签名/发送状态只 reconcile，不盲重发。私有 raw send 放私有目录，公开 source 只收明确 ACP GET/read RPC 原件及 pair；软件复制到 artifact 的按真实 SHA 命名不可执行 provenance。初次 campaign 可从明确 task-items 组装 v2 source，不要求借用其它对象的 retained source。旧原件、旧 ADR 和已发布报告不改。

兼容性回归：现有 single campaign case 增加真实 native/schema 投影、default/cap/source/required 校验、原对象不变、辅助 UNKNOWN、旧 task 映射版本 pin；仅该项运行一次通过（1项、3.014秒、exit0）。私有操作者仅静态及必要纯离线解析检查；网络、钱包、签名和真正端到端执行 NOT_RUN。
