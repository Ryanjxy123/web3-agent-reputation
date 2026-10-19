# 候选可测性核实

当前是候选准入工具，不是完整 API、worker 或网站。模型、付费接口和资产操作不启用。具体进度与命令结果见 STATUS。

## 独立环境

Python 3.12.4，uv workspace；Pydantic 2.13.5 与 httpx 0.28.1 已在新环境验证后生成 uv.lock。无需加载旧项目环境。

在项目根目录使用 uv：

```powershell
uv sync --frozen
.venv/Scripts/python.exe scripts/check_candidates.py
```

第二条命令仅输出计划，默认不联网。本机 uv 可执行文件位于 `D:/web3-runtime/tools/uv-env/Scripts/uv.exe`；解释器位于 `D:/web3-runtime/tools/python/cpython-3.12.4-windows-x86_64-none/python.exe`。这些是工具位置，不是旧源码依赖。

## 有范围的真实只读检查

仅在操作者已授权免费公开只读调用时使用以下形式：

```powershell
.venv/Scripts/python.exe scripts/check_candidates.py --execute-public-readonly --proxy http://127.0.0.1:7897 --targets brain-agent brain-burns catalog-defi
```

目标必须来自 services/platform 的静态注册表；`--targets` 可避免重跑已有请求。执行时必须显式传 `--proxy`，遗漏即拒绝，避免静默直连。每轮目录在 runtime 中独立生成，包含发送前的 manifest、原始响应和对应观测。任何 401/402/403/429 都停止该域，不能换账户、出口或路径绕过。

链上只读核实的固定 RPC 与来源记录在 configs/trusted-rpc.json。脚本先检验链号、固定区块，再读取注册与选定历史交易；历史回执成功不直接等于任务履约成功。数据源与选取规则保存在其计划中，不使用秘密。

先选择本仓库 runtime 中已生成、包含 `brain-agent.response.bin` 和 `brain-burns.response.bin` 的检查目录。克隆仓库后需使用本机实际产生的目录；`--source-run` 为必填，不接受 runtime 之外的路径。

```powershell
$sourceRun = 'runtime/<本机已生成的候选检查目录>'
.venv/Scripts/python.exe scripts/check_bsc_history.py --source-run $sourceRun
```

此命令只列出计划与所选交易的来源字段。审核计划并取得公开只读授权后，才使用：

```powershell
.venv/Scripts/python.exe scripts/check_bsc_history.py --source-run $sourceRun --execute-public-readonly --proxy http://127.0.0.1:7897
```

每轮最多 10 请求，不重试；RPC、HTTP 或链号错误即停止。

## 复用证据生成报告

```powershell
.venv/Scripts/python.exe scripts/build_admission_report.py runtime/<一次真实检查目录> runtime/<另一次检查目录>
```

此步骤仅读取既有证据，不联网，生成新目录中的 JSON 和自包含 HTML。未检查、缺资料、缺授权及未适配不得写成已确认业务失败。检查报告的缺项先解决，再开展足够样本的正式评分。

共享契约从类型生成：

```powershell
.venv/Scripts/python.exe scripts/export_contracts.py
```

必要测试的实际结果已记入 STATUS；不要把以上命令当成每次修改都需重跑的检查清单。

## 实际验证与退出码

依赖与工具：

- 使用独立 Python 创建 `.venv`、安装并读取 Pydantic/httpx 版本：退出 0。
- `D:/web3-runtime/tools/uv-env/Scripts/uv.exe lock`、`uv sync --frozen`：各退出 0；使用显式本机代理与项目内工具缓存。
- `.venv/Scripts/python.exe scripts/export_contracts.py`：退出 0。共享类型未再变化，不重复生成。
- `.venv/Scripts/python.exe scripts/check_candidates.py`：退出 0，默认计划、不联网。
- 新增显式代理入口校验后，执行 `.venv/Scripts/python.exe scripts/check_candidates.py --execute-public-readonly`：当前 PowerShell 命令报告退出 1，按预期显示必须提供代理并在联网前拒绝。只验证此新失败路径，没有重发已通过调用。
- `.venv/Scripts/python.exe scripts/check_bsc_history.py --source-run runtime/candidate-check-20261017T180114Z-bc374bd3`：退出 0；这是移除硬编码路径后的默认计划验证，未重发链请求。

必要工程验证（5 个不同用例均已有有效通过结果）：

- `PYTHONPATH=packages/core/src;services/platform/src` 后执行 `.venv/Scripts/python.exe -m unittest discover -s tests -v`：初次退出 1；核心 2 例通过，HTTP 2 例因沙箱临时目录权限报错。
- 临时目录改到本项目 runtime 后，仅重跑失败文件 `-m unittest discover -s tests -p test_safe_http.py -v`：退出 0，2 例通过，覆盖出口/重定向和大小/限流停止。
- 后续修正 HTTP 成功不能证明功能正确，新增并仅运行对应回归：`PYTHONPATH=packages/core/src;services/platform/src;tests`，`-m unittest test_safe_http.SafeHttpTests.test_http_success_is_not_a_functional_verdict -v`：退出 0，1 例通过。未为提交或文档重跑通过项。

真实外网采集：

- `scripts/check_candidates.py --execute-public-readonly --proxy http://127.0.0.1:7897 --targets ...`：三轮分别选择首批 9 项、Brain 资料 4 项、仓位查询 1 项，各退出 0。完整请求方法、地址、参数和当时用途由各轮 manifest/observation 保留。
- 初版 `scripts/check_bsc_history.py --execute-public-readonly --proxy http://127.0.0.1:7897`：退出 0，10 次链读取；当时输入目录固定，当前 CLI 已改为显式 `--source-run`。
- 通过 SafeHttpClient 的受控 Python 补查命令：退出 0，仅增仓交易及回执 2 次；输入来源路径与预算见 `defi-step-20261017T181209Z-f4925047/manifest.json`，方法和参数见两个 observation。不是重查包装 BNB 交易。
- `D:/web3-runtime/tools/foundry-v1.8.4/cast.exe keccak 'IncreaseLiquidity(uint256,uint128,uint256,uint256)'`：退出 0，与真实事件主题一致，未联网或执行交易。
- `scripts/build_admission_report.py` 加上述 5 个本地证据目录：退出 0，5 候选 / 26 观测 / 0 完整准入 / 0 输入问题。报告调整仅复用原件，没有再采集。

报告显示检查与材料准备：

- 首版 14 观测报告的 Chrome 桌面渲染退出 0，实际检查 `runtime/report-qa-20261018/desktop.png`，卡片与中文可读。最终版增加证据与调整文字，布局代码沿用。
- 最终版桌面、手机 Chrome 渲染均进程异常退出 `-2147483645`，未产生截图；Edge 手机渲染异常退出 `-1073741819`。当前环境下最终截图验收为 **BLOCKED**，手机显示不能声称已通过；未关闭浏览器安全机制或升级权限。
- 模型审阅材料准备：初次 16KB 输入界限不足退出 1，未截断资料/发送请求；调整为 64KB 后离线命令退出 0，2 份完整材料、0 请求、0 密钥读取。
