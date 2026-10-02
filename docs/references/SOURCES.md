# 外部资料与引用登记

网页核对日期2026-10-02。URL可能更新；M0/M4对实际使用的ABI、OpenAPI、依赖和规范快照固定版本/hash。以下列表本身不是完整upstream lock。
引用只支持相应标准/产品能力，不证明本项目实验有效，不构成“全球无相似方案”的检索结论。

| ID | 来源与URL | 本包使用范围 |
|---|---|---|
| S01 | Ethereum EIP，ERC-8004 https://eips.ethereum.org/EIPS/eip-8004 | 身份/反馈/验证，Draft状态，agentWallet语义，接口边界 |
| S02 | 官方合约仓库 https://github.com/erc-8004/erc-8004-contracts | ABI/部署/许可来源；读取时默认branch master；实际commit待锁 |
| S03 | 8004scan开发者 https://8004scan.io/developers | API入口、认证、OpenAPI、配额动态性 |
| S04 | 8004scan OpenAPI https://api.8004scan.io/openapi.json | 只读agents路由、过滤、复合identity、分页 |
| S05 | ERC8004 best practices https://github.com/erc-8004/best-practices/blob/main/Reputation.md | 可达性/成功率/延迟已有实践，避免错误创新声明 |
| S06 | OWASP SSRF https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html | 白名单/地址校验/DNS与网络边界 |
| S07 | RFC8785 https://www.rfc-editor.org/rfc/rfc8785 | JSON规范化，不能把任意json.dumps当JCS |
| S08 | EIP712 https://eips.ethereum.org/EIPS/eip-712 | 结构化签名；具体绑定与重放防护为本项目定义 |
| S09 | PostgreSQL SELECT https://www.postgresql.org/docs/current/sql-select.html | SKIP LOCKED队列领取；不保证外部恰好一次 |
| S10 | Ethereum JSON-RPC https://ethereum.org/developers/docs/apis/json-rpc/ | tx/receipt/block/log读取与独立核验 |
| S11 | GitHub保护分支 https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches | 保护、checks、权限与方案可用性 |
| S12 | OpenAI Codex Windows https://developers.openai.com/codex/windows/ | Windows运行与审批边界，环境依实际核查 |
| S13 | OpenAI Codex WSL https://developers.openai.com/codex/windows/wsl | 可选WSL/Linux工具环境 |
| S14 | OpenAI AGENTS.md https://developers.openai.com/codex/agent-configuration/agents-md | 目录层次的项目指令；普通md并非自动全读 |
| S15 | OpenAI ExecPlans https://developers.openai.com/cookbook/articles/codex_exec_plans | 活动计划、可复現里程碑和交接写法 |
| S16 | uv workspace https://docs.astral.sh/uv/concepts/projects/workspaces/ | 单lock、多包显式成员与workspace依赖 |
| S17 | GitHub既有本地代码 https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github | init/remote/push按现状选择，避免覆盖已有历史 |
| S18 | Python rfc8785库 https://pypi.org/project/rfc8785/ | JCS库候选；实际版本在M0兼容测试后锁定 |

源DOCX另见SOURCE_ALIGNMENT，公开提交是否附原DOCX由负责人决定，不自动把含个人元数据的文件加入Git。
依赖安装后生成实际THIRD_PARTY_NOTICES/许可清单；本包不擅自替用户仓库选择或更改LICENSE。
