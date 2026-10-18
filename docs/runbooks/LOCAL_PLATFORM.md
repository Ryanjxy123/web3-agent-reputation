# 本机平台启动与实际验收

日期：2026-10-18。工作目录：`D:/xjtu_project/block_chain_new/block_chain_new_new`。

Vue 网站、FastAPI、独立 worker 与 PostgreSQL 已实现。当前本机已有 5 个候选，同一个已适配对象已有两份完整窄范围报告；新提交的正式任务已自动完成，实际结果见文末。历史采集与离线核验用法见 [MODEL_EVIDENCE_LOOP.md](MODEL_EVIDENCE_LOOP.md)。

## 日常启动

本机依赖、前端构建、数据库连接文件和运营 profile 已准备好。普通用户不用填写 RPC、模型密钥或数据库信息，在项目根目录运行：

```powershell
.\scripts\start_local_platform.ps1
```

该命令启动并核实本项目 PostgreSQL，启动本机 API，检查数据库健康后运行前台 worker。默认 **public-off**：已有目录与报告可浏览，新的公开采样不会自动启用；匹配到已支持对象的任务会清楚说明尚未启用新采样，不产生新分数。

本次已获授权的免费公共只读评价使用：

```powershell
.\scripts\start_local_platform.ps1 -EnablePublicReadOnly -Proxy 'http://127.0.0.1:7897'
```

打开 [http://127.0.0.1:7754/](http://127.0.0.1:7754/)。网站与 API 同源，直接使用已有 `apps/web/dist`，无需额外运行 Vite。页面提供浏览和接入两个入口；提交后直接排队，只有活跃任务自动读取进度，成功后打开报告。

`-Once` 仅供单任务或启动验收：worker 至多处理一个待处理任务，队列为空时立即退出，启动器随后停止它创建的 API。日常使用保持启动器运行，不加 `-Once`。退出启动器会停止其创建的 API；PostgreSQL 保留运行，可单独停止：

```powershell
.\scripts\stop_local_postgres.ps1
```

只管理数据库时使用 `.\scripts\start_local_postgres.ps1` 与上述停止脚本；数据与现有凭证保留。

## 本机实例与运营配置

| 项目 | 当前实际配置 |
| --- | --- |
| PostgreSQL | 17.11，`127.0.0.1:55438`，库/角色均为 `reputation` |
| 数据目录 | `runtime/platform-postgres`，与旧项目分离 |
| PostgreSQL 工具 | `D:/web3-runtime/tools/postgresql-17.11/pgsql/bin` |
| API 与生产静态网页 | `127.0.0.1:7754` |
| API/worker 连接配置 | `runtime/platform-config/database-url.txt`，可由运营者环境变量覆盖，不进入公开接口 |
| 运营 profile | `runtime/platform-config/profiles.json`，引用已适配身份、政策与保留证据目录 |
| 启动日志 / 任务原件 | `runtime/platform-logs` / `runtime/worker-jobs` |

API 首次尝试绑定 8015 时，Windows 返回 `Errno 13`。随后一次原生 `socket.bind(127.0.0.1, 0)` 诊断由系统分配到可用的 7754，API 已在该端口真实启动；没有修改防火墙。当前启动脚本默认 7754，开发代理也已同步；Vite 的 5175 仅保留为开发配置，尚未完成该端口的真实启动验收。

profile 属于运营配置，本机已配置首个历史增仓方案。worker 对已支持对象执行新的 10 点可用性采样，再复用保留的历史交易、状态与上下文独立核验，生成新版本；当前流程不调用模型、不触发资产操作。规范标识尚缺适配资料时返回 `NEEDS_INFO`，无法识别的输入返回 `UNSUPPORTED`，不会冒充已评价或给零分。

## 安装、构建与首次导入

本轮 uv 锁定/依赖安装、前端独立 pnpm 锁定安装与首次构建均已真实退出 0。Python 使用项目 `.venv`，前端实际使用 Node 22.17.0、pnpm 11.25.0；精确依赖见 [前端说明](../../apps/web/README.md)。新机器安装入口为：

```powershell
uv sync --locked
```

然后在 `apps/web` 运行 `pnpm install --frozen-lockfile`、`pnpm run build`。当前本机日常启动可复用已有安装和构建。

运营者在取得真实证据后初始化并导入；以下是当前本机已存在的输入，不是 clone 自动附带的演示数据：

```powershell
.venv/Scripts/python.exe scripts/import_local_report.py `
  runtime/evaluation-report-20261018T053613Z-fe5237bc `
  --initialize --candidates runtime/admission-report-20261017T182038Z-f504c54e
```

主库已实际导入 **5 个候选**，首份报告 ID 为 `251eb31d-973d-4cb1-ba4a-4a735d652ec7`，综合分 **96.67**；三维为 88.89 / 100 / 100，限于报告列明的历史增仓范围。本机已有记录，不需在每次启动时重复导入。

`runtime` 中的公共采集原件、数据库和私有 profile 均被忽略，不入 Git。新 clone 没有这些采集证据，不能凭空生成上述 seed 报告。应按采集运行手册取得真实原件、生成报告，再由运营者导入并配置对应 profile；普通网站用户只提交注册资料。

## 本轮已执行的验证

实际页面/API 读请求保存于 `runtime/local-platform-check-20261018T055831Z-95665164`。`checks.json` 记录以下 5 个真实 HTTP 入口均为 **200**：

- `/`：生产构建网页。
- `/api/health`：API 与 PostgreSQL 就绪。
- `/api/agents`：5 个候选的真实目录。
- `/api/agents/brain-defi`：对象详情与历史报告。
- `/api/reports/251eb31d-973d-4cb1-ba4a-4a735d652ec7`：已导入的详细报告。

响应原件已保留，中文按 UTF-8 正确读取。HTTP 读取成功与浏览器 DOM 交互验收分开记录。

独立库 `reputation_verification` 的集成用例首次仅因 `pg_hba.conf` 未允许该库连接而失败。专门增加限定到该库、角色 `reputation`、`127.0.0.1/32` 的 SCRAM 规则并 reload 后，只重跑该受影响用例：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_local_platform.py -v
```

1 个用例 PASS，退出 **0**，使用私有 `REPUTATION_TEST_DATABASE_URL_FILE` 指向独立验收库。实际覆盖 3 个并发领取者仅一个获得任务、租约过期后旧 fencing token 无法续租或提交、报告 UPDATE/DELETE 追加写保护，以及正常和错误 API、证据摘要与下载归属。没有使用 SQLite 或内存数据库替代 PostgreSQL；已有有效结果直接复用。

共享 API DTO、Schema 与 TS 从 core 类型生成。`.venv/Scripts/python.exe scripts/export_api_contracts.py` 已退出 **0**，导出实际 FastAPI 路由的 `services/platform/generated/openapi.json`，共享字段统一由类型维护。

前端首次 `pnpm run build`（`vue-tsc` + Vite）PASS、退出 0；随后真实集成审查发现示例按钮误选旧短注册线索、身份标签不准确，修正必要 Vue 源并改善结论说明后，仅重新构建受影响前端一次，同样 PASS、退出 0。开发代理 8015→7754 的配置调整未触发重建。

后续只读审查进一步修复三个实际使用问题：未评分对象的旧短注册线索不再自动填入表单，任务原因以服务返回的明确 `message` 展示，已评分报告的 `runtime` 原件链接接入现有受控证据附件下载 API。候选没有报告上下文的本机路径仍为文本，HTTPS 来源链接保留；原件入口只在折叠技术区中出现。因这些 Vue 源实际变化，再仅执行受影响的 `pnpm run build` 一次，类型检查与构建 PASS、退出 **0**，生成 `dist/assets/index-DA0fC7Eh.js`，CSS 未变化。没有启动服务或重跑其他测试。

上述重建均对应真实源代码问题修复，没有为提交重复测试。浏览器视觉仍 **BLOCKED**，未重复 Chrome 崩溃尝试，未声称已完成浏览器交互 DOM 验收。

## 正式提交与当前交付范围

主库真实 POST `/api/evaluations` 返回 **202**，任务为 `88a22786-55ec-462e-a7e7-d440f215587c`，原始 QUEUED 响应保存于上述检查目录的 `submitted-job.json`。任务从 2026-10-18 **13:58:35+08:00** 提交至 **14:03:45+08:00** 完成，自动经历 QUEUED、RUNNING 与采集/核验/保存报告，最终为 **COMPLETE**。

本次新报告 ID 为 `568a411d-2548-48ed-8df7-1dd7840a903f`，原件位于 `runtime/evaluation-report-20261018T060340Z-4c27cea3`，实际结果如下：

| 维度 | 本次得分 | 实际样本 |
| --- | ---: | --- |
| 服务可用性 | 93.09 | 10 PASS，成功响应 p95 4109 毫秒 |
| 功能声明一致性 | 100.00 | 7 PASS |
| 交易行为可靠性 | 100.00 | 7 PASS |
| 综合分 | **97.93** | 状态 `COMPLETE` |

这是同一个 Agent 的第二次报告：重新执行本次可用性采样，复用保留的历史任务证据并重新独立核验，产生新的时间与报告版本。新可用性耗时使分数发生实际变化；历史业务样本没有因复评重新触发主网操作。第二份报告不增加真实对象数量，首份 96.67 分报告继续保留。

**静态资源、报告时序与实际启动器验收：PASS。** `runtime/complete_local_acceptance.py` 已改用带时区的日期时间解析，复用已完成结果执行后退出 **0**；没有重复采样。`worker-and-assets-checks.json` 确认新报告生成晚于提交（`generated_after_submission=true`），对象历史报告数为 2；实际静态资源结果为：

| 资源 | HTTP | 类型 |
| --- | --- | --- |
| `/assets/index-UpdWLm_I.js` | 200 | `application/javascript` |
| `/assets/index-Bi-5aUVn.css` | 200 | `text/css; charset=utf-8` |

该次 HTTP 验收对应当时构建的版本；后续三处前端使用问题修复产生的新 JS 本轮仅完成构建验证，结果见上一节。

停止此前自己启动的手动 API 后，实际执行 `.\scripts\start_local_platform.ps1 -Once`，退出 **0**：复用 PostgreSQL、通过 API 7754 的数据库健康检查，再领取 DegenAI 的规范注册输入任务 `94fa5a31-0a6e-4e44-a126-0d4a7d52927d`，终态 **NEEDS_INFO / DONE**，未产生报告，公共请求数为 0。

随后通过仓库读取与 socket 检查确认启动器自己的 API 已停止，原有两份报告仍保留，该核对也退出 **0**。原件 `worker-and-assets-checks.json`、`launcher-check.json` 均位于 `runtime/local-platform-check-20261018T055831Z-95665164`。早期时间字符串比较错误只属于验收汇总，实际测量与报告没有失败。

目前已有 1 个真实对象完成窄范围三维评分；至少 10 个真实公共 Agent 的目标仍未完成。网站/API/worker/PG 已实现，真实提交到报告保存、历史版本保留、不可适配任务和启动器生命周期均已通过本轮实际验收。浏览器视觉仍为 **BLOCKED**，未声称完成 DOM 交互或桌面/手机视觉验收。
