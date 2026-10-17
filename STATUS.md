# 新项目当前状态

更新日期：2026-10-18。已完成 `REQUIREMENTS_ALIGNMENT`、`CANDIDATE_TOOLING`；`CANDIDATE_FEASIBILITY` 尚未完成。下一项 `MODEL_PILOT` 的新增费用授权为 **WAITING_USER**。按用户睡前要求，本轮收口保存，等待确认后再推进模型接入。

## 实际实现

- 新目录使用独立 Python 3.12.4 / uv workspace，Pydantic 2.13.5、httpx 0.28.1 已实际安装验证并锁定；没有父目录源码 import。
- `packages/core` 实现六项候选准入、四态结果与用途类型，保持纯规则。完整准入由六项结果计算，不接受调用方直接指定 READY。
- JSON Schema 与 TypeScript 由共享类型生成。尚无 API，不手写虚构 OpenAPI。
- `SafeHttpClient` 默认不发请求；静态目标、显式启用、代理配置、HTTPS 公网地址检查、大小/时间/请求上限、不跟随重定向或重试。401/402/403/429 停止该主机。
- 候选采集 CLI 与固定可信 BSC 读取 CLI 实现；发送前保存范围，响应和观测只追加。BSC CLI 已改为显式传本机 `--source-run`，不绑定本次随机目录。
- 离线聚合核对输入摘要，生成 JSON 和中文 HTML。报告逐项解释已核实、缺什么及下一步，技术原件折叠；这是候选检查原型，还不是完整网站或正式声誉报告。
- `reference/CANDIDATES.md` 记录 5 个实查候选和 3 个提供方资料线索。未从旧项目导入名单、分数、数据库或证据。

## 本轮真实结果

真实采集总计 **26 条 HTTP 观测**，不是 26 次成功评价：3 次免费业务查询、11 次资料采集、12 次链上只读请求。全部原始采集取得 HTTP 200；业务正确性另行核验，不因此给满分。

- Brain DeFi #363709：直接核实注册，登记持有人与公开执行钱包、查询 owner、历史交易 sender 一致。第一笔交易只是包装 BNB；必要补查后核实一条增仓调用及同仓位、同管理合约事件。
- 该查询实际只接受仓位或钱包，公开源码未固定 block，不能把别的时刻的费用/区间数据拿来判对错。因此独立业务判据仍 UNKNOWN，历史可靠性采样未完成。
- Brain #49467：核实身份存在；所选旧 burn 交易涉及不同代币和执行者，缺迁移/归属证明，保持 UNKNOWN。
- DegenAI：免费资产查询返回数据，ERC-8183 任务线未部署。Arena：查询返回空资料，与目录不同，需独立溯源。DARKSOL：免费业务和链上证明条件未闭合。
- 新线索没有凑数：b1e55ed 的模拟盘不计真实交易，Molttail 的静态解析/演示 fallback 不计真实成功，ACK 身份不自动转给 Etch。

**完整三维准入 0，正式完整评分 0；至少 10 个的验收目标未完成。** 不能据本轮有限候选断言整个目标不可行。具体来源、链事实、缺项和证据目录见候选记录。

可审阅报告：

`runtime/admission-report-20261017T182038Z-f504c54e/admission-report.html`

同目录保留输入 manifest、JSON 结果和 26 条观测。0 个输入摘要/解析问题。此前报告作为中间版本保留，不覆盖原件或已发布结果。首批旧采集中的 functional/HTTP PASS 仅是采集标记，未计评分分母，语义说明见 ADR-0002。

## 等待用户决定：新增模型额度

模型尚未调用，密钥未为本轮分析读取。旧授权不自动续用，依据 LOCAL_CONFIGURATION 的“历史费用与调用记录”。

提议新增最多 **20 次 / 总保守预留 1 美元**，每次发送前预留 0.05 美元，首批只做 2 个资料充分对象。模型只提取有原文出处的业务承诺、限制和输入输出，辅助匹配方案，不给最终分、不启用工具、不调用付费 Agent。首批没有可执行且有独立判据的方案时停批量；401/402/403/429、未决请求、费用记录不清时停止，不盲目重发。旧账本与旧预留不清除。

审阅材料：`runtime/model-review-20261017T182601Z-ccb0ed3d/`。包含 DegenAI 完整能力发现 JSON（34,408 字节投影）、Brain DeFi 官方功能页 HTML 文本投影（6,336 字节），各自原件/投影摘要及来源分开记录。不是只送名字，也没有把目录现成分数当模型输入。此材料包不是已实现模型网关；费用持久化、共享输出类型和调用边界在授权后实现。

2026-10-18 只读核对 [DeepSeek 官方模型说明](https://api-docs.deepseek.com/quick_start/pricing/)与[Responses API](https://api-docs.deepseek.com/api/create-response/)：文档支持 `deepseek-flash`、`POST /responses` 及限制输出/关闭思考。没有通过带密钥 API 验证当前账户有效性。额度确认只解决费用前提，不会补出缺失的业务判据或交易样本。

## 实际验证摘要

独立依赖安装、uv lock/sync、类型生成、默认计划、26 条真实采集与离线报告均退出 0。5 个不同工程用例均已有有效通过结果；初次 HTTP 用例遇到临时目录权限问题，仅重跑失败项，后续 HTTP/功能语义改动只跑一个必要回归。未为提交或文档重跑测试。

首版桌面截图已实际查看；最终版 Chrome/Edge 截图进程异常，手机显示验收 BLOCKED，未声称通过。模型材料首次大小界限不足后保留完整输入调整，离线准备退出 0；模型请求始终为 0。命令、退出码、失败及重测原因完整记录于 [候选工具运行记录](docs/runbooks/CANDIDATE_CHECK.md#实际验证与退出码)。

## 尚未实现或未验收

- 完整 Vue 网站、接入自动编排、FastAPI、worker、数据库、正式评分和足量采样：未实现。
- PostgreSQL/Anvil 集成与并发验收：NOT_RUN；没有用 SQLite/内存替代。
- 模型 API、付费 Agent、签名、主网写入、资产交易：NOT_RUN。
- 安装工具：Node 22.17.0、PostgreSQL 17.11、Foundry 1.8.4 的独立可执行文件已找到；仅工具检查，不是服务验收。Docker 未找到，不影响本轮候选工具。
- 代理已保存用户级 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY；当前命令显式传代理。Codex 桌面重启后的实际重连验收仍为 RESTART_VERIFICATION_PENDING，不重复已通过 HTTP 检查。

## Git

独立仓库根目录与分支已核实：`D:/xjtu_project/block_chain_new/block_chain_new_new`，`codex/candidate-feasibility`。实现提交 `b27a54e`；事实与状态另行本地提交，文档提交号见 `git log -1`。暂存差异检查及常见秘密/私有目录扫描均退出 0，没有暂存 runtime、密钥或虚拟环境。

新远程 REMOTE_NOT_CONFIGURED；push、PR、部署均 NOT_RUN。未操作父仓库、旧服务、其他分支或共享历史。
