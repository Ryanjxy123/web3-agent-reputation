# ADR 0009：冻结部分报告与证据包

日期：2026-10-03。范围：M1-06；发布与独立 ZIP verifier 由 M1-07 实现。

## 统计边界

纯 build_report 从冻结计划、保存的 RecordVerificationInput、实际观测重新执行断言；不接受前端分数，也不读取数据库或当前时间。M1 只有一个 anchor_record 正向功能槽位，功能计数由 PASS/FAIL/UNKNOWN 推导；不同时充当可用性或行为样本。尚无独立声明映射正确性观测，人工 review 不等于 mapping=1，因此 mapping=null。

复用原 scoring_reference 与 policy-v1，min20/10/10、覆盖80%、充分度60%不变。报告 PARTIAL、overall=null；D 的确定关键冲突仍产生 NOT_RECOMMENDED，不被其他维度未知隐藏。报告记录未测范围和映射限制，不提供伪造完整分数。

## 冻结与并发

verify 保存结果时原子排入 report 作业。worker 读取并校验 CAS 输入、重做断言，与保存结果比较；冻结前独立重读交易/回执/区块并比较每条规则的结论及 TaskLink。RPC 不可读时报告作业保留平台错误并可重试，不改 Agent 断言；canonical 或业务结论变化时拒绝冻结，要求新评价，旧字节不修改。

同时读取受信本地 EvaluationAnchor 在固定块的 head，固定 previous/sequence、发布者、合约、链实例和平台实例。网络、文件读取和 CAS 准备均在事务外；最终短事务通过租约 fencing 与按发布者/Agent/链/合约的 advisory lock 串行化。相同 run 返回已有报告；前一报告尚未成为链上 head 时，不为该 Agent 静默冻结竞争 previous 的新报告。外部发布者越过平台锁造成链头变化时，后续 publisher 必须拒绝过时 previous，不能改旧 report_core。

报告提交后、作业确认前崩溃可重新领取并返回原 revision。数据表继续 append-only，无数据库迁移。报告代码版本取实际 Git SHA（有工作树改动则加 -dirty），无 Git 的部署须显式配置实际 CODE_VERSION。

## 承诺图与稳定导出

新增 EvidenceManifest、ManifestDocument、PublicationContext、ReportView 共享类型并生成 Schema/OpenAPI/TS。每份业务文档与固定 Schema 都以脱敏后的 JCS 字节进入 CAS。manifest 按 evidence_id 排序；文档别名按 path 排序，指向同一 CAS 字节，避免两个不同的内容摘要来源。断言按 assertion_id，观测按 observation_id 排序。

`blob bytes → manifest → report_core → reportHash` 没有循环。manifest 直接承诺公共发布上下文；拒绝把 report_core、manifest 或 anchor_receipt 加入自身证据清单。FORMAT.md 只是格式说明，不参与业务判断。anchor_receipt 独立，未发布时明确 NOT_REQUESTED；receipt 改变不会改变 reportHash。

导出只读取冻结 manifest 指定的 CAS 文件并校验长度/Keccak；不能从当前 Schema 文件重建旧报告。ZIP 固定成员顺序、时间戳、权限和压缩方式，同一未改变 receipt 的报告重复导出字节相同。导出上限64MiB；不导出受限 signed transaction outbox、私钥或 RPC URL。

## 验证与限制

真实 PostgreSQL + Anvil + HTTP A/D 生成报告，逐文件核对承诺，纯规则重新生成同一个 core，检查重复 ZIP 字节、JCS 字段顺序、20/10/10 门槛、零跨目的复用及密钥缺失；并发作业只能冻结一个 revision，损坏/缺失 CAS 导出失败。恢复测试区分报告事务提交和作业确认。

离线材料内部一致性仍不能证明采集者诚实；报告导出不是独立 verifier 通过。M1-07 必须从安全 ZIP 读取、重新检查所有引用并重做断言/统计/评分，再用自身可信配置核对真实锚定。
