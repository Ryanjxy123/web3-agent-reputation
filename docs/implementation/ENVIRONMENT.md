# 本地环境审查

日期：2026-10-02；Windows / PowerShell，正式目录包含中文。

## M0-01 仓库

- 初始正式目录为空且无 `.git`，没有用户未提交文件。
- 官方 GitHub device flow 已完成；私有仓库身份和读取权限已核实。
- 远程默认分支 main，初始提交 `e9430d186d7c63ddc8e2da2d70231ccb4873c8b1`，仅有 README。
- 安全 clone 后 fetch 成功，无其他远程分支，无历史冲突。
- 当前工作分支 `feat/foundation-m0-m1`；origin 与项目预期相同。
- Git 提交身份已存在，未修改任何全局身份或仓库权限。
- 启动包 44 个 manifest 项的大小和 SHA-256 全部匹配；安装 dry-run 通过。
- 唯一 sidecar 是 README，已保留原英文介绍并语义合并说明；sidecar 保留在被忽略目录以便追溯。

## 初始工具状态

| 工具 | 实测 | 分类 |
|---|---|---|
| Python | python 3.12.4；py -3 3.10.11 | 实施使用 3.12；安装器可用 3.10 |
| Node.js | 22.17.0 | 当前需要 |
| npm / pnpm | 11.4.2 / 10.12.4 | 前端使用 pnpm |
| Git / gh | 2.47.1.windows.2 / 2.97.0 | 可用 |
| Git Credential Manager | 2.6.1 | 可用 |
| uv | 未找到 | M0-02 安装并锁定 |
| Docker / Compose | 未找到 | 编排验收仍需解决 |
| Foundry / Anvil | 未找到 | M0-02 / M1 需要真实安装 |
| PostgreSQL | 未找到命令或服务 | M0-04 需要真实数据库 |

这里只记录实际检查，不把工具缺失视为测试通过。后续版本、安装方式和命令记录在任务状态中。
