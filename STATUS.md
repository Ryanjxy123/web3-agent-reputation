# 新项目当前状态

更新日期：2026-10-18。已完成 task：`REQUIREMENTS_ALIGNMENT`。下一 task：`CANDIDATE_FEASIBILITY`。

## 已完成

- 已按 `grill-me` / `grilling` 完成七项核心需求对齐，范围见 README，执行原则见 AGENTS，不重新开始访谈。
- 首版本机运行；浏览与接入两个主入口；平台自动选方案并执行，按需重评并保留历史。
- 至少 10 个真实公共 Agent 完整三维分及综合分，评分需有真实区分能力；先筛可测，不可测候选保留扩展记录。
- 权重已确认：可用性 30%、功能声明一致性 40%、交易行为可靠性 30%。政策、兼容性与后续必要验证见 ADR-0001；具体指标和阈值尚待设计。
- 新目录独立 Git 已核实；未扫描旧项目源码、复制秘密或启动旧服务。
- 已安装 skill，已保存用户级 HTTP 代理环境。桌面重启后的重连验收仍待完成，详见 LOCAL_CONFIGURATION。

## 下一步与实际进度

- 候选与缺项集中保存于 reference/CANDIDATES.md。目前三个对象仅完成资料调研，完整三维证据准入通过数为 0，不满足 10 个目标。
- 先核实注册、真实业务接口、独立判据及执行归因，再选取对象；设计固定评分细则，随后完成第一个真实闭环、同类复用并扩大覆盖。
- 公共业务可调用性和 Agent 自身执行证据能否同时取得，是当前主要待验证问题。不以查询别人交易、收款钱包或注册成功替代交易可靠性。
- 新应用、数据库、业务评价和模型请求均尚未开始；旧评分不计入新交付。
- 默认主动外网评价关闭，新模型预算未授权，旧额度不自动延续。先完成不依赖调用的准备，实际调用按后台授权范围执行，不增加前台选方案或确认步骤。
- Codex 代理桌面重启验收：`RESTART_VERIFICATION_PENDING`，不重复已完成的 HTTP 检查。

## 实际验证

- 新目录 `git status --short --branch`、`git rev-parse --show-toplevel`：退出 0。各轮文档暂存修改已审阅。
- 本次需求收口新增 ADR 和候选清单后，`git diff --cached --check` 及暂存文本常见秘密模式扫描均退出 0。该检查针对新增文档，不是应用测试。
- 既有代理检查：GitHub HTTP 200 / CONNECT 200，Codex 未认证 GET HTTP 405 / CONNECT 200，curl 均退出 0；环境持久化和通知退出 0。仅证明 HTTP 路径可用。
- skill 安装：首次路径错误退出 1；查明目录后 `grill-me` 与 `grilling` 安装各退出 0。
- 只读资料调研未调用 Agent 接口或 RPC；部分网页读取失败，未计作 Agent 业务失败。
- 应用测试：`NOT_RUN`。本轮只有文档、资料调研与工具配置，无应用实现，不重复历史测试。

## Git

工作分支：`codex/requirements-alignment`。本状态与本轮需求收口文档一并本地提交，具体提交以 `git log -1` 为准。

新远程 `REMOTE_NOT_CONFIGURED`；push、PR、deployment 均 `NOT_RUN`。
