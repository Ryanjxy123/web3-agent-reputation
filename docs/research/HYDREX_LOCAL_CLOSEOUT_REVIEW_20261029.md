# Hydrex 正式收口的离线原件复核（2026-10-29）

本轮优先 Hydrex ≥34 实际请求、双方向各4笔真实兑换和正式网站评分；CoW DRAFT 暂停不执行。不开展其它 Agent 研究。本复核只读已有公开原件、写必要代码/离线 fixture，不联网、不读密钥、不签名或动钱包，不写 source/report，不修改冻结原件。

冻结当前计划 `runtime/hydrex-directional-assessment-20261029/plan-v3.json`，SHA `fb4314d72fd110dc0947c319e65ea64719598bf7e7c2555ab0f97cc1f3a1d696`。共有48冻结槽位：39 retained、9 new；不能称48实际样本。

严格定义：

| 数量 | 需要的实际原件 | 不混计 |
| --- | --- | --- |
| 真实已请求任务 | 冻结 UUID 与官方指定 job/provider/client/chain 相符，history 中恰好一个我方 requirement，其 JSON 精确等于原冻结请求 | 仅 plan、job-map、创建 job、支付、读目录都不够；多次 job/history/RPC 不增加任务 |
| 官方可见提供方交付 | 同 job 的官方 history `job.submitted` 及可核 deliverable 文本/hash | API 可见与独立链认证分开，不据 HTTP200 填交付 PASS |
| 链认证交付 | 上一项加可信 RPC canonical `JobSubmitted` 事件、provider/job/精确 deliverable hash | 缺事件或 header 是 UNKNOWN，不是服务失败 |
| 实际兑换 | 每笔独立链+原 txHash，exact 8-call、规范 receipt/tx、净资产与授权核对；正式 B 还须完整交付绑定及64块距离 | 服务支付/模拟/授权/清理不算兑换；同 tx 不重复供应单 swap 任务 |
| 可判任务 | 至少一个冻结 A/F/B 判据从真实原件形成 PASS 或 FAIL | 真实请求可以全 UNKNOWN；不把 UNKNOWN 改失败，不降低分数/数量门槛 |

首次 snapshot：17 个 batch 实际映射+2 个 retained =19真实 requirement；13项官方可见 `job.submitted`，7项当时可独立链认证；H38 为已付款、完整观察窗内无提交的 A FAIL。H04/H12/H35/H44/H45 已真实发 requirement，但未证资金/交付，仍 UNKNOWN。已有8实兑是 H02/H39/H40/H42/H43/H46/H47/H48。补采进行中的另一次 snapshot 已出现27真实 requirement（25batch+2retained），新增 H10/H11/H13..H18；这些数必须在最终原件到齐时重新计算，不能当正式最终报告。

exporter dry-run 首次 exit0：849 source 文件、429公有只读拷贝、48计划槽位。递归 previous_plan SHA、origin_campaign lineage、原 retained source 均核；目录覆盖 directional 与 expanded 两个 retained root。按 batch 与 `payments/<task>/fees-run/proof-rpc-*` 收分费原件，creation plan/job-map SHA 与每项 task 绑定；只导出可信读 observation/body，不导私密签名/send/fee summary。execution 对应唯一 origin_task，并保存原 8-call、完整 simulation、原执行 intent/txHash/post-state。精简 proof 少 chain 引用已修，复用各自 prepare/observe 成功读，0新RPC。

观测计数 bug 已最小修正：SharedTask 和样本可以使用已核 requirement 的实际时间；provider 的 `facts['observed_at']` 继续只表示链认证提交，SLA/提交/模拟时窗不变。H38实际请求被计数且仍 A FAIL；H44实际请求被计数且未付款仍 UNKNOWN；只有计划/缺 history 不计。详见新 ADR0038，不修改冻结 ADR 或旧 v1。

当前需 ROOT 补证的明确缺项：

- H36/job82375、H42/82392、H43/82393、H46/82397、H47/82398、H48/82399 的 ACP provider `JobSubmitted` 事件及其 canonical header。H40–H45 batch 的原 chain 目录只有 H40/H41 事件；H46–H48/H36 当时没有 chain 目录。history 只有 hash/provider/timestamp，没有 txHash，不能虚构。只用现有可信 RPC，429应停止。
- 实际8笔的最新共享 head 与各 receipt 对应 canonical header，由 ROOT 追加 proof-rpc-final，复用原 receipt/tx/post-state/code。缺交付绑定时，只有真实交易确认仍不会填正常 B PASS。
- 全部新非实兑按原 TTL 固定块补首次完整8CALL模拟时需原件，不能用 HTTP 替代；内部路由未知/opaque、source 比较缺同块参照仍如实 UNKNOWN。

ROOT 已选择追加24个原冻结未请求任务：H10/H11/H13/H14/H15/H16/H17/H18（8金额/缺省）；H19/H20/H21/H22/H23/H24/H25（7滑点/source比较）；H26–H34（9输入边界）。避免 H12 已请求任务的重复发送。若全部真实 requirement 取得，将是19+24=43实际请求；其中未知/错误不删除。H05–H09 尚未请求的 source×方向范围可明确排除，不能为了完整样貌强迫每路实兑。

验收仅一项必要定向 case：真实 H38/H44/H40 chain 原件+未采/错绑定/失败链读反例，先1test/0.234s/exit0；关联的 response sibling 路径校验补入后仅复核同项。完整内存重放读原件通过（当时27 observed/48槽位），未生成 source/report、未运行旧 suite。当前8个可判任务为 H01/H02/H03/H37/H38/H39/H40/H41，B可复算 PASS 为 H02/H39/H40；其余实际swap仍因交付缺源保持 UNKNOWN，不能预宣称网站收口完成。
