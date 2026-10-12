# ADR 0023：Vite WebSocket 资源访问边界（SEC-2）

状态：已采纳；2026-10-12。本轮 SEC-2 指用户指定的 Vite WebSocket 问题。

锁定的 Vite 7.1.9 在客户端 HMR WebSocket 上注册 `vite:invoke` 的
`fetchModule` 模块读取 RPC。HTTP 的 `server.fs.allow` / `server.fs.deny`
检查没有覆盖这条路径；只使用新建合成 `.env.synthetic` 文件的回环复现确认
HTTP 返回 403，而无 Origin 的 WebSocket 返回文件内容。

原生 `pnpm dev` 受影响。当前 Compose Web 镜像虽然先执行 build，启动命令
仍是 `pnpm dev --host 0.0.0.0`，所以交付运行也受影响；宿主端口只映射到
127.0.0.1，不代表容器网络内不能接触服务。单独静态托管 `dist` 不运行
Vite HMR / RPC，但这不是仓库当前的 Compose 运行方式。

将 Vite 精确升级至 7.3.2，并提交 pnpm 生成的锁文件。这是
[GHSA-p9ff-h696-f583](https://github.com/advisories/GHSA-p9ff-h696-f583)
的首个修复版本。上游在默认 client environment 设置 `disableFetchModule`
并在 RPC handler 读取资源前拒绝请求。本项目没有 SSR / ModuleRunner 调用，
前端正常资源继续通过 HTTP 读取，HMR 保留更新通道。复用上游修复，不新增
本地路径解析、WebSocket 拦截插件或运行服务架构。

回归通过实际项目 Vite 配置启动独立回环服务，使用临时合成目录作为 root
和 envDir。验证 allow 外文件与 allow 内 deny 文件均不能经 WebSocket 读取，
覆盖路径编码、异常请求、无 Origin 与浏览器正常连接；另外验证实际浏览器
HMR、HTTP 正常资源和回环 API / health 代理。`pnpm test` 自动执行该集成集，
因此既有 `scripts/check.py` 和 foundation-quality CI 会执行它。

已有运行进程仍可能加载旧 Vite，必须重启原生前端或重新构建并重启 Web
容器才能应用更新。此次仅修复这条客户端资源读取路径，不把开发服务器
宣称为正式生产静态托管，也不改变 API 权限、证据、评分或历史数据。
