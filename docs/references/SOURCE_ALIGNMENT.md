# 来源对齐与未核实事项

## 1. 本项目需求来源
用户上传《Web3_Agent_项目实施规划_PRD_V1.0.docx》（26页）与《Web3_Agent_项目介绍与展示方案_V1.0.docx》（11页），版本原资料核对日2026-09-23。
PRD为待确认基线，不是已完成系统。本包没有复制其“拟完成目标”为实测结果。

| 原文位置 | 保留内容 | 本包落地 |
|---|---|---|
| PRD1/2/3 | 业务场景、三维、P0/不做范围 | PLAN、AGENTS、BACKLOG |
| PRD5/10 | 技术栈、模型/API、任务恢复 | ARCHITECTURE、DOMAIN、API、SECURITY_AND_JOBS |
| PRD6/7 | ERC身份、执行绑定、三能力、目的分离 | ERC8004、EVALUATION、EVIDENCE_AND_CONTRACTS |
| PRD8 | A/B/T/Q、样本阈值、只读与golden | policy-v1.json、scoring_reference、36项reference tests |
| PRD9 | 三合约、JCS/Keccak、证据包/独立复核 | EVIDENCE_AND_CONTRACTS与M1任务卡 |
| PRD11/12 | M0–M4、短分支/PR、团队分工 | BACKLOG、WINDOWS_AND_GIT、EXTENSIONS |
| PRD13/14 | SSRF、八类样本、消融、真实实验 | SECURITY_AND_JOBS、ACCEPTANCE |
| PRD15/16 | 可执行交付、创新边界、P1 | DEMO_AND_RELEASE、PLAN |

工程细化不是原文已经给出的唯一标准：目录合并、API版本前缀、整数基点、精确阈值、角色化绑定、派生统计复核、发送状态、非覆盖安装、Git条件流程都由本包提出。ADR-0001明确这些变化。

## 2. 未能读取的来源
共享聊天：
- https://chatgpt.com/share/6abf7c9d-a998-83e9-9860-555294a2167a
- https://chatgpt.com/share/6abf7ccc-3b74-83e9-ba03-ab3a9bb8005a
此次读取仅获得页面标题，未获得正文，因此没有声称继承其中不可见的具体技术决定。
用户GitHub仓库公开读取返回404，无法确定是私有、权限、地址还是其他原因；不能断言“仓库为空”。本地路径也未连接。
后续Codex M0必须读取实际文件与Git历史；若存在已确认方案冲突，保留现有内容，写明差异并做最小兼容调整。

## 3. 外部核对范围
实际网页核对ERC提案/官方合约仓库、best-practices、8004scan开发者页与OpenAPI、PostgreSQL/OWASP/JCS/EIP712/Codex/GitHub/uv官方资料。
没有取得上游固定git commit/文件下载hash，没有使用RPC实测公网合约，没有采集真实Agent样本、没有试调用其业务接口，没有设置用户GitHub权限或进行push。
所有上游地址/请求是待本地核实的集成线索，示例外部功能disabled。详见SOURCES。
