# web3-agent-reputation
Multi-source evidence based reputation evaluation platform for Web3 Agents.

面向链上凭证查询、核验与存证 Agent 的任务级证据评价平台。

当前正在实现 M0/M1，尚不是已部署应用。执行计划见 [PLAN.md](PLAN.md)，真实进度见 [STATUS.md](docs/implementation/STATUS.md)。

## 已有检查

从仓库根目录执行：

```powershell
python scripts/check_bootstrap.py
python scripts/git_doctor.py
```

前者验证评分参考、配置和算例；后者只读检查 Git。通过这些检查不代表 API、数据库、合约或端到端验收通过。

## 开发入口

阅读 [AGENTS.md](AGENTS.md)、[任务卡](docs/implementation/BACKLOG.md)、[Windows/Git runbook](docs/runbooks/WINDOWS_AND_GIT.md)。其他规格见 [文档导航](docs/README.md)。

## 产品边界

ERC-8004 身份、8004scan 发现与本项目测评结论分开记录。基础版使用本地测试链，不涉及真实资产。少量样本只生成部分评价，不降低 policy-v1 的 20/10/10 门槛；成功交易必须与当前任务独立关联。技术评价不是主体诚信或未来安全保证。
