# 声明分析、历史证据与评价报告运行记录

日期：2026-10-18。工作目录：`D:/xjtu_project/block_chain_new/block_chain_new_new`。

本轮将有出处的模型声明接入固定评价方案，再采集真实公共证据。模型不直接给分；历史采集完成也不等于业务核验通过。规则见 [ADR-0003](../adr/0003-source-backed-model-analysis.md) 与 [ADR-0004](../adr/0004-liquidity-history-policy.md)。原件、输入 manifest、观测和产物保存在本项目 `runtime`，新运行写入新目录，不覆盖旧结果。

## 授权、凭证和网络范围

用户已授权使用现有 DeepSeek 余额，不设额外请求数或金额上限；余额不足时告知，不自动充值。此前预算提议不再控制执行。该授权不包括付费 Agent、签名、主网写入或资产操作。

DeepSeek 凭证只从本机既有文件进入固定 `/responses`、`/user/balance` 端点的请求头。模型没有工具、网络或代码执行权限。公开资料中的文字不能修改平台指令，也不能配置任意 RPC。

所有应用网络通过 `SafeHttpClient`，真实执行显式传代理 `http://127.0.0.1:7897`。默认 CLI 只展示计划；公共读取需 `--execute-public-readonly`，模型请求需 `--execute`。固定白名单、请求与响应界限、超时和停止条件继续生效；不自动重试或换节点。401/402/403/429 停止该主机。节点、代理、未适配或证据缺口不会直接扣 Agent 分。

ZAN 使用固定 Base/BSC 主网地址。先检查固定地址、POST 和只读 JSON-RPC 方法，再加载本机凭证；发送时再次验证，拒绝批准后修改 method。已有 Base 完整密钥 URL 可提取同一项目凭证用于固定 BSC 端点。密钥只在实际 HTTP 传输 URL 的最后一段出现，不发送 ZAN Bearer；PublicTarget、manifest 和观测均保留无密钥地址。异常只保留类型，响应回显秘密时脱敏并标记不完整。手册不记录密钥、私有 URL 或其摘要。

## 模型调用与离线复核

本轮共发生 **3 次计费模型调用，合计 39,981 tokens**。沙箱 DNS 失败的运行没有产生模型结果；余额查询不计入这 3 次模型调用。以下 token 数来自保留响应的 `usage`，不是费用估算。

| 运行 | 实际结果 | 模型 tokens | 命令退出码 |
| --- | --- | ---: | ---: |
| `runtime/model-analysis-20261018T044110Z-65294851` | 初次沙箱 DNS `gaierror`，在提供方请求阶段停止 | 无模型调用结果 | 1 |
| `runtime/model-analysis-20261018T044232Z-707ed004` | 原命令取得执行环境网络权限后成功；DegenAI 初始 21 条引用通过，Brain DeFi 20 条引用通过 | 17,395 + 6,067 | 0 |
| `runtime/model-analysis-20261018T044646Z-bfa4d1c0` | 第二次 DegenAI 返回 18 条声明，其中 1 条引用不是来源连续子串；保留为 `INVALID_OUTPUT`，未自动重发 | 16,519 | 1 |
| `runtime/model-reviewed-20261018T045116Z-10a85dc4` | 只读第一次成功响应再做语义审查；DegenAI 接纳 18、拒绝 3；Brain DeFi 接纳 20、拒绝 0；新网络请求 0 | 0 | 0 |

前两次模型调用的引用通过只说明原文确实存在。离线语义复核进一步拒绝 DegenAI 能力目录之外的 3 条声明，没有为得到更好输出再次付费。第二次 DegenAI 的无效引用保留在原运行记录，不拿它覆盖第一次的合格材料。离线复核当时通过一次性 `.venv/Scripts/python.exe -` 命令完成，未固化成额外 CLI；现成结果可直接审阅复用。

当前声明分析入口：

```powershell
.venv/Scripts/python.exe scripts/analyze_declarations.py runtime/model-review-20261017T182601Z-ccb0ed3d
```

以上为本机已有材料的默认计划，不联网。本轮首批真实执行使用同一入口加 `--execute --proxy http://127.0.0.1:7897`；第二次 DegenAI 另加 `--candidates degenai`。每次真实调用先保存来源摘要、投影和请求意图，再保存响应、usage 与验证结果。不要为重现本手册再次调用模型，优先读取上表原件。

## 离线选择评价方案

平台根据来源引用、历史结构、身份和可信协议配置选择已实现方案，不让普通用户挑方案。当前选择器接入的是历史增仓窄范围试点，不声称任意业务类别都已适配。

本机已执行以下离线命令，退出 **0**：

```powershell
.venv/Scripts/python.exe scripts/select_evaluation_plan.py `
  --analysis-run runtime/model-reviewed-20261018T045116Z-10a85dc4 `
  --admission-run runtime/admission-report-20261017T182038Z-f504c54e `
  --history-run runtime/candidate-check-20261017T180114Z-bc374bd3 `
  --source-run runtime/model-review-20261017T182601Z-ccb0ed3d
```

结果位于 `runtime/plan-selection-20261018T052136Z-9bcf3814`：`SELECTED`，政策 `liquidity-history-v1`，匹配声明 `c8`、`c14`；网络请求 0。该结果表示方案匹配完成，完整证据与样本充分性仍由后续核验决定。

## 历史状态读取的实际排障

入口为 `scripts/probe_liquidity_state.py`。当前必须显式给出本项目 runtime 内的交易运行、历史运行和原始索引；RPC 只能从操作者可信配置中的固定提供方选择。下表退出码来自本轮实际命令回执，细节与目录中的 manifest、result、观测交叉核对；早期运行使用修改前的 CLI，不作为当前默认命令。

| 提供方 / 运行 | 已取得的事实与停止位置 | 退出码 |
| --- | --- | ---: |
| BNB 官方，`runtime/liquidity-state-20261018T044800Z-067952d1` | 首次链号 `ConnectError` 后停止 | 1 |
| BNB 官方，`runtime/liquidity-state-20261018T045328Z-550270fb` | 链号与区块头取得；历史 positions 返回 `-32000 missing trie node`，3 次读取后停止 | 1 |
| PublicNode，`runtime/liquidity-state-20261018T045647Z-87f7a4e2` | 链号 `ConnectError` 后停止 | 1 |
| PublicNode，`runtime/liquidity-state-20261018T045912Z-d56d6ffe` | positions 返回 HTTP 403，3 次读取后停止该主机 | 1 |
| ZAN，`runtime/liquidity-state-20261018T050823Z-bbe07233` | 无密钥 URL 加 Bearer 返回 HTTP 400 `path not match`，1 次读取后停止 | 1 |
| ZAN 修复传输认证后，`runtime/liquidity-state-20261018T051558Z-2222c99c` | 链 56、匹配区块头、固定 N−1/N 的 positions 均取得，4 次读取，`HISTORICAL_STATE_READABLE` | 0 |

官方节点缺历史状态与 PublicNode 拒绝访问都保留为平台读证据受阻，没有记成 Agent 失败。ZAN 认证方式依据规范私有路径修复，未覆盖 HTTP 400 旧记录。最后一次只证明历史状态可读，manifest 明确尚未采集完整同块事件，不能凭探针直接宣布功能通过。

当前显式参数示例，默认只展示计划：

```powershell
.venv/Scripts/python.exe scripts/probe_liquidity_state.py `
  --transaction-run runtime/defi-step-20261017T181209Z-f4925047 `
  --history-run runtime/candidate-check-20261017T180114Z-bc374bd3 `
  --history-index 123 --rpc-provider zan
```

只有需要采集新证据时才加 `--execute-public-readonly --proxy http://127.0.0.1:7897`。四次读取顺序为链号、与保留回执匹配的 N 区块头、N−1 状态、N 状态；任一读取失败保存原因后停止，不重新请求已保留的交易和回执。

## 实际可用性采样

本轮命令 `.venv/Scripts/python.exe scripts/sample_availability.py --execute-public-readonly --proxy http://127.0.0.1:7897` 退出 **0**。

`runtime/availability-20261018T051222Z-219f9c9c` 保留 10 个采样点，间隔 30 秒，`samples.json` 中 10 条均为 PASS。这只表示公开运行记录入口在本轮返回约定 JSON 结构。请求耗时属于本机经指定代理的访问体验，不是纯服务端耗时；也不能据此推出业务结果正确。此批样本仅进入 availability，不复用为功能或行为分母。

默认不带执行开关的 `scripts/sample_availability.py` 只显示计划。既有 10 点可直接复算，不为文档、截图或提交重新采样。

## 固定历史任务采集与定向补缺

冻结来源为 `runtime/candidate-check-20261017T180114Z-bc374bd3/brain-agent.response.bin`，具体分组见 `configs/pilots/brain-defi-liquidity-v1.json`。功能 7 个运行与行为 7 个运行互斥，同一任务不能拆到两个分母。成功或整体 `ok` 字段没有被用于预筛选。

| 命令入口 / 运行 | 实际结果 | 新读取 | 退出码 |
| --- | --- | ---: | ---: |
| `collect_liquidity_history.py --history-index 98`；`runtime/liquidity-history-20261018T051729Z-35dc93d7` | 首个完整行为任务证据采集，`REQUESTED_EVIDENCE_RETAINED`，无采集缺项 | 13 | 0 |
| `collect_liquidity_history.py` 全批；`runtime/liquidity-history-20261018T051810Z-e3ed26f4` | `HAS_GAPS`：99、112 被采集器误要求必须有三条交易标签；106 的 wrap/swap/increase 三个区块头出现 `ConnectError`。其余成功证据保留 | 96 | 1 |
| 修正功能组标签适配后，仅 `--history-index 99 106 112`；`runtime/liquidity-history-20261018T052322Z-09bc1979` | 三条任务均取得所需采集证据，无缺项；复用已有成功读取 | 16 | 0 |

99、112 属于功能组，只需其已声明的最终增仓结果与独立状态证据；不能把行为组三笔操作的结构要求套到功能组。106 的连接失败没有算作业务失败。修复后只补这三条，未重跑其他成功任务。

当前可先检查默认离线计划，例如：

```powershell
.venv/Scripts/python.exe scripts/collect_liquidity_history.py `
  --history-run runtime/candidate-check-20261017T180114Z-bc374bd3 `
  --history-index 99 106 112 `
  --reuse-run runtime/liquidity-history-20261018T051729Z-35dc93d7 `
    runtime/liquidity-history-20261018T051810Z-e3ed26f4 `
    runtime/liquidity-history-20261018T052322Z-09bc1979
```

以上路径是本机已有审计输入，不是脚本内硬编码默认值。`--reuse-run` 按保留请求与响应摘要匹配复用；不提供执行开关便不联网。新的显式采集才加 `--execute-public-readonly --proxy http://127.0.0.1:7897`。

## 登记、资产精度与协议上下文

入口为 `scripts/collect_liquidity_context.py`，读取已保留交易，补登记交易与区块、仓位持有人、功能组 token decimals、行为组可信 factory 的池映射。它不触发新交易，也不直接产生分数。

- 初次运行 `runtime/liquidity-context-20261018T052440Z-92dc55d4` 因参数 `TypeError` 在网络发送前退出 **1**，只留下意图 manifest，没有伪称已采到证据。
- 修参后 `runtime/liquidity-context-20261018T052524Z-318916ac` 真实退出 **0**；`result.json` 为 requested 39、retained 39、new_requests 38、planning_gaps 空、stopped_reason 空。链号 1 项复用，其余 38 项为新读取。

当前只读计划用法：

```powershell
.venv/Scripts/python.exe scripts/collect_liquidity_context.py `
  --history-run runtime/candidate-check-20261017T180114Z-bc374bd3 `
  --transaction-runs runtime/liquidity-history-20261018T051729Z-35dc93d7 `
    runtime/liquidity-history-20261018T051810Z-e3ed26f4 `
    runtime/liquidity-history-20261018T052322Z-09bc1979 `
    runtime/liquidity-context-20261018T052524Z-318916ac
```

执行开关和代理与上一节相同。需要新证据才执行；本机已有上下文可以直接用于离线核验。采集无缺项只说明所需响应已保留，登记归属、精度和交易语义仍须由规则逐项检验。

## 必要工程验证与契约生成

本轮新增的下列文件各含 1 个关键 test method，包含必要正常、矛盾和证据缺项分支；仅在对应实现首次完成或相关边界实质变化时执行。最终已执行结果均为 PASS、退出 **0**。

| 受影响文件 | 核验重点 |
| --- | --- |
| `test_claims.py` | 来源连续引用和声明接纳边界 |
| `test_provider_scope.py` | DeepSeek 固定凭证作用域和秘密保护 |
| `test_liquidity.py` | 真实增仓调用、身份/事件/限制和缺证据 |
| `test_scoring.py` | 30/40/30、UNKNOWN 不补零、缺维度无总分、任务互斥 |
| `test_zan_scope.py` | 固定只读方法、私有传输路径、无 Bearer、公开证据无 key、回显脱敏与 method 变更拒绝 |
| `test_disclosure.py` | 精确金额、固定状态重建、同块前后抵消操作与缺/重复日志 |
| `test_behavior.py` | 同一公开增仓步骤内包装、兑换、增仓三笔语义 |
| `test_planning.py` | 有来源的支持方案选择和资料缺项拒绝 |

实际执行入口如下，每条最终均为 1 项通过、退出 0；此处是记录，不是要求再次执行：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_claims.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_provider_scope.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_liquidity.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_scoring.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_zan_scope.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_disclosure.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_behavior.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_planning.py -v
```

ZAN 认证传输由 Bearer 改为私有路径后，仅重跑受影响的 `test_zan_scope.py`，1 项通过、退出 0；没有因此重跑整套。此前候选工具的 5 个有效工程用例直接复用，旧临时目录失败与已完成修复见 [候选工具记录](CANDIDATE_CHECK.md#实际验证与退出码)。

`.venv/Scripts/python.exe scripts/export_contracts.py` 本轮实际退出 **0**。共享类型是契约来源，Schema/TS 由生成器更新，不手工另写一套。文档整理期间没有再运行测试、契约生成或网络调用。

## 离线核验与最终报告

纯规则已分别实现增仓步骤、完整行为步骤、精确披露和三维评分。HTML 报告从样本派生分数，展示真实输入、公布输出、独立核验、分项结论及折叠原件；缺少维度时不给综合分。

报告 CLI 已使用以下本机保留输入完成离线核验与生成，不调用网络或模型：

```powershell
.venv/Scripts/python.exe scripts/build_liquidity_report.py `
  --history-run runtime/candidate-check-20261017T180114Z-bc374bd3 `
  --context-run runtime/liquidity-context-20261018T052524Z-318916ac `
  --availability-run runtime/availability-20261018T051222Z-219f9c9c `
  --plan-run runtime/plan-selection-20261018T052136Z-9bcf3814 `
  --rpc-runs runtime/bsc-check-20261017T180807Z-79c769b9 `
    runtime/defi-step-20261017T181209Z-f4925047 `
    runtime/liquidity-state-20261018T051558Z-2222c99c `
    runtime/liquidity-history-20261018T051729Z-35dc93d7 `
    runtime/liquidity-history-20261018T051810Z-e3ed26f4 `
    runtime/liquidity-history-20261018T052322Z-09bc1979 `
    runtime/liquidity-context-20261018T052524Z-318916ac
```

| 实际运行 | 结果 | 退出码 |
| --- | --- | ---: |
| `runtime/evaluation-report-20261018T053426Z-ba06f389` | 首次完成离线核验与报告，注册 PASS，24 个评分槽位与 13 条不适用背景记录 | 0 |
| `runtime/evaluation-report-20261018T053613Z-fe5237bc` | 改进可读性后仅复用同一批原件生成新版，评分不变；新增网络与模型请求均为 0 | 0 |

两版 `report.json` 的实际结果一致：

| 维度 | 得分 | 计划 / 已保留槽位 | 通过 / 未通过 / UNKNOWN |
| --- | ---: | --- | --- |
| 服务可用性 | 88.89 | 10 / 10 | 10 / 0 / 0 |
| 功能声明一致性 | 100.00 | 7 / 7 | 7 / 0 / 0 |
| 交易行为可靠性 | 100.00 | 7 / 7 | 7 / 0 / 0 |
| 综合分 | **96.67** | 状态 `COMPLETE` | 按 30% / 40% / 30% 计算 |

可用性成功响应 p95 为 6000 毫秒，反映本机指定代理线路体验，因此该维度没有因 10 次响应均成功就自动满分。功能和行为的固定样本均核验通过，保留其真实满分，不制造失败。另有 13 条明确无动作记录以 NOT_APPLICABLE 背景保留，不进入 24 个评分槽位或任何评分分母。

注册核验同时对应登记事件、登记时公开的 Operating wallet / 记录入口及登记后的任务关系。注册 NFT 持有人与执行钱包分角色处理，不要求二者相同，也不把收款地址直接当执行者。精确登记证据和每条任务结果保留在 `background.json`、`report.json` 与 manifest 所列原件中。

最新可读报告为 [report.html](../../runtime/evaluation-report-20261018T053613Z-fe5237bc/report.html)。新版将原始最小单位金额转换成精确 token 金额，以 CST（北京时间）显示时间，补充中文通过说明，并解释早期平台采集缺项已经定向补齐。旧版及失败采集目录全部保留，没有覆盖原件或重新采集成功证据。

### 完整槽位门槛修复

核查评分核心时发现，原实现只检查确定结论门槛，可能在仅提供 8 / 10 个可用性记录时提前给分。已修复为同时要求保留全部 10 个槽位，并至少有 8 个确定结论；中断或证据不足的槽位必须保留为 UNKNOWN。功能、行为各完整保留 7 个任务并各有 7 个确定结论。该修复不会改变本轮已有全部 24 个槽位的得分。

实施解释另记 [ADR-0005](../adr/0005-evidence-binding-and-complete-slots.md)，未改写 ADR-0004 的冻结政策或其摘要。追加缺槽断言后，仅再次执行受影响的 `.venv/Scripts/python.exe -m unittest discover -s tests -p test_scoring.py -v`，1 项通过、退出 **0**。没有重跑其他测试；共享类型和 Schema 没有变化，因此没有重复生成契约。

### 当前交付边界

本轮已有 **1 个真实对象完成上述窄范围三维评分**，不是所有动态能力、收益或资产安全均已评价。至少 10 个真实公共 Agent 的目标仍未完成；完整网站、API、worker 与 PostgreSQL 尚未实现。

新报告的浏览器视觉验收仍为 **BLOCKED**。此前 Chrome 进程崩溃的问题尚未解决，本轮没有重复同类崩溃尝试，也没有声称桌面或手机实际视觉检查通过。离线生成成功与浏览器呈现验收分开记录。
