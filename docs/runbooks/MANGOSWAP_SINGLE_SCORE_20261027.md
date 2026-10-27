# MangoSwap单分与发布记录

当前默认报告`2c7ded39-f808-40b0-8d15-dddebee21704`，policy `transaction-agent-evidence-v3`，34任务、153判据。刷新[MangoSwap](http://127.0.0.1:7754/?agent=mangoswap-26345)即可查看。

| A可用性 | F功能一致性 | B交易履约 | 综合 |
| ---: | ---: | ---: | ---: |
| 100 | 91.67 | 100 | **96.67** |

每案例按可判P/(P+V)计算，再逐层等权，综合30/40/30；未知、未采、无效测量不填0或100。A的100对应28个可判业务响应，3个待核和3个未采另列；F保留既有资产标签错误，即时兑换75、两项订单管理各100，等权为91.67；B的10个任务为8次兑换和2次创建撤销退款。规则见[ADR-0029](../adr/0029-single-score-and-report-scope.md)。

页面主区仅功能介绍、单分与代表样本。报价或模拟没有预定交易时显示已返回方案/方案已验证，撤销任务显示已撤销退款，真实兑换完成显示已成交；实际FAIL/UNKNOWN仍在样本。未测开发清单不放主页面。自动触发成交、周期等未验证路线已在对话告知，源码退款缺口没有用真实资金触发。

本轮代码发布数据只保留MangoSwap：删除27个旧发布包、候选/实例与审核端点文件；10个旧采集/构建入口改为显式配置。通用规则和适配实现保留。旧对象专属或被新单分验收覆盖的6个验收入口移除，CI只用当前Mango真实包及通用规则，并保留真实PostgreSQL租约/并发/不可改报告检查。

唯一发布包为`data/public-reports-single-score-v3.tar.gz`，1004637字节、1495依赖文件，SHA256 `34ff0f5e5e6f8b1ebb53366f925fb388835d82d2450380d35ab15d4a9486f7bc`。索引仅一个身份mangoswap-26345；含本报告与必要历史原件，1496成员凭据审查0发现。Mango绑定配置/ADR/声明保持原字节，不上传钱包会话/签名器或私有配置。

新环境按README只导入该包即可。已有个人数据库不会因代码拉取自动删除；旧报告留在本机审计历史，Git历史不重写。旧公开包不再随当前版本分发。

本地检查：单项组合验收先因测试误用computed-property对象身份比较报错，修正测试后56.807秒/exit0；覆盖单值不是旧区间端点、未知不进分母、B门槛、真实34任务及旧v2原字节保持。前端构建exit0，PG导入及默认报告/新附件SHA/私有附件404检查通过。离线公开包verify通过（1个Mango报告、0网络请求）；收据runtime/public-report-restore-d57b5a6b244ab80158bef9c816dbdc5f/result.json。浏览器视觉NOT_RUN。没有新增RPC、签名、交易或付款。收据在`runtime/single-score-web-verification-20261027/`。

产品提交`74bcb37c458206e00b5424e0b8b574a4b0ae3b0f`已推送`codex/single-score-report`，通过[PR #22](https://github.com/Ryanjxy123/web3-agent-reputation/pull/22)交付。该产品提交的[CI](https://github.com/Ryanjxy123/web3-agent-reputation/actions/runs/40507551259)中python-web、postgres-smoke均通过；最终合并及最新head检查以PR实时状态为准。PR21保持关闭，下一任务为用户查看单分页面，无待执行资金操作。
