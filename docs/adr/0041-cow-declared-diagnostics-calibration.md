# 0041：CoW 已声明诊断语义的回顾测量校准

状态：2026-10-29。仅对显式选择新测量契约的来源校准离线证据解释；不修改交易协议、操作者、安全约束或评分政策。

原测量把正常 build 后的原生 validate 一律要求为 `valid:true/errors:[]/warnings:[]`，并把所有隔离异常一律要求为 `valid:false`。这比既有声明更强：短有效期可以在阶段间经过真实时间后触发保护；归因字段的检查也可以按声明返回警告。冻结任务决定观察什么，不能自行证明提供方承诺了某种错误等级。

现存官方原件给出明确边界：

- `runtime/candidate-expansion-goal-20261028-direct/phase7/ophis-tools-list.response.bin`，SHA256 `a0759d32392b7105957d9f30bcb27564a68d09d3a2e491e8ef0ca76a1313726e`。`/result/tools/2/inputSchema/properties/validForSeconds` 声明 build 最低 60 秒；`/result/tools/12/description` 声明检查问题并返回 `valid/errors/warnings/expected`，未承诺 appCode 不匹配必须使 `valid:false`。
- `runtime/protocol-cow-review-20261029/phase3/ophis-api-source.response.bin`，SHA256 `dce38174c52e98e05b6eff4ae71bffdf9be86520e865f3c91cf15c994cbdf8c3`。既有官方 `apps/mcp-server/src/ophis.ts` 缓存第265–268行将错误 appCode 加入 warnings；第469–472行将验证时剩余不足60秒加入 errors；第524行以 `errors.length === 0` 决定 valid。对应 observation 保存官方 URL、HTTP200、完整正文及相同 SHA。

C16 请求声明允许的60秒生命周期，到 validate 时剩54秒；原生工具按上述 guard 拒绝。此保护退出不能仅因阶段间耗时算功能失败：对应正常验证判据保留 UNKNOWN，原有效字段核验独立保留，不能补正常 B。C24 的 appCode 与相应 appData 哈希一致变更后，原件 `valid:true/errors:[]` 且明确警告错误原值和修正方法，符合已声明的警告诊断；它不能被描述为未检查，也不能因冻结标题使用“rejection”而强行要求 fatal 拒绝。

来源可新增可选 `measurement_contract={path,sha256}`，引用 manifest 内独立公开的确定性测量契约，并核对其原字节 SHA 及官方声明依据。它明确是既有原件的回顾解释校准，不冒充任务发送前的前瞻规则。未提供该引用的旧来源、旧冻结计划、fixture 和已发布报告继续原 legacy 重放；不得静默套用新规则、覆盖原报告或改写原 HTTP/RPC、原计划 SHA。新来源及新报告追加保存，并带上契约与本 ADR 的确切引用。

契约按声明的字段诊断等级和保护条件核验原请求、独立预期及原响应，不按服务名、域名或 Agent ID 分支。警告诊断的 PASS 需要明确对应字段/非法原值和声明语义；任意警告、泛化错误或缺源仍不能补 PASS。时间保护只有在原件确实支持已声明 guard 时才归 UNKNOWN，不将一般服务错误隐藏为保护。

fatal 的 domain、哈希、owner、chain、fee、receiver 不匹配仍须保持其独立约束和应有的拒绝判据；不得借 warnings 接受错误收款、错误签名域、额外权限或错误资产。诊断校准不改变三维30/40/30、case身份/成员、required_decisive、正常 B 门槛、64块确认、净资产归属、原 UID 及授权清零条件；不生成新任务、不重发旧请求、不将本地重放当真实实验。
