# 视觉与任务证据工作台 · 2026-10-28

已完成，分支 `codex/evidence-workbench`，本地修改保留待审阅。当前验收入口：http://127.0.0.1:7756/。原7754服务保留，未停止或替换；已运行的旧API需重启新代码才支持按任务的只读摘要，本轮另启7756验证，未启动worker。原私有数据库配置未覆盖；验收进程只在内存中复用既有服务连接设置（本机当前使用不同schema）。

## 页面与交互

统一深空主题、品牌导航、接入表单和报告/错误状态。单对象入口包含真实分数、任务/履约任务/判据计数、原生兑换、定时/限价退款、声明不符和测量待核样本。详情分概览、任务链路、评价报告、链上证据；保留注册链与业务链分离。

工作台包含任务搜索/能力及结果筛选、业务执行/证据核验两层SVG关系图、步骤/判据/证据标签、可折叠底部明细、节点检查和受控JSON预览。选择任务、节点、步骤、判据与评分维度相互定位；支持缩放、适应、重置、纯前端播放/暂停/前后步骤/重置。窄桌面使用检查抽屉，手机使用纵向步骤；Escape关闭并返回焦点。保留所有旧sample/task锚点及报告选择参数，增加稳定的report/task/node深链接和报告JSON下载。

## 数据来源与边界

实际API当前报告 `b8000bbd-429c-4a4b-86da-32b6bc91db71`，不同于旧文档 `2c7ded39-...`；34任务、153判据、A100/F91.67/B100/综合96.67一致。Agent补测快照当前为null，没有把其他报告或快照混入。

- 以shared_assessment.tasks.task_key连接observations/cases及samples.sample.task_key，再用sample_id、该报告明确引用的证据集合校验操作。组件缓存仅作用于当前报告。
- HTTP请求、响应、传输观测从既有报告证据下载接口按需读取。结构化输入输出来自原件，不编内部工具日志。生命周期三任务未记录业务HTTP，因此对应节点标未记录，不以交易代替服务可用性。
- 现有 `/api/reports/{id}/chain-evidence` 向后兼容增加可选task_key；只读取当前报告白名单且通过SHA校验的交易/回执/区块/ABI。按真实calldata展开同笔批调用，查询不是独立交易。core评分与生成契约未修改。
- E1原生兑换为1操作/1交易；E2定时管理为7操作/1交易（4读取）；E3限价管理为8操作/1交易（5读取）。实际chain_id均8453。所有操作沿用任务结论，不新增逐调用核验。
- 区块时间、HTTP原始时间、报告生成时间分别标示；observed_at只作采证记录时间。回放按序列，不生成耗时。没有Agent规划、内部工具选择、模型思考或签名交互日志；查询内部返回未记录，不把模拟中间态冒充链上返回。自动触发成交/周期执行仍未测。

## 修改位置

`apps/web/src/App.vue` 页面路由与入口；`AgentOverview.vue`/`overview.css` 单对象概览；`TaskTraceWorkbench.vue`、`TaskTraceCanvas.vue`及对应CSS为工作台；`TraceInspector.vue`/`inspector.css` 为证据检查；`traceProjection.ts` 为纯展示投影；`style.css`、`shared-assessment.css`、`ReportView.vue`及`SharedAssessmentView.vue`为统一主题与报告联动。后端仅 `api.py`/`db.py`/`report_chain_view.py` 只读路径及再生OpenAPI。未添加依赖。

## 实际验证

- `pnpm --dir apps/web run build`：vue-tsc与Vite均PASS。视觉修正后按受影响前端重建；最终资源约15KiB CSS/74KiB JS gzip。
- `node --experimental-strip-types --test apps/web/tests/traceProjection.test.mjs`：5/5 PASS。覆盖稳定关联、跨报告/外来来源拒绝、多交易与同笔多操作、缺字段/报价不补钱包/时间、HTTP嵌套字段与只读GET边界。
- `.venv/Scripts/python.exe -m unittest tests.test_report_chain_view`：2/2 PASS。覆盖真实批调用读写区分、同hash、多交易及摘要篡改拒绝。OpenAPI已用项目脚本再生。
- 本机HTTP10项PASS；7754/7756整份报告响应字节相同，canonical SHA256 `6288b2f12eea3f41eed70e0d3f602260db86d5a9c41c20287c01d1f92412d7e9`。11份原件在两API及本地逐字节一致。未知任务空操作，私有/未引用附件404。收据 `runtime/visual-trace-20261028/http-checks.json`。
- 实际IAB检查1440×900、1920×1080、1100×900、390×844，浏览器缩放100%。兑换/两项订单退款/ETH-WETH不符/A05测量待核均检查；节点/步骤/判据、评分跳转、原件JSON、播放暂停和前后步骤、#sample-12深链接、Escape与焦点返回通过。桌面几何复核节点无重叠、连线不穿节点内部、页面无横向溢出。
- 复制按钮成功反馈已核；虚拟浏览器剪贴板无法读回navigator.clipboard写入，独立粘贴验收BLOCKED。当前API仅一份报告，多版本切换NOT_RUN；选择器/查询参数保留。IAB全页/裁剪捕获受工具限制，交付正常viewport截图。新评价提交NOT_RUN。

## 真实截图

位于 `runtime/visual-trace-20261028/`：

- `entry-1440.jpg`：入口。
- `task-trace-1920.jpg`：订单工作台。
- `evidence-inspector.jpg`：选中真实订单合约调用的检查抽屉。
- `mobile-trace-390.jpg`：手机纵向步骤；`before-entry-1440.jpg`：改造前。

浏览器检查收据 `browser-checks.json`，独立API进程信息 `process.json`，均不含凭据。

本轮无新实验、RPC/LLM/Agent付费调用、签名、授权、交易、充值或业务数据写入。已有报告/原件保持；未提交、推送、合并或部署。没有待办资金操作。
