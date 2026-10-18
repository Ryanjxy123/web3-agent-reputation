# 本机前端

Vue 3 + TypeScript + Vite。目录、报告和任务状态均读取平台 API；共享接口类型来自 `../../packages/core/generated/contracts.ts`。

本轮已核对官方 npm 元数据并锁定 Vue 3.5.44、Vite 8.3.4、@vitejs/plugin-vue 6.0.10、vue-tsc 3.3.13、TypeScript 5.9.3。Node 使用已安装的 22.17.0，pnpm 11.25.0；依赖版本与独立 `pnpm-lock.yaml` 一起维护。

## 本机开发

先启动平台后端（`127.0.0.1:7754`），在本目录运行：

```powershell
pnpm install --frozen-lockfile
pnpm dev
```

Vite 只监听 `127.0.0.1:5175`，`/api` 代理到本机后端。不绑定公网，不注册、同步或发布 Sites 远程站点。生产构建放在 `dist`，由平台同源提供静态资源与 API。

## 实际验证

2026-10-18 使用 Node 22.17.0、pnpm 11.25.0 执行 `pnpm run build`，退出 0。该命令依次运行 `vue-tsc --noEmit -p tsconfig.json` 与 `vite build`；两项均通过，仅执行一次。没有添加前端单元测试，也未重复已有浏览器崩溃尝试。浏览器视觉与前后端完整流程验收由整体应用集成阶段另记。

页面以查询参数保留当前位置：`?agent=<key>&report=<id>` 查看对象和历史报告，`?view=submit&job=<id>` 查看任务。只有当前打开且仍在排队或运行中的任务自动读取进度，终态停止；成功后跳到实际报告。
