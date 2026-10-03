# ADR 0002：可复现工作空间与契约来源

日期：2026-10-02。状态：M0 实施中。

沿用规划的四个 uv workspace 包，core 不依赖平台，verifier 只依赖 core 和其独立链客户端。schemas 是生成的数据目录。Python 3.12、Node 22；工具版本及解析出的所有运行依赖写入真实锁文件。

Windows 缺失工具优先安装到被忽略的 runtime/tools，不修改系统 PATH 或 Git 全局身份；Foundry 预编译包核对 GitHub 发布资产 SHA-256。PostgreSQL 使用官方 Windows 下载入口关联的 EDB 二进制；数据库并发验收始终使用真实 PostgreSQL。Docker 尚未安装，Compose 运行验收仍未完成；本机直接启动路径不代表 Compose 已验证。

领域 DTO 是 Pydantic v2 单一来源。JSON Schema、OpenAPI 和 TS 从其生成。新增必填字段、修改安全语义需同步测试及格式版本；M0 初始版本 1.0.0，目前没有已发布报告需要迁移。

回归：原 policy-v1 与 36 条 golden/reference 测试保持不变。仅将参考模块中歧义变量 l 重命名为 timely，评分公式不变。架构测试禁止 core 网络/DB依赖，禁止 verifier 导入平台。

M0-04 实测：EDB Windows initdb 在当前中文安装路径将 ANSI 路径嵌入 UTF-8 初始化 SQL 后失败。使用动态空闲 subst 盘符仅映射项目 runtime；二进制和数据仍位于唯一正式项目中，Git/代码/文档操作仍在原中文路径。PostgreSQL 17.11 的 initdb、迁移、事务和并发测试通过。Compose/Linux 不需要此 Windows 兼容层。

2026-10-03 本地运行修复：用项目所在盘根目录的 `web3-runtime` NTFS 目录联接替代上述 subst 盘符。本机 `D:\web3-runtime` 指向原 runtime；脚本自动创建、核对目标，拒绝同名冲突，不再读写 postgres-drive.json 或创建 R:。保留中文目录、数据库和凭证；真实 initdb 及移除 R: 后的重启与 SQL 连接已验证。旧 subst 方案仅为历史记录。
