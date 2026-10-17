# Web3 Agent 声誉平台重建交接

创建日期：2026-10-18。本目录是新项目的独立交接起点，目前只有文档和 Git 基础配置，没有新应用、部署、数据库或真实测评。

用户决定先重新对齐需求，再建设一个精简版本。产品的两个主入口是“浏览 Agent 声誉”和“接入 Agent 产生评价”，报告必须让普通用户看懂。旧项目仅作为经验、证据和可选模块来源。

## 阅读顺序

1. [经验教训](LESSONS_LEARNED.md)：为什么原项目没有把工程投入转化为产品能力。
2. [初步规划](PLAN.md)：已确认方向、待对齐问题和按用户闭环验收的顺序。
3. [本机配置位置](LOCAL_CONFIGURATION.md)：现有 DeepSeek、RPC 凭证和历史费用记录的位置。
4. [新对话交接 prompt](HANDOFF_PROMPT.md)：全文复制到新对话即可。
5. [当前状态](STATUS.md)和[Git 使用说明](GIT_SETUP.md)：区分已经完成的交接准备与后续工作。

`AGENTS.md` 是本目录内的工作约束。历史事实的精简快照见 [reference/PREVIOUS_PROJECT_FACTS.json](reference/PREVIOUS_PROJECT_FACTS.json)。

## 目录与仓库

- 新项目：`D:/xjtu_project/block_chain_new/block_chain_new_new`。
- 旧项目：`D:/xjtu_project/block_chain_new`。
- 新目录使用自己的 `.git`，不作为父仓库的 submodule 或 gitlink 提交。
- 不复制旧仓库历史、runtime、数据库、依赖目录或凭证文件。
- 新 GitHub 仓库地址尚未提供，`origin` 不配置；没有创建远程仓库或推送。
- 新目录内运行 Git 命令前，先核实 `git rev-parse --show-toplevel` 指向新目录。

文档中的旧项目本机路径是同一台机器上的定位信息。把新仓库克隆到另一台机器不会自动带来这些文件，也不能把凭证随代码上传。

## 当前边界

下一会话先与用户对齐首版需求。用户确认后才开始应用实现、外部调用和模块迁移。旧项目的历史运行授权、费用额度和默认里程碑，不自动成为新项目的启动指令。

不以“30 个身份已收录”“模型分析已完成”代替“30 个业务评价已完成”。资料不足、未适配和无法核验都是需要清楚展示的结果，不补成 0 分或 100 分。
