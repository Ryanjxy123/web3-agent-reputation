# ADR 0003：受控服务与宿主回环入口

状态：采用；2026-10-02。

Linux CI 运行 37017016686 中 API/数据库健康、迁移成功，但所有只连接 internal 网络的容器在 `docker compose ps` 中没有 published ports，宿主回环访问超时。原生同一 smoke 脚本通过，定位为容器网络接入配置。

保持 control 与 demo 内网，另给确需宿主入口的 API、web、Anvil 连接普通 ingress bridge，并继续只发布到 `127.0.0.1`。PostgreSQL、worker 和受控 fixture 不连接 ingress；不挂载 Docker socket。API 不持签名私钥；受控 HTTP 出口仍精确白名单，公网功能继续禁用。

普通 bridge 提供了这三个进程的网络路由能力，因此不能宣称它们被网络层彻底禁止外网。当前信任运行中的平台代码及 SafeHttpClient；不执行不可信插件/元数据代码。未来公网接入仍需 M3 安全出口，不能仅修改开关绕过。

验证：原生 smoke 已通过；修改后的 Compose 必须重新构建并从宿主检查 API、web proxy、401 和 Anvil chainId，结果记录 STATUS。
