# 预测历史方案的真实复用记录

日期：2026-10-18。政策 `prediction-history-v1`，原始规则先冻结于 ADR-0008；首个增仓报告保留特例。这里记录同一实现的两个真实对象，不代表已支持任意提供方或实时付费推理。

## 共同规则与各自证据

两对象均为 Gnosis 注册，实际 agentId/serviceId/Mech 与服务执行者分开核验。各自在 UTC 2026-10-01 之前机械选取14个不同的已结算市场，7个功能、另外7个行为，两个已看pilot市场排除。先存资格与计划再读输出；结算固定到区块48815687。

| 对象 | 正式历史原件 | 自动选案 | 登记补证 |
| --- | --- | --- | --- |
| 2198 | `runtime/prediction-history-20261018T072135Z-26548298`，418新读取，exit0 | `runtime/plan-selection-20261018T073341Z-f7430c1b`，SELECTED/exit0 | `runtime/olas-identity-supplement-20261018T072835Z-81d7a2c6` |
| 2235 | `runtime/prediction-history-20261018T072524Z-fc00242b`，432新读取，exit0 | `runtime/plan-selection-20261018T073342Z-dbc66d5f`，SELECTED/exit0 | `runtime/olas-identity-supplement-20261018T072903Z-9384bed1` |

同一collect、纯链核验、评分、报告与worker处理两对象；只改冻结profile和真实资料来源。root从原RPC请求/响应、CAR块与链上CID重新计算，不接受bundle自报PASS。缺少当前登记日期不能算行为完整；mint与同笔ServiceAgentLinked及区块时间均独立核实。

初始2198选案误要求引用完整描述，因真实模型使用合法原文片段而NEEDS_INFO。修正为对应工具描述中的预测业务原文引用，仍须来源、语义和schema同时成立；不是放宽评分或更换样本。仅重做该失败的离线选案，旧评分政策未改。

## 真实报告与访问采样

从实际API分别提交2198和2235，均HTTP202：

- 2198任务：`9f2e3c7a-468e-4665-97fe-977b156f0817`。
- 2235任务：`18fdbaf8-49e6-475e-bc91-0bad4cecc2ed`。
- 提交原件：`runtime/prediction-platform-check-20261018T074030Z-58260bb4`。

两个相同worker进程各用`--once --enable-public-readonly --proxy http://127.0.0.1:7897`处理一个任务；新采各10次历史交付文件、30秒间隔，随后离线重验和发布。其租约和fencing与既有平台共用，没有付费推理或链上写入。最终状态以API/数据库与下方完成记录为准，采集READY不是完整评分。

新采样前，离线真实原件已算出2198功能75.66（4方向通过、3偏离）、行为100；2235功能97.81（7方向通过）、行为100。此时可用性尚无样本，两个总体均PARTIAL、无综合分，没有提前计数。

## 中文与必要验证

两对象28题去重后仍28题，4次DeepSeek翻译请求共10596tokens，exit0；模型不接收预测概率、结算方向或分数。平台复核修订4处语义，原材料和缓存不改；`runtime/question-translation-reviewed-20261018T074043Z-b002326d`可信加载28题、4编辑/24原文，exit0。一次验收脚本误将两对象总题数断言14，纠正为真实28后只复核该失败步骤，无模型重发。

纯概率、自动选案各1个必要用例exit0；CAR六个拒绝控制、历史执行五个失败控制exit0。报告新增1个真实pilot单元验证exit0：重算概率与结算，拒绝伪造结果和RPC副本，拒绝私有文件；pilot仍排除正式样本。旧测试不重跑。新增区块交易顺序绑定由这两次真实worker预处理验证，未发新HTTP。

旧2182串行任务因优先级调整人为中止，268观测保留，无正式计划/bundle/评分；新排序实验只影响UNKNOWN背景的同时间位置，两个既定14样本及顺序均不变，生产保留原确定性排序，未在看输出后换组。

## 接下来

先完成这两份报告，再做跨提供方的大量真实功能声明收集、能力聚类和可测覆盖/价值分析。评价单位是功能，一个Agent可适用多类；覆盖分析前不启动第三类。第一类特例与当前同模板复用边界见`docs/architecture/GENERALIZABILITY_REVIEW.md`。

## 最终发布结果

| 对象 | 可用性 | 功能 | 行为 | 综合 | 真实报告 |
| --- | ---: | ---: | ---: | ---: | --- |
| 2198 | 98.20（10PASS、p95 1812ms） | 75.66 | 100 | 89.72 | `runtime/evaluation-report-20261018T074802Z-2378ca3d` |
| 2235 | 98.61（10PASS、p95 1625ms） | 97.81 | 100 | 98.71 | `runtime/evaluation-report-20261018T074803Z-c4f9fbe0` |

两个worker均exit0，真实API任务均COMPLETE，报告GET200，报告号分别为`6fb09167-0bce-4142-9b52-4b89dd13fdc1`和`079a5a34-edf2-4699-a17f-509609092427`。新A原件为`runtime/prediction-availability-20261018T074307Z-12650b51`和`runtime/prediction-availability-20261018T074307Z-397a3952`。目录实际33候选、3个不同完整评分对象、4份报告；下载1份本报告所属原件与文件逐字节一致。一次验收摘要误读latest_report.status而非latest_report.scores.status，改为真实结构后离线核对exit0，成功HTTP下载未重发。所有原件在提交记录目录，浏览器视觉验收仍BLOCKED，没有以HTTP替代截图。
