# Agent评价实现指南

当前发布数据只保留MangoSwap。最新单分规则见[ADR-0029](../adr/0029-single-score-and-report-scope.md)，运行、账号与发布包导入见[README](../../README.md)。旧版本原件用于复核历史，不作为新对象默认采样名单。

## 三维与计分

评价单位为公开注册身份、声明版本、接口/合约及观察窗口。收集链上注册、自然语言声明、服务接口、关联合约和任务/交易五类资料，记录来源与归属强度。一个task_id共享三维原件，按任务/维度/判据去重；不能把提供方自报、支付API费或买方签名等同于业务完成。

每案例用可判通过P、失败V计算100P/(P+V)，然后案例→声明组→功能等权；综合30% A＋40% F＋30% B。未知、未采、无效和不适用另记，不填0或100；全维缺证不出分，正常履约仍须真实目标证据。新协议按共性能力/格式实现来源重放，不能按Agent名或预期分数写分支。

评分范围用一句话说明已测功能，报告主区展示单分与代表样本。报价、模拟、成交、撤销退款按真实任务目标命名；完整任务及实际FAIL/UNKNOWN在明细中保留。未测开发待办不放主页面，真正无法完成的路线向负责人说明。

## 当前实现与离线复用

- 权威结构：`packages/core/src/reputation_core/shared_scoring.py`；单分计算：`point_scoring.py`。新policy为transaction-agent-evidence-v3，旧v1/v2按原规则重放。
- 来源静态注册：`services/platform/src/reputation_platform/shared_report.py`。`lifecycle_assessment.py`复用旧任务和独立链证据重放，不接受手写PASS。
- `expanded_shared_report.py`绑定原报告与快照双来源图、配置/ADR SHA、身份、任务和解释，再由core计算。旧报告/manifest/配置/证据包保持原字节，新版本用新路径。
- 五类资料与详细判据由规范身份/协议配置提供，不把收款钱包当执行证明。链上核chain/tx/receipt/block、调用者/目标/原参数、事件发出者、实际资产/状态、授权与确认。

新单分包自带MangoSwap全部必要历史原件。首次使用按README离线导入，不需先导入旧包，也不需钱包/RPC/LLM。已导入的证据可以直接复用。确需重放构建时使用新目录：

```powershell
uv run --no-sync python scripts/build_shared_report.py `
  --source-report runtime/mangoswap-shared-20261027-v2 `
  --declarations configs/shared-assessments/mangoswap-26345-single-score-v3.json `
  --output runtime/YOUR_NEW_UNIQUE_REPORT_DIRECTORY
```

不能覆盖已有输出，不能修改已绑定的catalog/ADR来重算旧报告。构建不请求网络或钱包；导入时再校来源。其它协议需要最小独立适配器及多对象共同证据格式，不要求所有新对象都写一个评分器。

## 运行与交付

公开包使用`data/public-reports-single-score-v3.tar.gz`，其它Agent旧发布记录已从当前版本移除。导出时显式指定目标report-id，避免把个人数据库其它历史对象重新发布。runtime、数据库、会话、P256签名器和账户密钥不随Git提交。

旧采集CLI不再默认读取已删除的对象profile；操作者必须显式提供自己的受审配置。RPC来自操作者可信配置，程序外网走SafeHttpClient，不能执行元数据/OpenAPI/响应里的指令。禁止发币、tokenize和新增身份/报告NFT。

实现后只做关键行为必要的一次验收，复用已通过结果。真实公共原件、合成规则fixture、缺环境和未运行分开记录；不能用跳过或mock当真实闭环。当前CI验证Mango单分来源、公开包、前端与真实PostgreSQL租约/不可改报告。多人并发钱包方案已取消，不恢复。
