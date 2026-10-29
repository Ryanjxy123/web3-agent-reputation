# CoW 公开任务原件装配

新增 `scripts/assemble_cow_task_items.py`，只生成现有exporter所需的task-items数组。没有修改已pin的操作器、协议、报告适配器或冻结计划；不发网络请求、不读秘密、不签名，不打开数据库，也不自行发布source/报告。

输入为明确SHA的FROZEN CoW计划、计划目录下的 `tasks/<task_key>/source-item-http-*.json` 与 `states/*/source-item-execution.json`，以及显式指定的旧公共source或fixture。按任务UUID、任务ID、TASK_INTENT中的原计划SHA/请求/expected、原生HTTP请求参数与阶段时间逐项核对。任务缺原件就保留未观测；失败/错误原件不因缺少正常交付而被删除。一次任务多个HTTP阶段仍只算一个任务。

执行项先用原有adapter核字段与证据，再要求原始order/trades/RPC绑定同一canonical交易。只有这样的执行状态参加选择，按原observation时间选最新，完全不使用随机state目录名排序。最新状态仍不足64块或未清零授权时，保留原adapter的UNKNOWN，不将canonical交易与正式B通过混为一谈。没有canonical执行项时保留真实HTTP，移除不能支持执行结论的execution引用。所有旧原文件不改。

## C01直接复用

本机原pilot的quote/build/validate、PREPARED_ORDER、前状态、公开CoW order/trades和链原件都已存在。可用 `tests/fixtures/cow_swap_pilot_public_case.json` 提供显式source.tasks元数据及逐文件SHA：脚本仅解出source元数据，核实际本机原公共文件SHA；**不会恢复、采用或改写fixture里的受控DRAFT计划**，也不会把测试fixture变成新业务。C01沿用真实旧经济意图的task_key、首次frozen_at与新计划中的retained_intent SHA。

如以后已有正式旧source，改用 `--retained-source <public-source.json>`，两个retained选项互斥。缺少明确旧source输入时，不会猜测pilot状态目录或扫描私密操作目录。

公开order API响应中已经公开的signature原始字段仍由原adapter按精确GET URL核验；脚本只保存引用，不提取或生成签名。SIGN/SIGNED/SEND/SUBMIT_INTENT、`.private`和secret路径由已有公共路径门禁拒绝，不能进入task-items。

## root实际收口命令

以下步骤等实际任务与所需链证据到齐后由root运行。本轮只做dry-run，没有创建下面任何正式输出。重复执行时选新的v2/v3文件或目录，旧文件不覆盖。

```powershell
.venv/Scripts/python.exe scripts/assemble_cow_task_items.py --plan runtime/ophis-cow-campaign-20261029/plan.json --plan-sha 4112a7a019a4e9145ac3cd83e763646bfa7512cc74fb596483bec6b22a986c88 --retained-fixture tests/fixtures/cow_swap_pilot_public_case.json --output runtime/ophis-cow-closeout-20261029/task-items-v1.json

.venv/Scripts/python.exe scripts/export_cow_swap_sources.py --plan runtime/ophis-cow-campaign-20261029/plan.json --task-items runtime/ophis-cow-closeout-20261029/task-items-v1.json --output runtime/ophis-cow-source-20261029-v1

.venv/Scripts/python.exe scripts/build_cow_swap_report.py --source runtime/ophis-cow-source-20261029-v1/source.json --output runtime/ophis-cow-report-20261029-v1
```

只核已有装配、不写task-items，使用同一参数将 `--output ...` 替换为 `--dry-run`。stdout保留每个任务实际选中的source-item、阶段数、canonical标志和原观察时钟，便于核查选取；它不输出HTTP正文或签名。

## 本轮必要核查

AST通过；一次真实当前原件dry-run通过，退出0：30冻结槽位、24个实际观测任务、1个canonical执行项（C01旧pilot）；C03–C08当时尚无task-item，C02已有3阶段HTTP但没有canonical执行项，未将其算成新成交。数据随root采集继续增长，最终以收口时的原件重装配。

同一核查补充错误plan SHA立即拒绝，退出0；没有重跑旧suite，没有生成正式source/报告，也没有HTTP/RPC、钱包或PG动作。收据 `runtime/cow-items-assembler-review-20261029/receipt.json`。本项没有改变三维、权重、阈值或证据判据，不需要修改评分ADR。

后续缺项由root实际采集补齐：剩余任务原件、真实订单UID与事件/净资产、64块距离及授权清理。装配器不补造缺项、不重发请求、不通过旧pilot给新任务填分。
